# backend/engine/trading_bot_execution.py
import logging
import json
import math
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from backend.utils.db import get_db_connection
# ✅ Engine brain (single source of truth)
from backend.engine.bot_brain import run_bot_brain
from backend.engine.guardrails_engine import apply_guardrails
from backend.domain.finn_dca_plan_contract import benchmark_score, normalize_benchmark_weights, is_confirmed_dca_amount_rule
from backend.domain.setup_market_match import match_setup_from_daily_scores
import asyncio
from backend.services.exchange_service import ExchangeService
from backend.services.platform_metrics import increment_execution_safety_counter
from backend.utils.encryption_utils import EncryptionUtils


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

DEFAULT_SYMBOL = "BTC"

ACTIONS = ("buy", "sell", "hold", "observe")
CONFIDENCE_LEVELS = ("low", "medium", "high")


# =====================================================
# 🔧 Helpers
# =====================================================
def _table_exists(conn, table: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema='public'
              AND table_name=%s
            """,
            (table,),
        )
        return cur.fetchone() is not None

def _map_confidence(v: float) -> str:
    if v >= 0.7:
        return "high"
    elif v >= 0.4:
        return "medium"
    return "low"


def _verified_score(v: Any) -> Optional[float]:
    """Score 2.0: a measured zero is valid; missing or invalid is unknown."""
    try:
        if v is None or isinstance(v, bool):
            return None
        x = float(v)
        return x if math.isfinite(x) and 0 <= x <= 100 else None
    except (TypeError, ValueError):
        return None


def _normalize_action(v: str) -> str:
    v = (v or "").lower().strip()
    return v if v in ACTIONS else "hold"


def _normalize_confidence(v: str) -> str:
    v = (v or "").lower().strip()
    return v if v in CONFIDENCE_LEVELS else "low"


def _safe_json(v, fallback):
    if v is None:
        return fallback
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except Exception:
        return fallback

def _get_live_price(
    conn, symbol: str, max_age_seconds: Optional[int] = None,
    *, paper_execution: bool = False,
) -> Optional[float]:
    symbol = (symbol or DEFAULT_SYMBOL).upper()

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.price, EXTRACT(EPOCH FROM (NOW() - m.timestamp)) AS age_seconds,
                   a.quote_currency, m.source_observed_at, m.quote_currency
            FROM market_data m
            LEFT JOIN asset_catalog a ON a.symbol = m.symbol
            WHERE m.symbol = %s
              AND m.price IS NOT NULL
              AND m.source_observed_at IS NOT NULL
              AND m.quote_currency IS NOT NULL
            ORDER BY m.source_observed_at DESC, m.timestamp DESC
            LIMIT 1
            """,
            (symbol,),
        )
        row = cur.fetchone()

    if not row or row[0] is None:
        return None
    if str(row[2] or "").upper() != str(row[4] or "").upper():
        return None

    if max_age_seconds is not None and (row[1] is None or float(row[1]) > max_age_seconds or float(row[1]) < -60):
        return None
    if max_age_seconds is not None and str(row[2] or "").upper() != "EUR":
        return None

    if max_age_seconds is not None:
        price = float(row[0])
        return price if math.isfinite(price) and price > 0 else None

    from backend.services.portfolio_fx_service import price_in_eur, trade_quote_context
    quote = str(row[4] or "").upper()
    fx = None
    if quote in {"USD", "USDT"}:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT eur_per_unit, observed_at FROM portfolio_fx_rates
                WHERE quote_currency=%s
            """, (quote,))
            fx_row = cur.fetchone()
        if fx_row:
            fx = {"eur_per_unit": fx_row[0], "observed_at": fx_row[1]}
    if paper_execution:
        checked = trade_quote_context(
            price=row[0], price_at=row[3], row_quote=row[4],
            catalog_quote=row[2], usd_fx=None, quote_fx=fx, require_usd=False,
        )
        return checked.get("market_price_eur")
    eur_price, _source_at, _factor, _fx_at = price_in_eur(
        price=row[0], price_at=row[3], quote_currency=quote, fx=fx,
    )
    return eur_price


def _get_trade_quote_fx_context(conn, symbol: str, *, require_usd: bool = True) -> dict:
    """Read the verified row quote and independent dated FX sources."""
    with conn.cursor() as cur:
        cur.execute("SELECT quote_currency FROM asset_catalog WHERE symbol=%s LIMIT 1", (symbol,))
        row = cur.fetchone()
    catalog_quote = str(row[0] or "").upper() if row else ""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT quote_currency, eur_per_unit, observed_at FROM portfolio_fx_rates
            WHERE quote_currency IN ('USD', 'USDT')
        """)
        fx_rows = {
            str(currency).upper(): {"eur_per_unit": factor, "observed_at": at}
            for currency, factor, at in cur.fetchall()
        }
        cur.execute("""
            SELECT price, source_observed_at, quote_currency FROM market_data
            WHERE symbol=%s AND price IS NOT NULL
              AND source_observed_at IS NOT NULL
              AND quote_currency IS NOT NULL
            ORDER BY source_observed_at DESC, timestamp DESC LIMIT 1
        """, (symbol,))
        market_row = cur.fetchone()
    from backend.services.portfolio_fx_service import trade_quote_context
    verified = trade_quote_context(
        price=market_row[0] if market_row else None,
        price_at=market_row[1] if market_row else None,
        row_quote=market_row[2] if market_row else None,
        catalog_quote=catalog_quote,
        usd_fx=fx_rows.get("USD"),
        quote_fx=fx_rows.get(catalog_quote),
        require_usd=require_usd,
    )
    return {
        **verified, "quote_currency": catalog_quote,
        "eur_per_unit": verified.get("usd_fx_eur_per_unit"),
        "fx_as_of": verified.get("usd_fx_as_of"),
        "live_price_eur": verified.get("market_price_eur"),
    }


def _convert_trade_snapshot_to_eur(snapshot: dict, factor: float) -> dict:
    """Convert every saved USD level with the same verified FX factor."""
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError("Invalid trade FX factor")
    return {
        **snapshot,
        "entry": snapshot["entry"] * factor if snapshot.get("entry") is not None else None,
        "stop_loss": snapshot["stop_loss"] * factor if snapshot.get("stop_loss") is not None else None,
        "targets": [value * factor for value in snapshot.get("targets") or []],
    }

def _clear_existing_pending_orders_for_day(
    conn,
    *,
    user_id: int,
    bot_id: int,
    decision_id: int,
):
    """
    Zorgt dat oude ready/pending orders niet blijven hangen
    wanneer een decision opnieuw gegenereerd wordt.
    """
    if not _table_exists(conn, "bot_orders"):
        return

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE bot_orders
            SET status = 'cancelled',
                updated_at = NOW()
            WHERE user_id = %s
              AND bot_id = %s
              AND decision_id = %s
              AND status IN ('ready', 'pending')
            """,
            (user_id, bot_id, decision_id),
        )

    if _table_exists(conn, "bot_executions"):
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE bot_executions
                SET status = 'cancelled',
                    updated_at = NOW()
                WHERE user_id = %s
                  AND bot_order_id IN (
                      SELECT id
                      FROM bot_orders
                      WHERE user_id = %s
                        AND bot_id = %s
                        AND decision_id = %s
                  )
                  AND status = 'pending'
                """,
                (user_id, user_id, bot_id, decision_id),
            )

def _execute_on_exchange_sync(conn, user_id: int, exchange_name: str, symbol: str, side: str, qty: float, price: float):
    """
    Sync wrapper to execute on exchange using the async ExchangeService.
    """
    # 1. Fetch keys
    with conn.cursor() as cur:
        cur.execute(
            "SELECT api_key, api_secret, api_passphrase FROM exchange_keys WHERE user_id=%s AND exchange_name=%s AND is_active=TRUE LIMIT 1",
            (user_id, exchange_name)
        )
        row = cur.fetchone()
    
    if not row:
        raise RuntimeError(f"No active keys found for {exchange_name}")
    
    api_key, api_secret, api_passphrase = row

    async def _run():
        client = await ExchangeService.get_client(exchange_name, api_key, api_secret, api_passphrase)
        # Always use limit for safety in manual/bot trades
        return await ExchangeService.create_order(client, symbol, side, qty, price, order_type='limit')

    try:
        return asyncio.run(_run())
    except Exception:
        logger.error("Exchange order submission failed")
        raise

def _get_live_exchange_balance(conn, user_id: int) -> tuple[str, dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT exchange_name, api_key, api_secret, api_passphrase FROM exchange_keys "
            "WHERE user_id=%s AND is_active=TRUE ORDER BY id ASC LIMIT 2",
            (user_id,),
        )
        rows = cur.fetchall()
    if len(rows) != 1:
        raise RuntimeError("Exactly one active exchange connection is required for live execution")
    row = rows[0]

    async def _fetch():
        client = await ExchangeService.get_client(*row)
        return await ExchangeService.fetch_balance(client)

    return row[0], asyncio.run(_fetch())


def _get_live_cash_balance(conn, user_id: int) -> float:
    _, balance = _get_live_exchange_balance(conn, user_id)
    available = float((balance.get("free") or {}).get("EUR") or 0)
    if not math.isfinite(available) or available < 0:
        raise RuntimeError("Invalid exchange cash balance")
    return available


