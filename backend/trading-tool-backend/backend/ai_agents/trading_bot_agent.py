# backend/ai_agents/trading_bot_agent.py
import logging
import json
from datetime import date
from typing import Any, Dict, List, Optional

from backend.utils.db import get_db_connection
# ✅ Engine brain (single source of truth)
from backend.engine.bot_brain import run_bot_brain
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


def _clamp_score(v: Any, *, default: float = 10.0, lo: float = 10.0, hi: float = 100.0) -> float:
    """
    Scores mogen NOOIT 0 zijn.
    - None/NaN/invalid -> default
    - < lo -> lo
    - > hi -> hi
    """
    try:
        x = float(v)
        if x != x:  # NaN
            x = default
    except Exception:
        x = default

    if x < lo:
        return float(lo)
    if x > hi:
        return float(hi)
    return float(x)


def _confidence_from_score(score: float) -> str:
    s = float(score or 0)
    if s >= 70:
        return "high"
    if s >= 40:
        return "medium"
    return "low"


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

def _get_live_price(conn, symbol: str) -> Optional[float]:
    symbol = (symbol or DEFAULT_SYMBOL).upper()

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT price
            FROM market_data
            WHERE symbol = %s
              AND price IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (symbol,),
        )
        row = cur.fetchone()

    if not row or row[0] is None:
        return None

    return float(row[0])

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
    except Exception as e:
        logger.error(f"❌ Exchange execution failed: {e}")
        raise e

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
            SELECT base_amount, execution_mode, decision_curve, setup_type
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

    base_amount, execution_mode, decision_curve, setup_type = row

    # =====================================================
    # NORMALIZE VALUES
    # =====================================================
    try:
        base_amount = float(base_amount or 0.0)
    except Exception:
        base_amount = 0.0

    execution_mode = (execution_mode or "fixed").lower().strip()
    curve = _safe_json(decision_curve, {}) if decision_curve is not None else {}

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
    }

    if execution_mode == "custom":
        payload["decision_curve"] = curve or {}

    return payload

# =====================================================
# 📦 Risk profiles
# =====================================================
def _get_risk_thresholds(risk_profile: str) -> dict:
    """
    Defines decision thresholds per risk profile.
    (UI + legacy behavior: still used for setup_match text)
    """
    profile = (risk_profile or "balanced").lower()

    if profile == "conservative":
        return {"buy": 75, "hold": 55, "min_confidence": "high"}

    if profile == "aggressive":
        return {"buy": 35, "hold": 20, "min_confidence": "medium"}

    return {"buy": 55, "hold": 40, "min_confidence": "medium"}


