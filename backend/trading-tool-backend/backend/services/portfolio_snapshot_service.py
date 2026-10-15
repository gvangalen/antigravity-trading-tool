import logging
from datetime import datetime, timedelta, timezone
from typing import Literal, List, Tuple

from backend.utils.db import get_db_connection

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BucketType = Literal["1h", "1d"]


# =====================================================
# 🕒 Helpers
# =====================================================

def floor_timestamp(dt: datetime, bucket: BucketType) -> datetime:
    if bucket == "1h":
        return dt.replace(minute=0, second=0, microsecond=0)
    if bucket == "1d":
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return dt


# =====================================================
# 💰 Symbol Price
# =====================================================

def _get_latest_price(cur, symbol: str) -> float:
    cur.execute("""
        SELECT m.price, a.quote_currency, m.timestamp
        FROM market_data m
        LEFT JOIN asset_catalog a ON a.symbol = m.symbol
        WHERE m.symbol = %s
          AND m.price IS NOT NULL
        ORDER BY m.timestamp DESC
        LIMIT 1
    """, (symbol.upper(),))
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"Geen {symbol.upper()} prijs gevonden")
    if str(row[1] or "").upper() != "EUR":
        raise RuntimeError(f"Geen gecontroleerde EUR-prijs voor {symbol.upper()}")
    observed_at = row[2]
    if observed_at is None:
        raise RuntimeError(f"Geen gedateerde EUR-prijs voor {symbol.upper()}")
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    if not timedelta(0) <= datetime.now(timezone.utc) - observed_at <= timedelta(hours=24):
        raise RuntimeError(f"Geen recente EUR-prijs voor {symbol.upper()}")
    return float(row[0])


# =====================================================
# 🚀 SNAPSHOT SERVICE (PRO VERSION)
# =====================================================

def snapshot_all_for_user(
    user_id: int,
    bucket: BucketType = "1h",
) -> None:

    ts = floor_timestamp(datetime.utcnow(), bucket)

    with get_db_connection() as conn:
        with conn.cursor() as cur:

            # =====================================================
            # 🔁 PER BOT (FROM BOT_PORTFOLIOS)
            # =====================================================

            global_cash = 0.0
            global_btc_qty = 0.0
            global_btc_value = 0.0
            global_position_value = 0.0
            global_invested = 0.0
            global_realized_pnl = 0.0
            price_cache = {}

            cur.execute("""
                SELECT 
                    bp.bot_id,
                    COALESCE(NULLIF(UPPER(bc.symbol), ''), 'BTC') AS symbol,
                    bp.cash_eur,
                    bp.position_qty,
                    bp.invested_eur,
                    bp.avg_entry,
                    bp.realized_pnl_eur
                FROM bot_portfolios bp
                JOIN bot_configs bc
                    ON bc.id = bp.bot_id
                   AND bc.user_id = bp.user_id
                WHERE bp.user_id=%s AND bc.is_live=FALSE
            """, (user_id,))

            portfolio_rows = cur.fetchall()
            # Live ledger cash is a trade delta, not a funded exchange wallet.
            # Do not publish it as account equity until an exchange-backed
            # valuation contract is available.
            if not portfolio_rows:
                return

            # A missing quote makes the complete valuation unknown. Do not
            # write a new partial snapshot that silently excludes a funded
            # bot's cash or treats its held position as worth zero.
            for bot_id, symbol, _cash, qty, *_rest in portfolio_rows:
                if float(qty or 0) == 0:
                    continue
                symbol = (symbol or "BTC").upper()
                try:
                    if symbol not in price_cache:
                        price_cache[symbol] = _get_latest_price(cur, symbol)
                except Exception:
                    logger.warning("Portfolio snapshot uitgesteld: gecontroleerde EUR-koers ontbreekt voor bot=%s asset=%s", bot_id, symbol)
                    return

            for bot_id, symbol, b_cash, b_qty, b_invested, b_avg, b_realized in portfolio_rows:
                symbol = (symbol or "BTC").upper()
                b_cash = float(b_cash or 0)
                b_qty = float(b_qty or 0)
                b_invested = float(b_invested or 0)
                b_realized = float(b_realized or 0)

                if b_qty == 0:
                    # An unfunded or newly funded Paper bot has no position to
                    # value. Its virtual cash is known even without a quote.
                    price = 0.0
                else:
                    price = price_cache[symbol]

                # Position value at current market price
                position_value = b_qty * price

                # Equity = Cash + Current Asset Value
                bot_equity = b_cash + position_value

                # Unrealized PnL = Current Value - Cost Basis
                unrealized_pnl = position_value - b_invested

                # Accumulate globals
                global_cash += b_cash
                global_position_value += position_value
                if symbol == "BTC":
                    global_btc_qty += b_qty
                    global_btc_value += position_value
                global_invested += b_invested
                global_realized_pnl += b_realized

                # =====================================================
                # 🤖 BOT SNAPSHOT
                # =====================================================
                cur.execute("""
                    INSERT INTO bot_portfolio_snapshots
                    (
                        user_id, bot_id, bucket, ts, symbol,
                        net_qty, cash_eur, price_eur, equity_eur, invested_eur
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (user_id, bot_id, bucket, ts)
                    DO UPDATE SET
                        net_qty      = EXCLUDED.net_qty,
                        cash_eur     = EXCLUDED.cash_eur,
                        price_eur    = EXCLUDED.price_eur,
                        equity_eur   = EXCLUDED.equity_eur,
                        invested_eur = EXCLUDED.invested_eur
                """, (
                    user_id, bot_id, bucket, ts, symbol,
                    b_qty, b_cash, price, bot_equity, b_invested
                ))

                logger.info(
                    f"📊 Bot accurate snapshot | bot={bot_id} | symbol={symbol} | equity={round(bot_equity,2)} "
                    f"| realized={round(b_realized,2)}"
                )

            # =====================================================
            # 🌍 GLOBAL SNAPSHOT (PRO)
            # =====================================================

            global_equity = global_cash + global_position_value
            global_unrealized = global_position_value - global_invested

            cur.execute("""
                INSERT INTO portfolio_balance_snapshots
                (
                    user_id,
                    bucket,
                    ts,
                    equity_eur,
                    cash_eur,
                    btc_qty,
                    btc_value_eur,
                    invested_eur,
                    unrealized_pnl_eur
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (user_id, bucket, ts)
                DO UPDATE SET
                    equity_eur          = EXCLUDED.equity_eur,
                    cash_eur            = EXCLUDED.cash_eur,
                    btc_qty             = EXCLUDED.btc_qty,
                    btc_value_eur       = EXCLUDED.btc_value_eur,
                    invested_eur        = EXCLUDED.invested_eur,
                    unrealized_pnl_eur  = EXCLUDED.unrealized_pnl_eur
            """, (
                user_id,
                bucket,
                ts,
                global_equity,
                global_cash,
                global_btc_qty,
                global_btc_value,
                global_invested,
                global_unrealized
            ))

            logger.info(
                f"🌍 Global snapshot | equity={round(global_equity,2)} "
                f"| cash={round(global_cash,2)} "
                f"| btc={round(global_btc_qty,6)} "
                f"| invested={round(global_invested,2)} "
                f"| unrealized={round(global_unrealized,2)}"
            )