def _get_live_asset_eur_price(conn, user_id: int, exchange_name: str, asset: str) -> float:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT api_key, api_secret, api_passphrase FROM exchange_keys
            WHERE user_id=%s AND exchange_name=%s AND is_active=TRUE LIMIT 1
        """, (user_id, exchange_name))
        credentials = cur.fetchone()
    if not credentials:
        raise RuntimeError("Exchange connection unavailable for asset valuation")

    async def _fetch():
        client = await ExchangeService.get_client(exchange_name, *credentials)
        return await ExchangeService.fetch_ticker(client, asset)

    ticker = asyncio.run(_fetch())
    return ExchangeService.verified_eur_ticker_price(ticker, asset)


def _validate_live_auto_order_risk(
    conn, user_id: int, symbol: str, notional: float,
    balance: dict, max_asset_exposure_pct: float,
    bot_id: Optional[int] = None, decision_id: Optional[int] = None,
    exchange_name: Optional[str] = None,
    order_price: Optional[float] = None,
) -> None:
    from backend.services.bot_service import (
        LIVE_MAX_ASSET_EXPOSURE_PCT, LIVE_MAX_PORTFOLIO_EXPOSURE_PCT,
        LIVE_MARKET_PRICE_STALE_AFTER_SECONDS, LIVE_PORTFOLIO_DAILY_LIMIT_EUR,
    )

    with conn.cursor() as cur:
        cur.execute("""
            SELECT COALESCE(SUM(ABS(l.cash_delta_eur)), 0)
            FROM bot_ledger l LEFT JOIN bot_orders o ON o.id=l.order_id AND o.user_id=l.user_id
            WHERE l.user_id=%s
              AND (o.execution_environment='live' OR o.execution_environment IS NULL)
              AND DATE(l.ts)=CURRENT_DATE
              AND l.entry_type='execute' AND l.cash_delta_eur<0
        """, (user_id,))
        today_spent = float(cur.fetchone()[0] or 0)
        cur.execute("""
            SELECT symbol, COALESCE(quote_amount_eur,
                estimated_qty * estimated_price_eur, 0)
            FROM bot_orders WHERE user_id=%s AND execution_environment='live'
              AND side='buy' AND status IN
                ('ready', 'pending', 'sending', 'sent', 'unknown_exchange_state')
              AND (%s IS NULL OR NOT (bot_id=%s AND decision_id=%s))
        """, (user_id, bot_id, bot_id, decision_id))
        pending = [(str(asset).upper(), float(amount or 0)) for asset, amount in cur.fetchall()]
    pending_total = sum(amount for _, amount in pending)
    if not all(math.isfinite(value) and value >= 0 for value in [notional, today_spent, pending_total, *[v for _, v in pending]]):
        raise RuntimeError("Invalid live exposure amount")
    if LIVE_PORTFOLIO_DAILY_LIMIT_EUR > 0 and today_spent + pending_total + notional > LIVE_PORTFOLIO_DAILY_LIMIT_EUR + 0.01:
        raise RuntimeError("Live portfolio daily limit")

    holdings = balance.get("total") if isinstance(balance, dict) else None
    if not isinstance(holdings, dict):
        raise RuntimeError("Exchange balance unavailable for exposure check")
    quantities = {str(asset).upper(): float(qty or 0) for asset, qty in holdings.items()}
    if any(not math.isfinite(qty) or qty < 0 for qty in quantities.values()):
        raise RuntimeError("Invalid exchange balance for exposure check")
    asset_values = {}
    with conn.cursor() as cur:
        def fresh_price(asset: str) -> float:
            cur.execute("""
                SELECT m.price, EXTRACT(EPOCH FROM (NOW() - m.timestamp)) AS age_seconds,
                       a.quote_currency
                FROM market_data m
                LEFT JOIN asset_catalog a ON a.symbol = m.symbol
                WHERE m.symbol=%s AND m.price IS NOT NULL
                ORDER BY m.timestamp DESC LIMIT 1
            """, (asset,))
            market = cur.fetchone()
            if market and market[0] is not None and market[1] is not None:
                price, age_seconds = float(market[0]), float(market[1])
                if (str(market[2] or "").upper() == "EUR" and math.isfinite(price) and price > 0
                        and -60 <= age_seconds <= LIVE_MARKET_PRICE_STALE_AFTER_SECONDS):
                    return price
            if not exchange_name:
                raise RuntimeError("Exchange asset price unavailable for exposure check")
            return _get_live_asset_eur_price(conn, user_id, exchange_name, asset)

        target_price = fresh_price(symbol)
        if order_price is not None:
            # An unattended order must not cross the market after its proposal ages.
            if not exchange_name:
                raise RuntimeError("Exchange quote unavailable for live order price check")
            exchange_price = _get_live_asset_eur_price(conn, user_id, exchange_name, symbol)
            if abs(float(order_price) - exchange_price) / exchange_price > 0.03:
                raise RuntimeError("Live order price deviates from current exchange quote")
            target_price = exchange_price
        for asset, qty in quantities.items():
            if asset == "EUR" or qty <= 1e-12:
                continue
            price = target_price if asset == symbol else fresh_price(asset)
            asset_values[asset] = qty * price

    position_value = sum(asset_values.values())
    equity = quantities.get("EUR", 0) + position_value
    if not math.isfinite(equity) or equity <= 0:
        raise RuntimeError("Exchange equity unavailable for exposure check")
    portfolio_exposure = (position_value + pending_total + notional) / equity * 100
    pending_asset = sum(amount for asset, amount in pending if asset == symbol)
    asset_exposure = (asset_values.get(symbol, 0) + pending_asset + notional) / equity * 100
    if portfolio_exposure > LIVE_MAX_PORTFOLIO_EXPOSURE_PCT or asset_exposure > min(max_asset_exposure_pct, LIVE_MAX_ASSET_EXPOSURE_PCT):
        raise RuntimeError("Live portfolio exposure limit")

def _touch_bot_last_run(conn, *, user_id: int, bot_id: int) -> None:
    """
    Update echte last_run kolom (nieuwe kolom).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE bot_configs
            SET last_run = NOW()
            WHERE user_id = %s
              AND id = %s
            """,
            (user_id, bot_id),
        )


# =====================================================
# 📊 Asset position value (per symbol)
# =====================================================
def get_asset_position_value(
    conn,
    user_id: int,
    bot_id: int,
    symbol: str,
) -> float:
    """
    Returns current EUR value of a specific asset position.
    Used for asset exposure guardrails.
    """

    symbol = (symbol or DEFAULT_SYMBOL).upper()

    with conn.cursor() as cur:

        # current qty
        cur.execute(
            """
            SELECT COALESCE(SUM(qty_delta), 0)
            FROM bot_ledger
            WHERE user_id = %s
              AND bot_id = %s
              AND symbol = %s
            """,
            (user_id, bot_id, symbol),
        )

        qty = float(cur.fetchone()[0] or 0)

        if qty <= 0:
            return 0.0

        # latest market price
        cur.execute(
            """
            SELECT price
            FROM market_data
            WHERE symbol=%s
              AND price IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (symbol,),
        )

        row = cur.fetchone()

        if not row:
            return 0.0

        price = float(row[0] or 0)

    return round(qty * price, 2)


# =====================================================
# ✅ Default trade plan
# =====================================================
def _default_trade_plan(
    symbol: str,
    action: str,
    reason: str = "no_trade_today",
    watch_levels: Optional[dict] = None,
    snapshot: Optional[dict] = None,
) -> dict:
    """
    Hard UI contract:
    - Elke decision heeft een trade_plan
    - Ook observe / hold
    - Als brain geen levels geeft → gebruik snapshot levels
    """

    symbol = (symbol or DEFAULT_SYMBOL).upper()
    side = (action or "observe").lower()

    entry_plan = []
    targets = []
    stop_loss = {"price": None}

    # 1️⃣ Brain watch levels
    if watch_levels:
        pullback = watch_levels.get("pullback_zone")
        breakout = watch_levels.get("breakout_trigger")
        entry = watch_levels.get("entry")

        if pullback:
            entry_plan.append({
                "type": "watch",
                "label": "Observe pullback zone",
                "price": pullback,
            })

        if breakout:
            entry_plan.append({
                "type": "watch",
                "label": "Watch breakout",
                "price": breakout,
            })

        if entry and not entry_plan:
            entry_plan.append({
                "type": "watch",
                "label": "Potential entry",
                "price": entry,
            })

        stop = watch_levels.get("stop_loss")
        if stop:
            stop_loss = {"price": stop}

        watch_targets = watch_levels.get("targets") or []
        for i, t in enumerate(watch_targets):
            if t is not None:
                targets.append({
                    "label": f"TP{i+1}",
                    "price": t,
                })

    # 2️⃣ Snapshot fallback
    if snapshot:
        entry = snapshot.get("entry")
        stop = snapshot.get("stop_loss")
        tps = snapshot.get("targets") or []

        if entry is not None and not entry_plan:
            entry_plan.append({
                "type": "watch",
                "label": "Potential entry",
                "price": entry,
            })

        if stop is not None and stop_loss.get("price") is None:
            stop_loss = {"price": stop}

        if not targets:
            for i, t in enumerate(tps):
                if t is not None:
                    targets.append({
                        "label": f"TP{i+1}",
                        "price": t,
                    })

    return {
        "symbol": symbol,
        "side": side,
        "entry_plan": entry_plan,
        "stop_loss": stop_loss,
        "targets": targets,
        "risk": {
            "rr": None,
            "risk_eur": None,
        },
        "notes": [reason],
    }

# =====================================================
# ✅ Strategy setup payload (from DB) — single truth for bot_brain
# =====================================================
def _hold_for_unconverted_trade_levels(brain: Dict[str, Any], setup_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Never execute against ambiguous or unconverted trade price levels."""
    if setup_payload.get("setup_type") != "trade":
        return brain
    if setup_payload.get("market_price_verified") is False:
        held = dict(brain)
        reason_code = str(setup_payload.get("market_price_reason") or "market_quote_unverified")
        reason = {
            "market_quote_unverified": "De herkomstvaluta van de recente marktprijs is niet bevestigd; de Paper-order wacht op een nieuwe prijs.",
            "market_price_stale": "De marktprijs is te oud voor een Paper-order.",
            "usd_eur_fx_unavailable": "Een recente USD/EUR-koers ontbreekt voor de opgeslagen prijsniveaus.",
            "market_quote_eur_fx_unavailable": "Een recente omrekening van de marktvaluta naar EUR ontbreekt.",
            "trade_quote_sources_out_of_sync": "De prijs en valutakoersen komen niet uit hetzelfde recente tijdvak.",
        }.get(reason_code, "De actuele koersomrekening is niet verifieerbaar; de Paper-order wacht.")
        held.update({"action": "hold", "amount_eur": 0.0, "reason": reason,
                     "guardrail_reason": reason_code,
                     "guardrails_result": {
                         "allowed": False, "adjusted_amount_eur": 0.0,
                         "original_amount_eur": float(brain.get("amount_eur") or 0),
                         "blocked_by": reason_code, "reason": reason,
                         "warnings": [reason_code], "debug_code": reason_code,
                         "explanations": [{"code": reason_code, "message": reason}],
                         "guardrails": {},
                     }})
        return held
    if setup_payload.get("price_currency_confirmed") and (
        setup_payload.get("price_currency") == "EUR" or setup_payload.get("trade_levels_converted")
    ):
        return brain
    held = dict(brain)
    held["action"] = "hold"
    held["amount_eur"] = 0.0
    reason_code = (
        "strategy_price_currency_unconfirmed"
        if not setup_payload.get("price_currency_confirmed")
        else "strategy_price_conversion_unavailable"
    )
    held["reason"] = (
        "Bevestig eerst de valuta van de opgeslagen koersniveaus in de strategie."
        if reason_code == "strategy_price_currency_unconfirmed"
        else "Actuele omrekening van opgeslagen koersniveaus ontbreekt; automatische uitvoering wacht."
    )
    held["guardrail_reason"] = reason_code
    held["guardrails_result"] = {
        "allowed": False, "adjusted_amount_eur": 0.0,
        "original_amount_eur": float(brain.get("amount_eur") or 0),
        "blocked_by": reason_code, "reason": held["reason"],
        "warnings": [reason_code], "debug_code": reason_code,
        "explanations": [{"code": reason_code, "message": held["reason"]}],
        "guardrails": {},
    }
    return held


def _get_strategy_setup_payload(
    conn,
    *,
    user_id: int,
    strategy_id: int,
    setup_id: Optional[int] = None,
    setup_name: Optional[str] = None,
    symbol: Optional[str] = None,
) -> Dict[str, Any]:

    if not _table_exists(conn, "strategies"):
        return {
            "id": setup_id,
            "name": setup_name or "Strategy",
            "symbol": (symbol or DEFAULT_SYMBOL).upper(),
            "base_amount": 0.0,
            "execution_mode": "none",
            "setup_type": "unknown",
        }

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT base_amount, execution_mode, decision_curve, setup_type, data
            FROM strategies
            WHERE id=%s AND user_id=%s
            LIMIT 1
            """,
            (strategy_id, user_id),
        )
        row = cur.fetchone()

    if not row:
        return {
            "id": setup_id,
            "name": setup_name or "Strategy",
            "symbol": (symbol or DEFAULT_SYMBOL).upper(),
            "base_amount": 0.0,
            "execution_mode": "none",
            "setup_type": "unknown",
        }

    base_amount, execution_mode, decision_curve, setup_type, strategy_data = row

    # =====================================================
    # NORMALIZE VALUES
    # =====================================================
    try:
        base_amount = float(base_amount or 0.0)
    except Exception:
        base_amount = 0.0

    execution_mode = (execution_mode or "fixed").lower().strip()
    curve = _safe_json(decision_curve, {}) if decision_curve is not None else {}
    stored_data = _safe_json(strategy_data, {}) if strategy_data is not None else {}

    raw_type = (setup_type or "").lower().strip()

    # =====================================================
    # NORMALIZE TYPE → BOT BRAIN CONTRACT
    # =====================================================
    if raw_type in {"dca", "dca_basic", "dca_smart"}:
        normalized_type = "dca"
    elif raw_type in {"trade", "trading", "manual", "breakout"}:
        normalized_type = "trade"
    else:
        normalized_type = "unknown"

    payload = {
        "id": setup_id,
        "name": setup_name or "Strategy",
        "symbol": (symbol or DEFAULT_SYMBOL).upper(),
        "base_amount": base_amount,
        "execution_mode": execution_mode,
        "setup_type": normalized_type,
        "price_currency": str(stored_data.get("price_currency", "EUR")).upper(),
        "price_currency_confirmed": stored_data.get("price_currency_confirmed") is True,
    }

    if execution_mode == "custom":
        payload["decision_curve"] = curve or {}
    if stored_data.get("dca_amount_semantics") == "planned_exact" and normalized_type == "dca":
        # Preserve malformed historical plans as marked plans so the brain
        # holds them instead of silently treating them as ordinary DCA.
        payload["dca_amount_semantics"] = "planned_exact"
    # The strategy editor stored fixed DCA plans before it wrote the FINN
    # marker. The persisted DCA type, fixed mode and validated amount are the
    # same rule; the linked setup cadence is checked separately before a
    # worker may assess a buy. Do not extend this inference to custom curves.
    amount_rule = {
        **stored_data, "setup_type": normalized_type, "execution_mode": execution_mode,
        "base_amount": base_amount, "decision_curve": curve,
    }
    if normalized_type == "dca" and execution_mode == "fixed" and not curve:
        amount_rule["dca_amount_semantics"] = "planned_exact"
    if is_confirmed_dca_amount_rule(amount_rule):
        payload["dca_amount_semantics"] = "planned_exact"

    return payload

