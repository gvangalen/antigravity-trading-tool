import logging
from datetime import datetime
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
# 💰 BTC Price
# =====================================================

def _get_latest_btc_price(cur) -> float:
    cur.execute("""
        SELECT price
        FROM market_data
        WHERE symbol = 'BTC'
          AND price IS NOT NULL
        ORDER BY timestamp DESC
        LIMIT 1
    """)
    row = cur.fetchone()
    if not row:
        raise RuntimeError("Geen BTC prijs gevonden")
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
            # 📈 BTC PRIJS
            # =====================================================
            try:
                price = _get_latest_btc_price(cur)
            except Exception:
                logger.exception("❌ BTC prijs ophalen mislukt")
                return

            # =====================================================
            # 🤖 BOTS + BUDGET
            # =====================================================
            cur.execute("""
                SELECT id, COALESCE(budget_total_eur,0)
                FROM bot_configs
                WHERE user_id=%s
            """, (user_id,))

            bots: List[Tuple[int, float]] = cur.fetchall()

            # =====================================================
            # 🔁 PER BOT (FROM BOT_PORTFOLIOS)
            # =====================================================

            global_cash = 0.0
            global_qty = 0.0
            global_invested = 0.0
            global_realized_pnl = 0.0

            cur.execute("""
                SELECT 
                    bot_id, cash_eur, position_qty, invested_eur, avg_entry, realized_pnl_eur
                FROM bot_portfolios
                WHERE user_id=%s
            """, (user_id,))

            portfolio_rows = cur.fetchall()

            for bot_id, b_cash, b_qty, b_invested, b_avg, b_realized in portfolio_rows:
                b_cash = float(b_cash or 0)
                b_qty = float(b_qty or 0)
                b_invested = float(b_invested or 0)
                b_realized = float(b_realized or 0)

                # Position value at current market price
                position_value = b_qty * price

                # Equity = Cash + Current Asset Value
                bot_equity = b_cash + position_value

                # Unrealized PnL = Current Value - Cost Basis
                unrealized_pnl = position_value - b_invested

                # Accumulate globals
                global_cash += b_cash
                global_qty += b_qty
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
                    user_id, bot_id, bucket, ts, "BTC",
                    b_qty, b_cash, price, bot_equity, b_invested
                ))

                logger.info(
                    f"📊 Bot accurate snapshot | bot={bot_id} | equity={round(bot_equity,2)} "
                    f"| realized={round(b_realized,2)}"
                )

            # =====================================================
            # 🌍 GLOBAL SNAPSHOT (PRO)
            # =====================================================

            global_btc_value = global_qty * price
            global_equity = global_cash + global_btc_value
            global_unrealized = global_btc_value - global_invested

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
                global_qty,
                global_btc_value,
                global_invested,
                global_unrealized
            ))

            logger.info(
                f"🌍 Global snapshot | equity={round(global_equity,2)} "
                f"| cash={round(global_cash,2)} "
                f"| btc={round(global_qty,6)} "
                f"| invested={round(global_invested,2)} "
                f"| unrealized={round(global_unrealized,2)}"
            )