# =====================================================
# 📦 Build setup match (UI CONTRACT)
# =====================================================
def _build_setup_match(
    *,
    bot: Dict[str, Any],
    scores: Dict[str, float],
    snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    UI-CONTRACT (KEIHARD):
    - setup_match bestaat ALTIJD
    - score is NOOIT 0
    - status + UI-tekst komen UITSLUITEND uit de backend
    - frontend mag NIETS interpreteren
    """

    macro = _clamp_score(scores.get("macro", 10), default=10)
    technical = _clamp_score(scores.get("technical", 10), default=10)
    market = _clamp_score(scores.get("market", 10), default=10)
    setup = _clamp_score(scores.get("setup", 10), default=10)

    combined_score = round((macro + technical + market + setup) / 4, 1)
    combined_score = _clamp_score(combined_score, default=10)

    thresholds = _get_risk_thresholds(bot.get("risk_profile", "balanced"))
    buy_th = float(thresholds["buy"])
    hold_th = float(thresholds["hold"])

    has_snapshot = snapshot is not None
    strategy_confidence = _clamp_score(
        snapshot.get("confidence", 0) if snapshot else 0,
        default=10,
    )

    match_buy = has_snapshot and combined_score >= buy_th and strategy_confidence >= buy_th
    match_hold = has_snapshot and combined_score >= hold_th

    if not has_snapshot:
        status = "no_snapshot"
        summary = "Geen actueel strategy-plan beschikbaar voor vandaag."
        detail = (
            "De marktcondities zijn bekend, maar deze strategie heeft vandaag "
            "onvoldoende context om gecontroleerd uitgevoerd te worden."
        )
        reason = "no_active_strategy_snapshot"

    elif match_buy:
        status = "match_buy"
        summary = "Strategie voldoet aan buy-voorwaarden."
        detail = (
            f"Totale score ({combined_score}) en strategie-confidence "
            f"({strategy_confidence}) liggen boven de buy-drempel ({buy_th})."
        )
        reason = "buy_conditions_met"

    elif match_hold:
        status = "no_match"
        summary = "Strategie actief, maar geen buy-signaal."
        detail = (
            f"Score ({combined_score}) is voldoende om vast te houden "
            f"(≥ {hold_th}), maar nog onder de buy-drempel ({buy_th})."
        )
        reason = "hold_conditions_only"

    else:
        status = "no_match"
        summary = "Strategie onder minimumdrempel."
        detail = (
            f"Score ({combined_score}) ligt onder de hold-drempel ({hold_th}). "
            "De strategie blijft inactief."
        )
        reason = "below_hold_threshold"

    return {
        "name": bot.get("setup_type") or bot.get("bot_name") or "Strategy",
        "symbol": bot.get("symbol", DEFAULT_SYMBOL),
        "timeframe": bot.get("timeframe") or "—",
        "score": combined_score,
        "confidence": _confidence_from_score(combined_score),
        "components": {"macro": macro, "technical": technical, "market": market, "setup": setup},
        "thresholds": {"buy": buy_th, "hold": hold_th},
        "strategy_confidence": strategy_confidence,
        "has_snapshot": has_snapshot,
        "match_buy": bool(match_buy),
        "match_hold": bool(match_hold),
        "status": status,
        "summary": summary,
        "detail": detail,
        "reason": reason,
    }


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
              st.timeframe

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
                "last_run": last_run.isoformat() if last_run else None,
                "budget": {
                    "total_eur": float(budget_total_eur or 0),
                    "daily_limit_eur": float(budget_daily_limit_eur or 0),
                    "min_order_eur": float(budget_min_order_eur or 0),
                    "max_order_eur": float(budget_max_order_eur or 0),
                    "max_asset_exposure_pct": float(max_asset_exposure_pct or 100),
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
def _get_daily_scores(conn, user_id: int, report_date: date, symbol: str = "BTC") -> Dict[str, float]:
    """
    Single source of truth. Returned scores are ALWAYS in [10..100].
    """
    symbol = (symbol or DEFAULT_SYMBOL).upper()

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT macro_score, technical_score, market_score, setup_score
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
        return dict(macro=10.0, technical=10.0, market=10.0, setup=10.0)

    macro, technical, market, setup = row

    return {
        "macro": _clamp_score(macro, default=10),
        "technical": _clamp_score(technical, default=10),
        "market": _clamp_score(market, default=10),
        "setup": _clamp_score(setup, default=10),
    }


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
):
    with conn.cursor() as cur:
        # 1. Insert Ledger
        cur.execute(
            """
            INSERT INTO bot_ledger (
                user_id, bot_id, decision_id, order_id, entry_type,
                symbol, cash_delta_eur, qty_delta, price_eur, note, meta, ts
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            ON CONFLICT (user_id, order_id, entry_type)
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
):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE bot_decisions
            SET status='failed_execution',
                updated_at=NOW()
            WHERE id=%s
              AND user_id=%s
              AND bot_id=%s
              AND status='executing'
            """,
            (decision_id, user_id, bot_id),
        )


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
                status,
                created_at,
                updated_at
            )
            VALUES (
                %s,%s,%s,
                %s,%s,
                'market',
                %s,%s,%s,
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
    scores: Dict[str, float],
) -> int:

    action = _normalize_action(decision.get("action"))
    confidence = _normalize_confidence(decision.get("confidence") or "low")
    symbol = (decision.get("symbol") or DEFAULT_SYMBOL).upper()

    amount_eur = float(decision.get("amount_eur") or 0.0)

    metrics = decision.get("metrics") or {}

    scores_payload = {
        "macro": _clamp_score(scores.get("macro", 10)),
        "technical": _clamp_score(scores.get("technical", 10)),
        "market": _clamp_score(scores.get("market", 10)),
        "setup": _clamp_score(scores.get("setup", 10)),

        # ✅ GEEN FAKE SCORE MEER
        "combined": _clamp_score(decision.get("score", 10)),

        "regime": decision.get("regime"),
        "risk_state": decision.get("risk_state"),

        "market_pressure": metrics.get("market_pressure"),
        "transition_risk": metrics.get("transition_risk"),

        "position_size": decision.get("position_size"),
        "amount_eur": amount_eur,

        "trade_plan": decision.get("trade_plan"),
        "watch_levels": decision.get("watch_levels"),
        "monitoring": decision.get("monitoring"),
        "alerts_active": decision.get("alerts_active"),
    }

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
                status = EXCLUDED.status,
                updated_at = NOW()
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
            ),
        )

        decision_id = int(cur.fetchone()[0])

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
def run_trading_bot_agent(
    user_id: int,
    report_date: Optional[date] = None,
    bot_id: Optional[int] = None,
) -> Dict[str, Any]:

    report_date = report_date or date.today()

    conn = get_db_connection()
    if not conn:
        return {"ok": False, "error": "db_unavailable"}

    try:
        bots = _get_active_bots(conn, user_id)

        if bot_id is not None:
            bots = [b for b in bots if b["bot_id"] == bot_id]

        if not bots:
            return {
                "ok": True,
                "date": str(report_date),
                "bots": 0,
                "decisions": [],
                "bot_ids": [],
            }


        results = []
        touched_bot_ids = []
        price_cache = {}

        for bot in bots:

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
            if symbol not in price_cache:
                price_cache[symbol] = _get_live_price(conn, symbol)
            live_price = price_cache[symbol]

            # =========================
            # SNAPSHOT
            # =========================
            snapshot = _get_active_strategy_snapshot(
                conn,
                user_id,
                bot["strategy_id"],
                report_date,
            )

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

            if setup_payload.get("symbol"):
                symbol = setup_payload.get("symbol").upper()

            if snapshot:
                setup_payload.update({
                    "entry": snapshot.get("entry"),
                    "stop_loss": snapshot.get("stop_loss"),
                    "targets": snapshot.get("targets"),
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
                },
                portfolio_context=portfolio_context,
            )

            action = _normalize_action(brain.get("action"))

            # =========================
            # SETUP MATCH
            # =========================
            setup_match = _build_setup_match(
                bot=bot,
                scores=scores,
                snapshot=snapshot,
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
                    float(brain.get("debug", {}).get("final_amount") or 0), 2
                ),

                "base_amount": brain.get("base_amount") or setup_payload.get("base_amount"),
                "execution_mode": setup_payload.get("execution_mode"),

                "position_size": round(position_size, 2),
                "exposure_multiplier": float(brain.get("exposure_multiplier") or 1.0),

                # V1: UI gebruikt setup score
                "score": scores.get("setup"),

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
            )

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
                )

                try:
                    _auto_execute_decision(
                        conn=conn,
                        user_id=user_id,
                        bot_id=bot["bot_id"],
                        decision_id=decision_id,
                        order=order,
                        is_live=bot.get("is_live", False),
                    )
                    execution_status = "filled"

                except Exception as e:
                    logger.exception("❌ Auto execution failed")
                    execution_status = f"failed: {e}"
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

        return {
            "ok": True,
            "date": str(report_date),
            "bots": len(bots),
            "decisions": results,
            "bot_ids": touched_bot_ids,
        }

    except Exception as e:
        logger.exception("❌ trading_bot_agent failed")
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
def _auto_execute_decision(
    *,
    conn,
    user_id: int,
    bot_id: int,
    decision_id: int,
    order: dict,
    is_live: bool = False,
):
    symbol = (order.get("symbol") or DEFAULT_SYMBOL).upper()
    side = (order.get("side") or "buy").lower().strip()

    qty = float(order.get("estimated_qty") or 0.0)
    price = float(order.get("estimated_price") or 0.0)

    if qty <= 0 or price <= 0:
        raise RuntimeError("Invalid execution parameters")

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

    try:
        # 0) Live Execution
        if is_live:
            _execute_on_exchange_sync(conn, user_id, "bitvavo", symbol, side, qty, price)

        with conn.cursor() as cur:
            # 1) Order -> filled (BELANGRIJK: filter ook op user/bot/decision)
            cur.execute(
                """
                UPDATE bot_orders
                SET status='filled',
                    executed_price_eur=%s,
                    executed_qty=%s,
                    quote_amount_eur=COALESCE(quote_amount_eur, %s),
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
    except Exception:
        _mark_bot_decision_execution_failed(
            conn=conn,
            user_id=user_id,
            bot_id=bot_id,
            decision_id=decision_id,
        )
        raise

    logger.info(f"⚡ Auto executed | bot={bot_id} | side={side} | qty={qty} | price={price}")


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
                SELECT o.id, o.symbol, o.side, o.estimated_qty, o.estimated_price_eur
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

        bot_order_id, symbol, side, qty, price = row
        symbol = (symbol or DEFAULT_SYMBOL).upper()
        side = (side or "buy").lower().strip()
        qty = float(qty or 0.0)
        price = float(price or 0.0)

        if qty <= 0 or price <= 0:
            raise RuntimeError("Invalid order execution values")

        cash_delta, qty_delta, notional = _ledger_deltas(side, qty, price)

        # 1.5) Live Execution
        with conn.cursor() as cur:
            cur.execute("SELECT is_live FROM bot_configs WHERE id=%s", (bot_id,))
            bot_live = cur.fetchone()[0]
        
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
                    quote_amount_eur=COALESCE(quote_amount_eur, %s),
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
    except Exception:
        _mark_bot_decision_execution_failed(
            conn=conn,
            user_id=user_id,
            bot_id=bot_id,
            decision_id=decision_id,
        )
        raise