# =====================================================
# 📦 Build setup match (UI CONTRACT)
# =====================================================
def _build_setup_match(
    *,
    bot: Dict[str, Any],
    scores: Dict[str, Any],
    current_match: Dict[str, Any],
) -> Dict[str, Any]:
    """Expose the owner-scoped Score 2.0 match without legacy averaging."""
    status = current_match["status"]
    summary = {
        "matches": "Opgeslagen scorevoorwaarden passen bij de actuele benchmark.",
        "outside_conditions": "Opgeslagen scorevoorwaarden passen nu niet.",
        "insufficient_data": "Actuele benchmarkgegevens zijn niet volledig beschikbaar.",
        "unconfigured": "Deze setup heeft geen scorevoorwaarden.",
    }.get(status, "Setupmatch niet beschikbaar.")
    return {
        "name": current_match.get("name") or bot.get("setup_type") or "Setup",
        "symbol": current_match.get("symbol") or bot.get("symbol", DEFAULT_SYMBOL),
        "timeframe": current_match.get("timeframe") or bot.get("timeframe") or "—",
        "score": current_match["score"],
        "status": status,
        "is_active": current_match["is_active"],
        "summary": summary,
        "detail": " ".join(current_match["reasons"]) or summary,
        "components": current_match["components"],
        "as_of": scores.get("_report_date"),
        "source": "owner_setup_market_match",
        "match_buy": False,
        "match_hold": False,
    }


def _enforce_setup_match_on_buy(
    brain: Dict[str, Any], current_match: Dict[str, Any], setup: Dict[str, Any],
) -> Dict[str, Any]:
    """Keep the bot active, but never buy against measured setup conditions.

    A fixed DCA without score conditions can keep its independent calendar
    policy. Saved score conditions must be measurable before any buy.
    Sell/exit decisions remain available regardless of the match.
    """
    if _normalize_action(brain.get("action")) != "buy":
        return brain
    status = current_match.get("status")
    fixed_calendar_dca = (
        str(setup.get("setup_type") or "").lower() == "dca"
        and setup.get("execution_mode") == "fixed"
    )
    has_score_conditions = bool(current_match.get("conditions"))
    if status == "outside_conditions":
        reason = "Opgeslagen setupvoorwaarden passen niet bij de actuele scores."
    elif status == "unconfigured" and not fixed_calendar_dca:
        reason = "Deze setup heeft geen beoordeelbare scorevoorwaarden."
    elif status == "insufficient_data" and (has_score_conditions or not fixed_calendar_dca):
        reason = "Actuele benchmarkgegevens zijn onvoldoende voor deze aankoop."
    else:
        return brain
    blocked = dict(brain)
    blocked.update(action="hold", amount_eur=0.0, position_size=0.0,
                   execution_position_size=0.0, reason=reason)
    blocked["debug"] = {**(brain.get("debug") or {}), "suggested_amount": 0.0,
                        "setup_match_gate": status}
    return blocked


# =====================================================
# 📦 Actieve bots + strategy context
# =====================================================
def _get_active_bots(conn, user_id: int) -> List[Dict[str, Any]]:
    if not _table_exists(conn, "bot_configs"):
        return []

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              b.id              AS bot_id,
              b.name            AS bot_name,
              b.mode,
              b.is_live,
              b.risk_profile,
              b.strategy_id,
              b.last_run,

              COALESCE(b.budget_total_eur, 0),
              COALESCE(b.budget_daily_limit_eur, 0),
              COALESCE(b.budget_min_order_eur, 0),
              COALESCE(b.budget_max_order_eur, 0),
              COALESCE(b.max_asset_exposure_pct, 100),

              s.setup_type,   -- ✅ FIX
              st.id           AS setup_id,
              st.symbol,
              st.timeframe,
              st.dca_frequency,
              st.dca_day,
              st.dca_month_day,
              st.last_validated

            FROM bot_configs b
            JOIN strategies s ON s.id = b.strategy_id
            JOIN setups st    ON st.id = s.setup_id
            WHERE b.user_id = %s
              AND b.is_active = TRUE
            ORDER BY b.id ASC
            """,
            (user_id,),
        )
        rows = cur.fetchall()

    bots = []
    for r in rows:
        (
            bot_id,
            bot_name,
            mode,
            is_live,
            risk_profile,
            strategy_id,
            last_run,
            budget_total_eur,
            budget_daily_limit_eur,
            budget_min_order_eur,
            budget_max_order_eur,
            max_asset_exposure_pct,
            setup_type,
            setup_id,
            symbol,
            timeframe,
            dca_frequency,
            dca_day,
            dca_month_day,
            setup_last_validated,
        ) = r

        bots.append(
            {
                "bot_id": int(bot_id),
                "bot_name": bot_name,
                "mode": mode,
                "is_live": bool(is_live),
                "risk_profile": risk_profile or "balanced",
                "strategy_id": int(strategy_id),

                # ✅ CONSISTENT
                "setup_type": setup_type,

                "setup_id": setup_id,
                "symbol": (symbol or DEFAULT_SYMBOL).upper(),
                "timeframe": timeframe,
                "dca_frequency": dca_frequency,
                "dca_day": dca_day,
                "dca_month_day": dca_month_day,
                "setup_revision": setup_last_validated.isoformat() if setup_last_validated else None,
                "last_run": last_run.isoformat() if last_run else None,
                "budget": {
                    "total_eur": float(budget_total_eur or 0),
                    "daily_limit_eur": float(budget_daily_limit_eur or 0),
                    "min_order_eur": float(budget_min_order_eur or 0),
                    "max_order_eur": float(budget_max_order_eur or 0),
                    "max_asset_exposure_pct": float(100 if max_asset_exposure_pct is None else max_asset_exposure_pct),
                },
            }
        )

    return bots

# =====================================================
# 📦 Bot Proposal (MARKET_DATA FIXED)
# =====================================================
def build_order_proposal(
    *,
    bot: dict,
    decision: dict,
    today_spent_eur: float,
    total_balance_eur: float,
    live_price: Optional[float],
) -> Optional[dict]:
    """
    Builds a concrete order preview for today.
    Returns None if no order should be proposed.
    """

    if decision.get("action") != "buy":
        return None

    amount_eur = float(decision.get("amount_eur") or 0)
    if amount_eur <= 0:
        return None

    if not live_price:
        logger.warning("⚠️ Geen marktprijs beschikbaar voor berekening order proposal.")
        return None

    symbol = decision.get("symbol", DEFAULT_SYMBOL)

    price_eur = float(live_price)
    estimated_qty = round(amount_eur / price_eur, 8)

    budget = bot.get("budget", {})
    daily_limit = float(budget.get("daily_limit_eur") or 0)
    total_budget = float(budget.get("total_eur") or 0)

    daily_remaining = (
        round(max(0.0, daily_limit - (today_spent_eur + amount_eur)), 2)
        if daily_limit > 0
        else None
    )

    total_remaining = (
        round(max(0.0, total_budget - (total_balance_eur + amount_eur)), 2)
        if total_budget > 0
        else None
    )

    return {
        "symbol": symbol,
        "side": "buy",
        "quote_amount_eur": round(amount_eur, 2),
        "estimated_price": round(price_eur, 2),
        "estimated_qty": estimated_qty,
        "status": "ready",
        "budget_after": {"daily_remaining": daily_remaining, "total_remaining": total_remaining},
    }


# =====================================================
# 📊 Daily scores (single source of truth)
# =====================================================
def _get_daily_scores(conn, user_id: int, report_date: date, symbol: str = "BTC") -> Dict[str, Any]:
    """Read only current, source-verified Score 2.0 components."""
    symbol = (symbol or DEFAULT_SYMBOL).upper()

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT macro_score, technical_score, market_score, calculated_at, indicator_evidence
            FROM daily_scores
            WHERE user_id=%s
              AND report_date=%s
              AND symbol=%s
            LIMIT 1
            """,
            (user_id, report_date, symbol),
        )
        row = cur.fetchone()

    if not row:
        return dict(macro=None, technical=None, market=None, setup=None,
                    _report_date=report_date.isoformat(),
                    _source_available={"macro_score": False, "technical_score": False,
                                       "market_score": False, "setup_score": False})

    macro, technical, market, calculated_at, indicator_evidence = row
    score_row = {"calculated_at": calculated_at, "indicator_evidence": indicator_evidence}

    source_fresh = _benchmark_component_source_freshness(conn, user_id, symbol, score_row)
    verified = {
        "macro": _verified_score(macro) if source_fresh["macro_score"] else None,
        "technical": _verified_score(technical) if source_fresh["technical_score"] else None,
        "market": _verified_score(market) if source_fresh["market_score"] else None,
    }
    return {
        **verified,
        "setup": None,
        "_report_date": report_date.isoformat(),
        "_source_available": {
            "macro_score": verified["macro"] is not None,
            "technical_score": verified["technical"] is not None,
            "market_score": verified["market"] is not None,
            "setup_score": False,
        },
    }


def _benchmark_component_source_freshness(conn, user_id: int, symbol: str, score_row: dict) -> dict[str, bool]:
    """Use the same raw-source freshness rule as FINN and reports."""
    from backend.services.setup_market_match_sync import _fresh

    result: dict[str, bool] = {}
    for category in ("macro", "technical", "market"):
        component = f"{category}_score"
        try:
            result[component] = _fresh(conn, user_id, symbol, category, score_row)
        except Exception:
            logger.exception("Cannot verify %s source freshness", component)
            result[component] = False
    return result


def _get_current_benchmark_weights(conn, user_id: int, symbol: str) -> tuple[dict[str, float] | None, str]:
    """Use the same current Analyse preferences as FINN and My Plan."""
    with conn.cursor() as cur:
        cur.execute("SELECT ai_preferences FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
    if not row:
        return None, "missing_user"
    preferences = _safe_json(row[0], {}) if isinstance(row[0], str) else (row[0] or {})
    if not isinstance(preferences, dict):
        return None, "invalid_preferences"
    custom = preferences.get("intelligence_weights")
    return normalize_benchmark_weights(custom), "user_preferences" if custom else "equal_default"


def _get_saved_setup_conditions(conn, user_id: int, setup_id: int | None) -> dict | None:
    if not setup_id:
        return None
    columns = (
        "id", "name", "symbol", "timeframe", "setup_type",
        "min_benchmark_score", "max_benchmark_score",
    )
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {', '.join(columns)} FROM setups WHERE id=%s AND user_id=%s LIMIT 1",
            (setup_id, user_id),
        )
        row = cur.fetchone()
    return dict(zip(columns, row)) if row else None


# =====================================================
# 📸 Active strategy snapshot (VANDAAG)
# =====================================================
def _get_active_strategy_snapshot(
    conn,
    user_id: int,
    strategy_id: int,
    report_date: date,
) -> Optional[Dict[str, Any]]:
    if not _table_exists(conn, "active_strategy_snapshot"):
        return None

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              entry,
              targets,
              stop_loss,
              confidence_score,
              adjustment_reason
            FROM active_strategy_snapshot
            WHERE user_id=%s
              AND strategy_id=%s
              AND snapshot_date=%s
            LIMIT 1
            """,
            (user_id, strategy_id, report_date),
        )
        row = cur.fetchone()

    if not row:
        return None

    entry, targets_raw, stop_loss, confidence, reason = row

    parsed_targets = []

    if isinstance(targets_raw, str) and targets_raw.strip():
        try:
            parsed = json.loads(targets_raw)
            if isinstance(parsed, list):
                parsed_targets = [
                    float(t) for t in parsed
                    if t is not None
                ]
        except Exception:
            try:
                parsed_targets = [
                    float(t.strip())
                    for t in targets_raw.split(",")
                    if t and t.strip()
                ]
            except Exception:
                parsed_targets = []

    elif isinstance(targets_raw, list):
        parsed_targets = [
            float(t) for t in targets_raw
            if t is not None
        ]

    return {
        "entry": float(entry) if entry is not None else None,
        "targets": parsed_targets,
        "stop_loss": float(stop_loss) if stop_loss is not None else None,
        "confidence": float(confidence or 0),
        "reason": reason,
    }


def _get_saved_strategy_plan(conn, user_id: int, strategy_id: int, match_score: Optional[float]) -> Optional[Dict[str, Any]]:
    """Use the confirmed owner strategy instead of a separately generated AI snapshot."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.entry, s.targets, s.stop_loss
            FROM strategies s
            JOIN setups st ON st.id = s.setup_id AND st.user_id = s.user_id
            WHERE s.id = %s AND s.user_id = %s
            LIMIT 1
            """,
            (strategy_id, user_id),
        )
        row = cur.fetchone()
    if not row:
        return None
    entry, raw_targets, stop_loss = row
    if isinstance(raw_targets, str):
        raw_targets = _safe_json(raw_targets, raw_targets.split(","))
    targets = []
    for value in raw_targets or []:
        try:
            targets.append(float(value))
        except (TypeError, ValueError):
            continue
    try:
        entry_value = float(entry) if entry is not None else None
        stop_value = float(stop_loss) if stop_loss is not None else None
    except (TypeError, ValueError):
        return None
    return {
        "entry": entry_value,
        "targets": targets,
        "stop_loss": stop_value,
        "confidence": None,
        "reason": (
            "saved_strategy_setup_match_is_eligibility_only"
        ),
    }

# =====================================================
# 📸 BOT BUDGET
# =====================================================
def check_bot_budget(
    *,
    bot_config: dict,
    today_spent_eur: float,
    proposed_amount_eur: float,
):
    budget = bot_config.get("budget") or {}

    daily_limit_eur = float(budget.get("daily_limit_eur") or 0)
    min_order_eur = float(budget.get("min_order_eur") or 0)
    max_order_eur = float(budget.get("max_order_eur") or 0)

    if proposed_amount_eur <= 0:
        return True, None

    if daily_limit_eur > 0 and (today_spent_eur + proposed_amount_eur) > daily_limit_eur:
        return False, "Daglimiet overschreden"

    if min_order_eur > 0 and proposed_amount_eur < min_order_eur:
        return False, "Onder minimum orderbedrag"

    if max_order_eur > 0 and proposed_amount_eur > max_order_eur:
        return False, "Boven maximum orderbedrag"

    return True, None


# =====================================================
# 📸 BOT TODAY SPENT
# =====================================================
def get_today_spent_eur(
    conn,
    user_id: int,
    bot_id: int,
    report_date: date,
) -> float:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(SUM(ABS(cash_delta_eur)), 0)
            FROM bot_ledger
            WHERE user_id = %s
              AND bot_id = %s
              AND entry_type = 'execute'
              AND cash_delta_eur < 0
              AND DATE(ts) = %s
            """,
            (user_id, bot_id, report_date),
        )
        return float(cur.fetchone()[0] or 0.0)


# =====================================================
# 📸 BOT RECORD LEDGER
# =====================================================
def record_bot_ledger_entry(
    *,
    conn,
    user_id: int,
    bot_id: int,
    entry_type: str,
    cash_delta_eur: float = 0.0,
    qty_delta: float = 0.0,
    price_eur: Optional[float] = None,
    symbol: str = DEFAULT_SYMBOL,
    decision_id: Optional[int] = None,
    order_id: Optional[int] = None,
    note: Optional[str] = None,
    meta: Optional[dict] = None,
    fill_sequence: int = 0,
    valuation_version: int = 1,
):
    with conn.cursor() as cur:
        # 1. Insert Ledger
        cur.execute(
            """
            INSERT INTO bot_ledger (
                user_id, bot_id, decision_id, order_id, entry_type,
                symbol, cash_delta_eur, qty_delta, price_eur, note, meta,
                fill_sequence, valuation_version, ts
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            ON CONFLICT (user_id, order_id, entry_type, fill_sequence)
            WHERE entry_type = 'execute' AND order_id IS NOT NULL
            DO NOTHING
            RETURNING id
            """,
            (
                user_id,
                bot_id,
                decision_id,
                order_id,
                entry_type,
                symbol,
                cash_delta_eur,
                qty_delta,
                price_eur,
                note,
                json.dumps(meta or {}),
                fill_sequence,
                valuation_version,
            ),
        )
        inserted = cur.fetchone()
        if inserted is None:
            return False

        # 2. Update Portfolio State (only for 'execute' type)
        if entry_type == "execute":
            cur.execute("""
                INSERT INTO bot_portfolios (user_id, bot_id, symbol, cash_eur, position_qty, invested_eur, avg_entry, realized_pnl_eur, updated_at)
                SELECT 
                    %s, %s, %s, %s, %s,
                    CASE WHEN %s > 0 THEN ABS(%s) ELSE 0 END,
                    CASE WHEN %s > 0 THEN ABS(%s) / %s ELSE 0 END,
                    0, NOW()
                ON CONFLICT (bot_id, symbol) DO UPDATE SET
                    cash_eur = bot_portfolios.cash_eur + EXCLUDED.cash_eur,
                    realized_pnl_eur = bot_portfolios.realized_pnl_eur + (
                        CASE 
                            WHEN EXCLUDED.position_qty < 0 AND bot_portfolios.position_qty > 0 THEN
                                ABS(EXCLUDED.cash_eur) - (ABS(EXCLUDED.position_qty) / bot_portfolios.position_qty * bot_portfolios.invested_eur)
                            ELSE 0 
                        END
                    ),
                    invested_eur = (
                        CASE 
                            WHEN EXCLUDED.position_qty > 0 THEN bot_portfolios.invested_eur + ABS(EXCLUDED.cash_eur)
                            WHEN EXCLUDED.position_qty < 0 AND bot_portfolios.position_qty > 0 THEN
                                bot_portfolios.invested_eur - (ABS(EXCLUDED.position_qty) / bot_portfolios.position_qty * bot_portfolios.invested_eur)
                            ELSE bot_portfolios.invested_eur
                        END
                    ),
                    position_qty = bot_portfolios.position_qty + EXCLUDED.position_qty,
                    avg_entry = (
                        CASE 
                            WHEN (bot_portfolios.position_qty + EXCLUDED.position_qty) > 0 THEN
                                (
                                    CASE 
                                        WHEN EXCLUDED.position_qty > 0 THEN bot_portfolios.invested_eur + ABS(EXCLUDED.cash_eur)
                                        ELSE bot_portfolios.invested_eur - (ABS(EXCLUDED.position_qty) / bot_portfolios.position_qty * bot_portfolios.invested_eur)
                                    END
                                ) / (bot_portfolios.position_qty + EXCLUDED.position_qty)
                            ELSE 0
                        END
                    ),
                    updated_at = NOW();
            """, (
                user_id, bot_id, symbol, cash_delta_eur, qty_delta,
                qty_delta, cash_delta_eur,
                qty_delta, cash_delta_eur, qty_delta
            ))
    return True


def _claim_bot_decision_for_execution(
    *,
    conn,
    user_id: int,
    bot_id: int,
    decision_id: int,
    executed_by: str,
) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE bot_decisions
            SET status='executing',
                executed_by=%s,
                updated_at=NOW()
            WHERE id=%s
              AND user_id=%s
              AND bot_id=%s
              AND status='planned'
            RETURNING id
            """,
            (executed_by, decision_id, user_id, bot_id),
        )
        claimed = cur.fetchone() is not None
        if not claimed:
            increment_execution_safety_counter("replay_block_hits")
        return claimed


def _mark_bot_decision_execution_failed(
    *,
    conn,
    user_id: int,
    bot_id: int,
    decision_id: int,
    reason: Optional[str] = None,
):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE bot_decisions
            SET status='failed_execution',
                scores_json=jsonb_set(COALESCE(scores_json, '{}'::jsonb),
                    '{execution_failure}', %s::jsonb, true),
                reason_json=COALESCE(reason_json, '[]'::jsonb) || jsonb_build_array(%s::text),
                updated_at=NOW()
            WHERE id=%s
              AND user_id=%s
              AND bot_id=%s
              AND status IN ('executing', 'planned')
            """,
            (json.dumps(reason or "De order kon niet veilig worden uitgevoerd. Controleer de bot en probeer opnieuw."),
             reason or "De order kon niet veilig worden uitgevoerd. Controleer de bot en probeer opnieuw.",
             decision_id, user_id, bot_id),
        )
        cur.execute("""
            UPDATE bot_orders SET status='failed', updated_at=NOW()
            WHERE user_id=%s AND bot_id=%s AND decision_id=%s
              AND status IN ('ready', 'pending', 'approved')
        """, (user_id, bot_id, decision_id))
        cur.execute("""
            UPDATE bot_executions e SET status='failed', updated_at=NOW()
            FROM bot_orders o
            WHERE e.bot_order_id=o.id AND e.user_id=%s
              AND o.user_id=%s AND o.bot_id=%s AND o.decision_id=%s
              AND o.status='failed' AND e.status='pending'
        """, (user_id, user_id, bot_id, decision_id))


def _require_current_setup_revision_for_buy(
    *, conn, user_id: int, bot_id: int, decision_id: int,
) -> None:
    """Recheck the exact owner setup used by a planned buy before execution.

    The row locks keep a concurrent plan edit or bot relink from overtaking
    this check before the Paper ledger write or live exchange call.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT d.setup_id, d.strategy_id, d.scores_json->>'setup_revision',
                   d.scores_json ? 'setup_revision',
                   b.strategy_id, s.setup_id, st.last_validated
            FROM bot_decisions d
            JOIN bot_configs b ON b.id=d.bot_id AND b.user_id=d.user_id
            JOIN strategies s ON s.id=b.strategy_id AND s.user_id=d.user_id
            JOIN setups st ON st.id=s.setup_id AND st.user_id=d.user_id
            WHERE d.id=%s AND d.user_id=%s AND d.bot_id=%s
            FOR SHARE OF b, s, st
            """,
            (decision_id, user_id, bot_id),
        )
        row = cur.fetchone()
    if not row:
        raise RuntimeError("Bot plan is no longer available")
    decision_setup_id, decision_strategy_id, recorded_revision, has_revision, strategy_id, setup_id, current = row
    current_revision = current.isoformat() if current else None
    if (
        decision_setup_id != setup_id
        or decision_strategy_id != strategy_id
        or not has_revision
        or recorded_revision != current_revision
    ):
        raise RuntimeError("Bot plan changed since this decision; evaluate it again")


# =====================================================
# 📸 BOT BALANCE
# =====================================================
def get_bot_balance(conn, user_id: int, bot_id: int) -> float:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(SUM(cash_delta_eur), 0)
            FROM bot_ledger
            WHERE user_id = %s
              AND bot_id = %s
            """,
            (user_id, bot_id),
        )
        return float(cur.fetchone()[0] or 0.0)

def get_bot_portfolio_state(conn, user_id: int, bot_id: int, symbol: str) -> Dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT cash_eur, position_qty, invested_eur, realized_pnl_eur
            FROM bot_portfolios
            WHERE user_id = %s AND bot_id = %s AND symbol = %s
            """,
            (user_id, bot_id, (symbol or "BTC").upper()),
        )
        row = cur.fetchone()
        if not row:
            return {"cash": 0.0, "qty": 0.0, "invested": 0.0, "realized": 0.0}
        return {
            "cash": float(row[0] or 0.0),
            "qty": float(row[1] or 0.0),
            "invested": float(row[2] or 0.0),
            "realized": float(row[3] or 0.0),
        }


# =====================================================
# Persist bot order
# =====================================================
def _persist_bot_order(
    *,
    conn,
    user_id: int,
    bot_id: int,
    decision_id: int,
    order: dict,
    is_live: bool = False,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO bot_orders (
                user_id,
                bot_id,
                decision_id,
                symbol,
                side,
                order_type,
                quote_amount_eur,
                estimated_price_eur,
                estimated_qty,
                execution_environment,
                status,
                created_at,
                updated_at
            )
            VALUES (
                %s,%s,%s,
                %s,%s,
                'market',
                %s,%s,%s,
                %s,
                'ready',
                NOW(), NOW()
            )
            RETURNING id
            """,
            (
                user_id,
                bot_id,
                decision_id,
                order["symbol"],
                order["side"],
                order["quote_amount_eur"],
                order["estimated_price"],
                order["estimated_qty"],
                "live" if is_live else "paper",
            ),
        )
        bot_order_id = int(cur.fetchone()[0])

        cur.execute(
            """
            INSERT INTO bot_executions (
                user_id,
                bot_order_id,
                status,
                created_at,
                updated_at
            )
            VALUES (%s, %s, 'pending', NOW(), NOW())
            ON CONFLICT (user_id, bot_order_id) DO UPDATE SET
                status = EXCLUDED.status,
                updated_at = NOW()
            """,
            (user_id, bot_order_id),
        )

        return bot_order_id

# =====================================================
# 🧱 Build Trade Plan from snapshot + brain
# =====================================================
def _build_trade_plan(
    *,
    symbol: str,
    action: str,
    snapshot: Optional[Dict[str, Any]],
    brain: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Creates structured execution plan.

    Used for:
    - TradePlanCard UI
    - paper trading
    - TP hit detection
    - pyramiding engine
    - exchange execution
    """

    if not snapshot:
        return None

    entry = snapshot.get("entry")
    stop = snapshot.get("stop_loss")
    targets = snapshot.get("targets") or []

    if not entry and not targets:
        return None

    rr = None
    if brain:
        rr = brain.get("rr_ratio") or brain.get("rr")

    return {
        "symbol": symbol,
        "side": action,
        "entry_plan": [{"type": "limit", "price": entry}] if entry else [],
        "stop_loss": {"price": stop} if stop else None,
        "targets": [
            {"label": f"TP{i+1}", "price": t}
            for i, t in enumerate(targets)
        ],
        "risk": {
            "rr": rr,
        },
    }


# =====================================================
# Persist trade plan
# =====================================================
def _persist_trade_plan(
    *,
    conn,
    user_id: int,
    bot_id: int,
    decision_id: int,
    symbol: str,
    side: str,
    plan: dict,
):
    """
    Store structured trade plan for execution & UI.

    HARD CONTRACT:
    - trade_plan bestaat altijd
    - ook voor observe/hold
    """

    if not plan:
        return

    symbol = (symbol or DEFAULT_SYMBOL).upper()
    side = (side or "observe").lower()

    entry_plan = plan.get("entry_plan") or []
    stop_loss = plan.get("stop_loss") or {"price": None}
    targets = plan.get("targets") or []
    risk = plan.get("risk") or {}

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO bot_trade_plans (
                user_id,
                bot_id,
                decision_id,
                symbol,
                side,
                entry_plan,
                stop_loss,
                targets,
                risk_json,
                status,
                created_at,
                updated_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'planned',NOW(),NOW())
            ON CONFLICT (decision_id)
            DO UPDATE SET
                entry_plan = EXCLUDED.entry_plan,
                stop_loss  = EXCLUDED.stop_loss,
                targets    = EXCLUDED.targets,
                risk_json  = EXCLUDED.risk_json,
                status     = 'planned',
                updated_at = NOW()
        """, (
            user_id,
            bot_id,
            decision_id,
            symbol,
            side,
            json.dumps(entry_plan),
            json.dumps(stop_loss),
            json.dumps(targets),
            json.dumps(risk),
        ))


# =====================================================
# Persist decision
# =====================================================
def _persist_decision_and_order(
    *,
    conn,
    user_id: int,
    bot_id: int,
    strategy_id: int,
    setup_id: Optional[int],
    report_date: date,
    decision: Dict[str, Any],
    scores: Dict[str, Any],
    setup_revision: Optional[str] = None,
) -> int:

    action = _normalize_action(decision.get("action"))
    confidence = _normalize_confidence(decision.get("confidence") or "low")
    symbol = (decision.get("symbol") or DEFAULT_SYMBOL).upper()

    amount_eur = float(decision.get("amount_eur") or 0.0)

    if action == "buy" and setup_id is not None:
        # A worker can read a setup before an owner edits it and only persist
        # the result afterwards. Lock the current setup row and reject that
        # obsolete buy before a ready order can be created.
        with conn.cursor() as cur:
            cur.execute(
                "SELECT last_validated FROM setups WHERE id=%s AND user_id=%s FOR SHARE",
                (setup_id, user_id),
            )
            row = cur.fetchone()
        current_revision = row[0].isoformat() if row and row[0] else None
        if not row or current_revision != setup_revision:
            raise RuntimeError("Setup changed during bot assessment")

    metrics = decision.get("metrics") or {}
    availability = scores.get("_source_available") or {}
    verified_components = {
        category: (
            _verified_score(scores.get(category))
            if availability.get(f"{category}_score") is True else None
        ) for category in ("macro", "technical", "market")
    }

    scores_payload = {
        "score_semantics": "verified_score_2",
        "setup_revision": setup_revision,
        **verified_components,
        "setup": (scores.get("_setup_match") or {}).get("score"),
        "setup_match": decision.get("setup_match"),
        "decision_basis": decision.get("decision_basis"),

        "combined": benchmark_score(
            {f"{category}_score": verified_components[category]
             for category in ("macro", "technical", "market")},
            scores.get("_benchmark_weights") or {},
            availability,
        ),

        "regime": decision.get("regime"),
        "risk_state": decision.get("risk_state"),

        "market_pressure": metrics.get("market_pressure"),
        "transition_risk": metrics.get("transition_risk"),

        "position_size": decision.get("position_size"),
        "amount_eur": amount_eur,

        "trade_plan": decision.get("trade_plan"),
        "strategy_reason": decision.get("strategy_reason"),
        "guardrail_reason": decision.get("guardrail_reason"),
        "guardrails_result": decision.get("guardrails_result"),
        "guardrails_checked_at": datetime.now(timezone.utc).isoformat() if decision.get("guardrails_result") else None,
        "watch_levels": decision.get("watch_levels"),
        "monitoring": decision.get("monitoring"),
        "alerts_active": decision.get("alerts_active"),
    }
    if decision.get("dca_amount_semantics") == "planned_exact":
        source = decision.get("score_source")
        components = {
            f"{category}_score": verified_components[category]
            for category in ("market", "macro", "technical")
        }
        weights = scores.get("_benchmark_weights") or {}
        combined = (
            benchmark_score(components, weights, availability)
            if source == "benchmark_score" else None
        )
        available = (
            combined is not None if source == "benchmark_score"
            else (False if source else None)
        )
        scores_payload["dca_policy"] = {
            "score_source": source,
            "source_available": available,
            "source_score": combined,
            "weights": weights if source == "benchmark_score" else None,
            "weight_source": scores.get("_benchmark_weight_source") if source == "benchmark_score" else None,
            "components": components if source == "benchmark_score" and available else None,
            "planned_amount_eur": decision.get("requested_amount_eur"),
            "applied_amount_eur": amount_eur,
        }

    guardrail_result = decision.get("guardrails_result") or {}
    reasons = [
        item.get("message") for item in guardrail_result.get("explanations", [])
        if isinstance(item, dict) and item.get("message")
    ]
    if not reasons and guardrail_result.get("blocked_by") and guardrail_result.get("reason"):
        reasons.append(guardrail_result["reason"])
    if decision.get("strategy_reason"):
        reasons.append(decision["strategy_reason"])

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO bot_decisions (
                user_id,
                bot_id,
                strategy_id,
                setup_id,
                symbol,
                decision_date,
                decision_ts,
                action,
                confidence,
                amount_eur,
                scores_json,
                reason_json,
                status,
                created_at,
                updated_at
            )
            VALUES (
                %s,%s,%s,%s,
                %s,%s,
                NOW(),
                %s,%s,%s,
                %s::jsonb,
                %s::jsonb,
                'planned',
                NOW(), NOW()
            )
            ON CONFLICT (user_id, bot_id, decision_date) DO UPDATE SET
                strategy_id = EXCLUDED.strategy_id,
                setup_id = EXCLUDED.setup_id,
                symbol = EXCLUDED.symbol,
                decision_ts = EXCLUDED.decision_ts,
                action = EXCLUDED.action,
                confidence = EXCLUDED.confidence,
                amount_eur = EXCLUDED.amount_eur,
                scores_json = EXCLUDED.scores_json,
                reason_json = EXCLUDED.reason_json,
                status = EXCLUDED.status,
                updated_at = NOW()
            WHERE bot_decisions.status NOT IN ('executed', 'executing')
            RETURNING id
            """,
            (
                user_id,
                bot_id,
                strategy_id,
                setup_id,
                symbol,
                report_date,
                action,
                confidence,
                amount_eur,
                json.dumps(scores_payload),
                json.dumps(reasons),
            ),
        )

        persisted = cur.fetchone()
        if persisted is None:
            # A concurrent manual execution may have completed after the
            # assessment began. Never turn its decision back into a proposal.
            return None
        decision_id = int(persisted[0])

    _persist_trade_plan(
        conn=conn,
        user_id=user_id,
        bot_id=bot_id,
        decision_id=decision_id,
        symbol=symbol,
        side=action,
        plan=decision.get("trade_plan"),
    )

    return decision_id
    
# =====================================================
# 🚀 Run Trading Bot Agent
# =====================================================
def run_trading_bot_execution(
    user_id: int,
    report_date: Optional[date] = None,
    bot_id: Optional[int] = None,
    paper_only: bool = False,
) -> Dict[str, Any]:

    report_date = report_date or date.today()

    conn = get_db_connection()
    if not conn:
        return {"ok": False, "error": "db_unavailable"}

    try:
        bots = _get_active_bots(conn, user_id)

        if bot_id is not None:
            bots = [b for b in bots if b["bot_id"] == bot_id]
        if paper_only:
            if any(b.get("is_live") for b in bots):
                return {"ok": False, "error": "paper_mode_changed"}

        if not bots:
            if paper_only:
                return {"ok": False, "error": "paper_mode_changed"}
            return {
                "ok": True,
                "date": str(report_date),
                "bots": 0,
                "decisions": [],
                "bot_ids": [],
            }


        results = []
        skip_reasons = {}
        touched_bot_ids = []
        price_cache = {}

        for bot in bots:

            if bot.get("is_live"):
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT 1 FROM bot_orders
                        WHERE user_id=%s AND bot_id=%s
                          AND execution_environment='live'
                          AND status IN ('ready', 'pending', 'sending', 'sent', 'unknown_exchange_state')
                        LIMIT 1
                    """, (user_id, bot["bot_id"]))
                    if cur.fetchone():
                        logger.warning("Skipping bot %s while a live order is unresolved", bot["bot_id"])
                        continue
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT status FROM bot_decisions
                        WHERE user_id=%s AND bot_id=%s AND decision_date=%s
                        ORDER BY id DESC LIMIT 1
                    """, (user_id, bot["bot_id"], report_date))
                    prior_decision = cur.fetchone()
                if prior_decision and prior_decision[0] in {
                    "executed", "skipped", "executing", "awaiting_exchange", "unknown_exchange_state"
                }:
                    continue

            # =========================
            # SYMBOL
            # =========================
            symbol = (bot.get("symbol") or DEFAULT_SYMBOL).upper()

            # =========================
            # SCORES (SYMBOL SPECIFIC)
            # =========================
            scores = _get_daily_scores(conn, user_id, report_date, symbol)

            # =========================
            # LIVE PRICE (CACHED)
            # =========================
            price_key = (symbol, bool(bot.get("is_live")))
            if price_key not in price_cache:
                if bot.get("is_live"):
                    from backend.services.bot_service import LIVE_MARKET_PRICE_STALE_AFTER_SECONDS
                    live_price = _get_live_price(
                        conn, symbol, max_age_seconds=LIVE_MARKET_PRICE_STALE_AFTER_SECONDS,
                    )
                    if live_price is None:
                        try:
                            exchange_name, _ = _get_live_exchange_balance(conn, user_id)
                            live_price = _get_live_asset_eur_price(conn, user_id, exchange_name, symbol)
                        except Exception:
                            logger.warning("Verified live EUR price unavailable for %s", symbol)
                    price_cache[price_key] = live_price
                else:
                    price_cache[price_key] = _get_live_price(conn, symbol)
            live_price = price_cache[price_key]

            # =========================
            # SNAPSHOT
            # =========================
            snapshot = None

            # =========================
            # SETUP PAYLOAD
            # =========================
            setup_payload = _get_strategy_setup_payload(
                conn,
                user_id=user_id,
                strategy_id=bot["strategy_id"],
                setup_id=bot.get("setup_id"),
                setup_name=bot.get("setup_type"),
                symbol=symbol,
            )
            if setup_payload.get("symbol") and setup_payload["symbol"].upper() != symbol:
                logger.warning("Bot %s asset differs from linked strategy; skipping decision", bot["bot_id"])
                continue
            try:
                scores["_benchmark_weights"], scores["_benchmark_weight_source"] = _get_current_benchmark_weights(conn, user_id, symbol)
            except Exception:
                logger.exception("Analyse weights unavailable for user_id=%s", user_id)
                scores["_benchmark_weights"] = None
                scores["_benchmark_weight_source"] = "unavailable"
            saved_setup = _get_saved_setup_conditions(conn, user_id, bot.get("setup_id"))
            if saved_setup and str(saved_setup.get("symbol") or "").upper() == symbol:
                current_match = match_setup_from_daily_scores(saved_setup, scores, scores.get("_benchmark_weights"))
            else:
                current_match = match_setup_from_daily_scores({}, scores, scores.get("_benchmark_weights"))
            scores["_setup_match"] = current_match
            if setup_payload.get("setup_type") == "trade":
                setup_payload["saved_trade_match_status"] = (
                    current_match.get("status") if not bot.get("is_live") else None
                )
                # The saved score band is the Paper trade signal. Live orders
                # retain their existing independent confidence policy.
                setup_payload["confirmed_trade_match"] = (
                    not bot.get("is_live") and current_match.get("status") == "matches"
                )
            snapshot = _get_saved_strategy_plan(
                conn, user_id, bot["strategy_id"], current_match.get("score"),
            )
            # A missing match has no sizing effect. Only measured matches may
            # influence sizing; no synthetic neutral score is recorded.
            scores["setup"] = current_match["score"]
            scores["_source_available"]["setup_score"] = current_match["score"] is not None

            if setup_payload.get("dca_amount_semantics") == "planned_exact":
                from backend.domain.finn_dca_plan_contract import dca_due_on_date

                if not dca_due_on_date(bot, report_date):
                    skip_reasons[bot["bot_id"]] = "not_due"
                    continue
                with conn.cursor() as cur:
                    # Serialize runs for this owner and bot until the paper
                    # decision and order commit. A second worker must observe
                    # the first execution before considering another buy.
                    cur.execute(
                        "SELECT pg_advisory_xact_lock(%s, %s)",
                        (user_id, bot["bot_id"]),
                    )
                    cur.execute(
                        """SELECT 1 FROM bot_decisions
                           WHERE user_id=%s AND bot_id=%s AND decision_date=%s
                             AND status='executed' LIMIT 1""",
                        (user_id, bot["bot_id"], report_date),
                    )
                    if cur.fetchone():
                        skip_reasons[bot["bot_id"]] = "already_executed"
                        continue

            if setup_payload.get("symbol"):
                symbol = setup_payload.get("symbol").upper()

            if snapshot:
                setup_payload.update({
                    "entry": snapshot.get("entry"),
                    "stop_loss": snapshot.get("stop_loss"),
                    "targets": snapshot.get("targets"),
                })

            trade_fx_context = None
            source_trade_levels = None
            if setup_payload.get("setup_type") == "trade":
                trade_fx_context = _get_trade_quote_fx_context(
                    conn, symbol, require_usd=setup_payload.get("price_currency") == "USD",
                )
                setup_payload["market_quote_currency"] = trade_fx_context["quote_currency"]
                if not bot.get("is_live"):
                    live_price = trade_fx_context.get("live_price_eur")
                    setup_payload["market_price_verified"] = live_price is not None
                    setup_payload["market_price_reason"] = trade_fx_context.get("reason")
                if setup_payload.get("price_currency") == "USD" and snapshot:
                    factor = trade_fx_context.get("eur_per_unit")
                    if (not bot.get("is_live") and setup_payload.get("price_currency_confirmed") and
                            trade_fx_context.get("quote_currency") in {"USD", "USDT", "EUR"}
                            and factor and live_price is not None):
                        source_trade_levels = dict(snapshot)
                        snapshot = _convert_trade_snapshot_to_eur(snapshot, factor)
                        setup_payload.update({
                            "entry": snapshot["entry"], "stop_loss": snapshot["stop_loss"],
                            "targets": snapshot["targets"], "trade_levels_converted": True,
                        })

            # =========================
            # PORTFOLIO CONTEXT (ACCURATE)
            # =========================
            portfolio_state = get_bot_portfolio_state(conn, user_id, bot["bot_id"], symbol)
            
            today_spent_eur = get_today_spent_eur(
                conn,
                user_id,
                bot["bot_id"],
                report_date,
            )

            # Use values from bot_portfolios (the new source of truth)
            cash_balance_eur = portfolio_state["cash"]
            live_cash_error = None
            if bot.get("is_live"):
                try:
                    cash_balance_eur = _get_live_cash_balance(conn, user_id)
                except Exception:
                    live_cash_error = "cash_unavailable"
                    cash_balance_eur = 0.0
            current_qty = portfolio_state["qty"]
            invested_eur = portfolio_state["invested"]

            current_asset_value_eur = current_qty * (live_price or 0)

            # True equity = Cash + Assets
            portfolio_value_eur = cash_balance_eur + current_asset_value_eur

            portfolio_context = {
                "today_allocated_eur": today_spent_eur,
                "portfolio_value_eur": portfolio_value_eur,
                "current_asset_value_eur": current_asset_value_eur,
                "cash_balance_eur": cash_balance_eur,
                "invested_eur": invested_eur,
                "max_trade_risk_eur": bot["budget"].get("max_order_eur"),
                "daily_allocation_eur": bot["budget"].get("daily_limit_eur"),
                "max_asset_exposure_pct": bot["budget"].get("max_asset_exposure_pct"),
                "total_budget_eur": bot["budget"].get("total_eur"),
                "min_order_eur": bot["budget"].get("min_order_eur"),
                "kill_switch": True,
                "live_price": live_price,
                "active_strategy": snapshot,
            }

            # =========================
            # BOT BRAIN
            # =========================
            brain = run_bot_brain(
                user_id=user_id,
                setup=setup_payload,
                scores={
                    "macro_score": scores.get("macro"),
                    "technical_score": scores.get("technical"),
                    "market_score": scores.get("market"),
                    "setup_score": scores.get("setup"),
                    "_source_available": scores.get("_source_available"),
                    "_benchmark_weights": scores.get("_benchmark_weights"),
                },
                portfolio_context=portfolio_context,
            )
            brain = _enforce_setup_match_on_buy(brain, current_match, setup_payload)

            # All comparisons and sizing now use EUR. Ambiguous old levels or
            # a missing dated FX rate still fail closed before an order.
            brain = _hold_for_unconverted_trade_levels(brain, setup_payload)

            if live_cash_error or (bot.get("is_live") and live_price is None):
                reason_code = live_cash_error or "market_price_stale"
                original = float((brain.get("guardrails_result") or {}).get("original_amount_eur") or 0)
                brain["guardrails_result"] = {
                    "allowed": False, "adjusted_amount_eur": 0.0,
                    "original_amount_eur": original, "blocked_by": reason_code,
                    "reason": "Live kassaldo of actuele EUR-marktprijs is niet bevestigd.",
                    "warnings": [reason_code], "debug_code": reason_code, "guardrails": {},
                }
                brain["guardrail_reason"] = reason_code
                brain["amount_eur"] = 0.0
                brain["action"] = "hold"

            action = _normalize_action(brain.get("action"))

            # =========================
            # SETUP MATCH
            # =========================
            setup_match = _build_setup_match(
                bot=bot,
                scores=scores,
                current_match=scores["_setup_match"],
            )

            # =========================
            # TRADE PLAN (fallback safe)
            # =========================
            trade_plan = brain.get("trade_plan")

            if not trade_plan or not isinstance(trade_plan, dict):
                trade_plan = _default_trade_plan(
                    symbol=symbol,
                    action=action,
                    reason="fallback_trade_plan",
                    snapshot=snapshot,
                )
            if setup_payload.get("setup_type") == "trade" and isinstance(trade_plan, dict):
                trade_plan["price_currency"] = (
                    "EUR" if setup_payload.get("trade_levels_converted") else setup_payload.get("price_currency")
                )
                if snapshot:
                    original_levels = source_trade_levels or snapshot
                    trade_plan["source_price_currency"] = setup_payload.get("price_currency")
                    trade_plan["source_levels"] = {
                        key: original_levels.get(key) for key in ("entry", "stop_loss", "targets")
                    }
                    trade_plan["market_quote_currency"] = trade_fx_context["quote_currency"]
                    trade_plan["quote_check_reason"] = trade_fx_context.get("reason")
                    if trade_fx_context.get("live_price_eur") is not None:
                        trade_plan["market_price"] = trade_fx_context["market_price"]
                        trade_plan["market_price_as_of"] = trade_fx_context["market_price_at"].isoformat()
                        trade_plan["market_fx_eur_per_unit"] = trade_fx_context["market_fx_eur_per_unit"]
                        market_fx_at = trade_fx_context.get("market_fx_as_of")
                        trade_plan["market_fx_as_of"] = market_fx_at.isoformat() if market_fx_at else None
                        trade_plan["fx_eur_per_unit"] = trade_fx_context["eur_per_unit"]
                        fx_at = trade_fx_context.get("fx_as_of")
                        trade_plan["fx_as_of"] = fx_at.isoformat() if fx_at else None

            # =========================
            # POSITION SIZE
            # =========================
            raw_position_size = brain.get("position_size")
            if raw_position_size is None:
                raw_position_size = brain.get("metrics", {}).get("position_size", 0.0)

            position_size = float(raw_position_size)
            position_size = max(0.0, min(position_size, 1.0))

            # =========================
            # METRICS
            # =========================
            metrics = brain.get("metrics") or {}

            # =========================
            # DECISION
            # =========================
            decision = {
                "bot_id": bot["bot_id"],
                "symbol": symbol,

                "action": action,
                "confidence": _map_confidence(float(brain.get("confidence") or 0.0)),
                "status": "planned",

                "amount_eur": round(float(brain.get("amount_eur") or 0), 2),
                "requested_amount_eur": round(
                    float(brain.get("debug", {}).get("suggested_amount") or 0), 2
                ),
                "dca_amount_semantics": setup_payload.get("dca_amount_semantics"),
                "score_source": (setup_payload.get("decision_curve") or {}).get("input"),
                "decision_basis": (
                    "saved_setup_score_band" if setup_payload.get("confirmed_trade_match")
                    else None
                ),

                "base_amount": brain.get("base_amount") or setup_payload.get("base_amount"),
                "execution_mode": setup_payload.get("execution_mode"),

                "position_size": round(position_size, 2),
                "exposure_multiplier": float(brain.get("exposure_multiplier") or 1.0),

                # Setup match is a separate Score 2.0 assessment.
                "score": scores["_setup_match"].get("score"),

                "strategy_reason": brain.get("reason"),
                "regime": brain.get("regime"),
                "risk_state": brain.get("risk_state"),

                "market_pressure": metrics.get("market_pressure"),
                "transition_risk": metrics.get("transition_risk"),

                "volatility_state": brain.get("volatility_state"),
                "trend_strength": brain.get("trend_strength"),
                "structure_bias": brain.get("structure_bias"),

                "trade_plan": trade_plan,
                "watch_levels": brain.get("watch_levels"),
                "monitoring": brain.get("monitoring"),
                "alerts_active": brain.get("alerts_active"),

                "guardrails_result": brain.get("guardrails_result"),
                "guardrail_reason": brain.get("guardrail_reason"),

                "setup_match": setup_match,
                "live_price": live_price,

                "metrics": metrics,
            }

            # =========================
            # SAVE DECISION
            # =========================
            decision_id = _persist_decision_and_order(
                conn=conn,
                user_id=user_id,
                bot_id=bot["bot_id"],
                strategy_id=bot["strategy_id"],
                setup_id=bot.get("setup_id"),
                report_date=report_date,
                decision=decision,
                scores=scores,
                setup_revision=bot.get("setup_revision"),
            )
            if decision_id is None:
                continue

            _clear_existing_pending_orders_for_day(
                conn=conn,
                user_id=user_id,
                bot_id=bot["bot_id"],
                decision_id=decision_id,
            )

            # =========================
            # ORDER + EXECUTION 🔥
            # =========================
            execution_status = None

            order = build_order_proposal(
                bot=bot,
                decision=decision,
                today_spent_eur=today_spent_eur,
                total_balance_eur=cash_balance_eur,
                live_price=live_price,
            )

            if order:
                _persist_bot_order(
                    conn=conn,
                    user_id=user_id,
                    bot_id=bot["bot_id"],
                    decision_id=decision_id,
                    order=order,
                    is_live=bool(bot.get("is_live")),
                )

                # A planned order is not consent to execute it. Manual and
                # semi-automatic bots wait for the explicit execution route,
                # including when an exchange connection is present.
                if bot.get("mode") == "auto":
                    try:
                        execution_status = _auto_execute_decision(
                            conn=conn,
                            user_id=user_id,
                            bot_id=bot["bot_id"],
                            decision_id=decision_id,
                            order=order,
                            is_live=bot.get("is_live", False),
                            mode=bot.get("mode"),
                        )
                    except Exception as e:
                        logger.exception("❌ Auto execution failed")
                        _mark_bot_decision_execution_failed(
                            conn=conn, user_id=user_id, bot_id=bot["bot_id"],
                            decision_id=decision_id,
                            reason=(str(e) if isinstance(e, BotSafetyBlock) else
                                    "Automatische uitvoering gestopt: de actuele bot- of marktvoorwaarden konden niet veilig worden bevestigd."),
                        )
                        execution_status = f"failed: {e}"
                else:
                    execution_status = "pending_confirmation"
            else:
                execution_status = "no_order"

            # =========================
            # UPDATE LAST RUN
            # =========================
            _touch_bot_last_run(
                conn=conn,
                user_id=user_id,
                bot_id=bot["bot_id"],
            )

            touched_bot_ids.append(bot["bot_id"])

            results.append({
                "bot_id": bot["bot_id"],
                "decision_id": decision_id,
                "action": decision["action"],
                "decision": decision,
                "trade_plan": trade_plan,
                "execution_status": execution_status,
            })

        conn.commit()

        for recorded in results:
            if recorded.get("decision_id") and str(recorded.get("action") or "").lower() not in {"hold", "houd_vast", "none"}:
                try:
                    from backend.celery_task.store_daily_scores_task import publish_coach_bot_decision
                    publish_coach_bot_decision.delay(user_id, int(recorded["decision_id"]))
                except Exception:
                    logger.warning("FINN Paper feed dispatch failed", exc_info=True)

        return {
            "ok": True,
            "date": str(report_date),
            "bots": len(bots),
            "decisions": results,
            "bot_ids": touched_bot_ids,
            "skip_reasons": skip_reasons,
        }

    except Exception as e:
        logger.exception("❌ trading_bot_execution failed")
        try:
            conn.rollback()
        except Exception:
            pass
        return {"ok": False, "error": str(e)}

    finally:
        conn.close()
        
# =====================================================
# 📊 Ledger delta calculator
# =====================================================
def _ledger_deltas(side: str, qty: float, price: float):
    """
    Calculates ledger deltas for a trade.

    Returns:
        cash_delta_eur
        qty_delta
        notional_eur
    """

    side = (side or "").lower().strip()

    notional = round(qty * price, 2)

    if side == "buy":
        cash_delta = -notional
        qty_delta = qty

    elif side == "sell":
        cash_delta = notional
        qty_delta = -qty

    else:
        raise ValueError(f"Unsupported side for ledger: {side}")

    return cash_delta, qty_delta, notional


# =====================================================
# 🚀 Bot execute decision functie
# =====================================================
class BotSafetyBlock(RuntimeError):
    """A safe, user-facing reason why automatic execution was stopped."""


def _paper_buy_quantity(approved_eur: Any, current_price_eur: Any) -> float:
    """Use the approved EUR spend at the current Paper price without rounding up."""
    try:
        amount = float(approved_eur)
        price = float(current_price_eur)
        if not all(math.isfinite(value) and value > 0 for value in (amount, price)):
            raise ValueError("Invalid Paper amount or price")
        qty = math.floor(amount / price * 100_000_000) / 100_000_000
        if qty > 0:
            return qty
    except (TypeError, ValueError, OverflowError):
        pass
    raise BotSafetyBlock("Het goedgekeurde bedrag past niet bij de actuele Paper-prijs.")


def _recheck_auto_buy_limits(
    *, conn, user_id: int, bot_id: int, symbol: str,
    notional: float, price: float, cash: float, current_bot: tuple,
    require_explicit_limits: bool = True,
) -> None:
    """Re-read current bot limits and ledger under the bot row lock."""
    if len(current_bot) < 8:
        raise BotSafetyBlock("De actuele botlimieten konden niet worden gecontroleerd.")
    total, daily, minimum, maximum = current_bot[4:8]
    try:
        values = [float(value) for value in (total, daily, minimum, maximum)]
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("Invalid limit")
        if require_explicit_limits and any(value <= 0 for value in values):
            raise ValueError("Missing active auto limit")
        if values[2] > values[3] or values[1] > values[0] or values[3] > values[0]:
            raise ValueError("Inconsistent active auto limits")
    except (TypeError, ValueError):
        raise BotSafetyBlock("De actuele botbudgetten zijn ongeldig. De order is geblokkeerd.") from None

    portfolio = get_bot_portfolio_state(conn, user_id, bot_id, symbol)
    today = get_today_spent_eur(conn, user_id, bot_id, date.today())
    asset_value = float(portfolio["qty"]) * price
    result = apply_guardrails(
        proposed_amount_eur=notional,
        portfolio_value_eur=cash + asset_value,
        current_asset_value_eur=asset_value,
        invested_eur=portfolio["invested"],
        today_allocated_eur=today,
        cash_balance_eur=cash,
        kill_switch=bool(current_bot[2]),
        max_trade_risk_eur=maximum,
        daily_allocation_eur=daily,
        max_asset_exposure_pct=current_bot[3],
        total_budget_eur=total,
        min_order_eur=minimum,
    )
    if not result["allowed"]:
        raise BotSafetyBlock(result["reason"] or "De actuele botlimieten laten deze order niet toe.")
    if notional > result["adjusted_amount_eur"] + 0.000001:
        raise BotSafetyBlock(
            f"De geplande order is €{notional:.2f}; de actuele limieten laten nog "
            f"€{result['adjusted_amount_eur']:.2f} toe. {result['reason']} "
            "Laat de bot een nieuw voorstel maken."
        )


def _recheck_paper_trade_entry(conn, *, user_id: int, decision_id: int, symbol: str) -> Optional[float]:
    """Return a fresh EUR execution price for a trade or None for DCA."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT s.setup_type, s.data, d.scores_json->'trade_plan'
               FROM bot_decisions d
               JOIN strategies s ON s.id=d.strategy_id AND s.user_id=d.user_id
               WHERE d.id=%s AND d.user_id=%s AND d.symbol=%s
               FOR SHARE OF s""",
            (decision_id, user_id, symbol),
        )
        row = cur.fetchone()
    if not row:
        raise BotSafetyBlock("De opgeslagen strategie bij deze Paper-beslissing is niet beschikbaar.")
    if str(row[0] or "").lower() not in {"trade", "trading", "manual", "breakout", "position"}:
        return None
    saved = _safe_json(row[1], {})
    plan = _safe_json(row[2], {})
    source = str(plan.get("source_price_currency") or "").upper()
    levels = plan.get("source_levels") or {}
    if not saved.get("price_currency_confirmed") or source not in {"EUR", "USD"}:
        raise BotSafetyBlock("De koersvaluta van deze Paper-beslissing is niet bevestigd. Maak een nieuwe beslissing.")
    if str(saved.get("price_currency") or "").upper() != source:
        raise BotSafetyBlock("De koersvaluta van de strategie is gewijzigd. Maak een nieuwe beslissing.")
    try:
        entry = float(levels["entry"])
        current_entry = float(saved["entry"])
        current_stop = float(saved["stop_loss"])
        planned_stop = float(levels["stop_loss"])
        current_targets = [float(value) for value in saved["targets"]]
        planned_targets = [float(value) for value in levels["targets"]]
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise BotSafetyBlock("De opgeslagen prijsniveaus zijn onvolledig. Maak een nieuwe beslissing.") from exc
    all_levels = [entry, current_entry, current_stop, planned_stop, *current_targets, *planned_targets]
    if (not all(math.isfinite(value) and value > 0 for value in all_levels)
            or not current_targets or current_entry != entry
            or current_stop != planned_stop or current_targets != planned_targets):
        raise BotSafetyBlock("De strategieprijzen zijn gewijzigd. Maak een nieuwe Paper-beslissing.")
    context = _get_trade_quote_fx_context(conn, symbol, require_usd=source == "USD")
    price = context.get("market_price_eur")
    if price is None:
        raise BotSafetyBlock("De marktprijs of valutakoers is niet recent genoeg voor Paper-uitvoering.")
    entry_eur = entry * float(context["usd_fx_eur_per_unit"]) if source == "USD" else entry
    if not entry_eur <= price <= entry_eur * 1.01:
        raise BotSafetyBlock("De actuele prijs ligt buiten de opgeslagen instapzone. Maak een nieuwe Paper-beslissing.")
    return price


def _auto_execute_decision(
    *,
    conn,
    user_id: int,
    bot_id: int,
    decision_id: int,
    order: dict,
    is_live: bool = False,
    mode: str = "manual",
):
    if mode != "auto":
        raise RuntimeError("Automatic execution requires auto mode")
    if is_live:
        # Share the account lock with manual orders and exchange key changes.
        # The lock is released by the durable intent commit before the remote call.
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s, %s)", (user_id, 0))
            cur.execute("""
                SELECT 1 FROM bot_orders
                WHERE user_id=%s AND execution_environment='live'
                  AND status IN ('sending', 'sent', 'unknown_exchange_state')
                  AND NOT (bot_id=%s AND decision_id=%s)
                LIMIT 1
            """, (user_id, bot_id, decision_id))
            if cur.fetchone():
                raise RuntimeError("Another live exchange order is unresolved")
    # Lock the current owner-scoped configuration before any exchange call.
    # A stale worker snapshot must not execute after a user switches mode,
    # disables the bot, or changes its Paper/Live setting.
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT mode, is_live, is_active, max_asset_exposure_pct,
                   budget_total_eur, budget_daily_limit_eur,
                   budget_min_order_eur, budget_max_order_eur
            FROM bot_configs
            WHERE id=%s AND user_id=%s
            FOR UPDATE
            """,
            (bot_id, user_id),
        )
        current_bot = cur.fetchone()
    if not current_bot or current_bot[0] != "auto" or not current_bot[2]:
        raise RuntimeError("Automatic execution requires an active auto bot")
    if bool(current_bot[1]) != bool(is_live):
        raise RuntimeError("Bot execution environment changed")
    symbol = (order.get("symbol") or DEFAULT_SYMBOL).upper()
    side = (order.get("side") or "buy").lower().strip()

    qty = float(order.get("estimated_qty") or 0.0)
    price = float(order.get("estimated_price") or 0.0)

    if qty <= 0 or price <= 0:
        raise RuntimeError("Invalid execution parameters")

    if not is_live:
        checked_trade_price = _recheck_paper_trade_entry(
            conn, user_id=user_id, decision_id=decision_id, symbol=symbol,
        ) if side == "buy" else None
        price = checked_trade_price if checked_trade_price is not None else _get_live_price(
            conn, symbol, paper_execution=True,
        )
        if price is None:
            raise BotSafetyBlock("Geen actuele, gecontroleerde EUR-prijs voor Paper-uitvoering.")
        if side == "buy":
            # Preserve the approved EUR amount when the Paper market price
            # changes between planning and execution. Quantity can shrink;
            # spend must never grow beyond the checked proposal.
            qty = _paper_buy_quantity(order.get("quote_amount_eur"), price)
    cash_delta, qty_delta, notional = _ledger_deltas(side, qty, price)
    claimed = _claim_bot_decision_for_execution(
        conn=conn,
        user_id=user_id,
        bot_id=bot_id,
        decision_id=decision_id,
        executed_by="auto",
    )
    if not claimed:
        raise RuntimeError("Decision already processing or executed")

    submission_started = False
    try:
        if not is_live and side == "buy":
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT cash_eur FROM bot_portfolios
                       WHERE user_id=%s AND bot_id=%s AND symbol=%s FOR UPDATE""",
                    (user_id, bot_id, symbol),
                )
                cash_row = cur.fetchone()
            if cash_row is None or float(cash_row[0] or 0) + 0.001 < notional:
                raise BotSafetyBlock("De Paper-bot heeft onvoldoende virtueel kassaldo voor deze order.")
            _recheck_auto_buy_limits(
                conn=conn, user_id=user_id, bot_id=bot_id, symbol=symbol,
                notional=notional, price=price, cash=float(cash_row[0]),
                current_bot=current_bot,
            )
        if side == "buy":
            _require_current_setup_revision_for_buy(
                conn=conn, user_id=user_id, bot_id=bot_id, decision_id=decision_id,
            )
        # Live submission is durable before contacting the exchange. Only a
        # confirmed exchange fill may update the ledger and Paper-style
        # portfolio projection.
        if is_live:
            exchange_name, balance = _get_live_exchange_balance(conn, user_id)
            if side == "buy":
                available = float((balance.get("free") or {}).get("EUR") or 0)
                if not math.isfinite(available) or available < notional:
                    raise BotSafetyBlock("Het actuele exchange-kassaldo is te laag voor deze Live order.")
                _recheck_auto_buy_limits(
                    conn=conn, user_id=user_id, bot_id=bot_id, symbol=symbol,
                    notional=notional, price=price, cash=available,
                    current_bot=current_bot,
                )
                _validate_live_auto_order_risk(
                    conn, user_id, symbol, notional, balance,
                    float(100 if current_bot[3] is None else current_bot[3]), bot_id, decision_id,
                    exchange_name, order_price=price,
                )
            else:
                available = float((balance.get("free") or {}).get(symbol) or 0)
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT COALESCE(SUM(qty_delta), 0) FROM bot_ledger
                        WHERE user_id=%s AND bot_id=%s AND symbol=%s
                    """, (user_id, bot_id, symbol))
                    bot_position = float(cur.fetchone()[0] or 0)
                if not math.isfinite(available) or available < qty or bot_position < qty:
                    raise RuntimeError("Insufficient live asset balance at execution time")
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE bot_orders SET status='sending', exchange_name=%s,
                        updated_at=NOW()
                    WHERE user_id=%s AND bot_id=%s AND decision_id=%s
                      AND execution_environment='live' AND status='ready'
                    RETURNING id
                """, (exchange_name, user_id, bot_id, decision_id))
                if not cur.fetchone():
                    raise RuntimeError("Live order is no longer ready")
            conn.commit()
            submission_started = True
            try:
                exchange_order = _execute_on_exchange_sync(
                    conn, user_id, exchange_name, symbol, side, qty, price
                )
            except Exception:
                logger.error("Automatic live exchange response uncertain: bot=%s decision=%s", bot_id, decision_id)
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE bot_orders SET status='unknown_exchange_state', updated_at=NOW()
                        WHERE user_id=%s AND bot_id=%s AND decision_id=%s
                    """, (user_id, bot_id, decision_id))
                    cur.execute("""
                        UPDATE bot_decisions SET status='unknown_exchange_state', updated_at=NOW()
                        WHERE id=%s AND user_id=%s AND bot_id=%s
                    """, (decision_id, user_id, bot_id))
                conn.commit()
                return "unknown_exchange_state"
            exchange_id = str((exchange_order or {}).get("id") or "")
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE bot_orders SET status=%s, exchange_order_id=%s,
                        exchange_symbol=%s, updated_at=NOW()
                    WHERE user_id=%s AND bot_id=%s AND decision_id=%s
                """, (
                    "sent" if exchange_id else "unknown_exchange_state",
                    exchange_id or None,
                    str((exchange_order or {}).get("symbol") or f"{symbol}/EUR"),
                    user_id, bot_id, decision_id,
                ))
                cur.execute("""
                    UPDATE bot_decisions SET status=%s, updated_at=NOW()
                    WHERE id=%s AND user_id=%s AND bot_id=%s
                """, (
                    "awaiting_exchange" if exchange_id else "unknown_exchange_state",
                    decision_id, user_id, bot_id,
                ))
            conn.commit()
            return "awaiting_exchange" if exchange_id else "unknown_exchange_state"

        with conn.cursor() as cur:
            # 1) Order -> filled (BELANGRIJK: filter ook op user/bot/decision)
            cur.execute(
                """
                UPDATE bot_orders
                SET status='filled',
                    executed_price_eur=%s,
                    executed_qty=%s,
                    quote_amount_eur=%s,
                    updated_at=NOW()
                WHERE user_id=%s
                  AND bot_id=%s
                  AND decision_id=%s
                RETURNING id
                """,
                (price, qty, notional, user_id, bot_id, decision_id),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError("No bot_order found to execute")

            bot_order_id = int(row[0])

            # 2) Ledger entry
            record_bot_ledger_entry(
                conn=conn,
                user_id=user_id,
                bot_id=bot_id,
                entry_type="execute",
                cash_delta_eur=cash_delta,
                qty_delta=qty_delta,
                price_eur=price,
                symbol=symbol,
                decision_id=decision_id,
                order_id=bot_order_id,
                note="Auto execution",
                valuation_version=1 if is_live else 2,
                meta={
                    "side": side,
                    "price": price,
                    "qty": qty,
                    "notional_eur": notional,
                },
            )

            # 3) Execution -> filled
            cur.execute(
                """
                UPDATE bot_executions
                SET status='filled',
                    filled_qty=%s,
                    avg_fill_price=%s,
                    updated_at=NOW()
                WHERE user_id=%s
                  AND bot_order_id=%s
                """,
                (qty, price, user_id, bot_order_id),
            )

            # 4) Decision -> executed
            cur.execute(
                """
                UPDATE bot_decisions
                SET status='executed',
                    executed_by='auto',
                    executed_at=NOW(),
                    updated_at=NOW()
                WHERE id=%s
                  AND user_id=%s
                  AND bot_id=%s
                  AND status='executing'
                """,
                (decision_id, user_id, bot_id),
            )
    except Exception as exc:
        if not submission_started:
            _mark_bot_decision_execution_failed(
                conn=conn,
                user_id=user_id,
                bot_id=bot_id,
                decision_id=decision_id,
                reason=str(exc) if isinstance(exc, BotSafetyBlock) else None,
            )
        raise

    logger.info(f"⚡ Auto executed | bot={bot_id} | side={side} | qty={qty} | price={price}")
    return "filled"


# =====================================================
# 🚀 Manual execute decision functie
# =====================================================
def execute_manual_decision(
    *,
    conn,
    user_id: int,
    bot_id: int,
    decision_id: int,
):
    # Match the automatic executor's lock order: bot, decision, order, then
    # Paper portfolio. This serializes all debits for a bot without creating
    # a manual-versus-auto lock inversion.
    with conn.cursor() as cur:
        cur.execute(
            """SELECT is_live, is_active, max_asset_exposure_pct,
                      budget_total_eur, budget_daily_limit_eur,
                      budget_min_order_eur, budget_max_order_eur
               FROM bot_configs WHERE id=%s AND user_id=%s FOR UPDATE""",
            (bot_id, user_id),
        )
        bot_row = cur.fetchone()
    if bot_row is None:
        raise RuntimeError("Bot not found")
    bot_live = bool(bot_row[0])
    if not bot_row[1]:
        raise RuntimeError("Bot is paused")
    if bot_live:
        # This legacy confirmation route still books a sent limit order as a
        # fill. Use the reconciled Live manual-order path instead.
        raise RuntimeError("Live botbeslissing kan pas na bevestigde exchange-fill worden uitgevoerd")
    claimed = _claim_bot_decision_for_execution(
        conn=conn,
        user_id=user_id,
        bot_id=bot_id,
        decision_id=decision_id,
        executed_by="manual",
    )
    if not claimed:
        raise RuntimeError("Decision already processing or executed")

    try:
        # 1) Pak executable order (incl side)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT o.id, o.symbol, o.side, o.estimated_qty,
                       o.estimated_price_eur, o.quote_amount_eur
                FROM bot_orders o
                WHERE o.decision_id=%s
                  AND o.user_id=%s
                  AND o.bot_id=%s
                  AND o.status IN ('ready','pending')
                FOR UPDATE
                """,
                (decision_id, user_id, bot_id),
            )
            row = cur.fetchone()

        if not row:
            raise RuntimeError("No executable order")

        bot_order_id, symbol, side, qty, price = row[:5]
        approved_eur = row[5] if len(row) > 5 else qty * price
        symbol = (symbol or DEFAULT_SYMBOL).upper()
        side = (side or "buy").lower().strip()
        qty = float(qty or 0.0)
        price = float(price or 0.0)

        if qty <= 0 or price <= 0:
            raise RuntimeError("Invalid order execution values")

        if not bot_live:
            checked_trade_price = _recheck_paper_trade_entry(
                conn, user_id=user_id, decision_id=decision_id, symbol=symbol,
            ) if side == "buy" else None
            price = checked_trade_price if checked_trade_price is not None else _get_live_price(
                conn, symbol, paper_execution=True,
            )
            if price is None:
                raise BotSafetyBlock("Geen actuele, gecontroleerde EUR-prijs voor Paper-uitvoering.")
            if side == "buy":
                qty = _paper_buy_quantity(approved_eur, price)
        if side == "buy":
            try:
                _require_current_setup_revision_for_buy(
                    conn=conn, user_id=user_id, bot_id=bot_id, decision_id=decision_id,
                )
            except RuntimeError as exc:
                raise BotSafetyBlock("De gekoppelde setup is gewijzigd. Maak een nieuwe botbeslissing voordat je koopt.") from exc

        cash_delta, qty_delta, notional = _ledger_deltas(side, qty, price)

        # 1.5) Live Execution
        if not bot_live and side == "buy":
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT cash_eur FROM bot_portfolios
                       WHERE user_id=%s AND bot_id=%s AND symbol=%s FOR UPDATE""",
                    (user_id, bot_id, symbol),
                )
                cash_row = cur.fetchone()
            if cash_row is None or float(cash_row[0] or 0) + 0.001 < notional:
                raise BotSafetyBlock("De Paper-bot heeft onvoldoende virtueel kassaldo voor deze order.")
            _recheck_auto_buy_limits(
                conn=conn, user_id=user_id, bot_id=bot_id, symbol=symbol,
                notional=notional, price=price, cash=float(cash_row[0]),
                current_bot=("manual", bot_live, bot_row[1], *bot_row[2:]),
                require_explicit_limits=False,
            )
        
        if bot_live:
            _execute_on_exchange_sync(conn, user_id, "bitvavo", symbol, side, qty, price)

        with conn.cursor() as cur:
            # 2) Order -> filled
            cur.execute(
                """
                UPDATE bot_orders
                SET status='filled',
                    executed_price_eur=%s,
                    executed_qty=%s,
                    quote_amount_eur=%s,
                    updated_at=NOW()
                WHERE id=%s AND user_id=%s AND bot_id=%s
                """,
                (price, qty, notional, bot_order_id, user_id, bot_id),
            )

            # 3) Ledger entry
            record_bot_ledger_entry(
                conn=conn,
                user_id=user_id,
                bot_id=bot_id,
                entry_type="execute",
                cash_delta_eur=cash_delta,
                qty_delta=qty_delta,
                price_eur=price,
                symbol=symbol,
                decision_id=decision_id,
                order_id=bot_order_id,
                note="Manual execution",
                valuation_version=1 if bot_live else 2,
                meta={
                    "side": side,
                    "price": price,
                    "qty": qty,
                    "notional_eur": notional,
                },
            )

            # 4) Execution -> filled
            cur.execute(
                """
                UPDATE bot_executions
                SET status='filled',
                    filled_qty=%s,
                    avg_fill_price=%s,
                    updated_at=NOW()
                WHERE user_id=%s
                  AND bot_order_id=%s
                """,
                (qty, price, user_id, bot_order_id),
            )

            # 5) Decision -> executed
            cur.execute(
                """
                UPDATE bot_decisions
                SET status='executed',
                    executed_by='manual',
                    executed_at=NOW(),
                    updated_at=NOW()
                WHERE id=%s
                  AND user_id=%s
                  AND bot_id=%s
                  AND status='executing'
                """,
                (decision_id, user_id, bot_id),
            )
    except Exception as exc:
        _mark_bot_decision_execution_failed(
            conn=conn,
            user_id=user_id,
            bot_id=bot_id,
            decision_id=decision_id,
            reason=str(exc) if isinstance(exc, BotSafetyBlock) else None,
        )
        raise
