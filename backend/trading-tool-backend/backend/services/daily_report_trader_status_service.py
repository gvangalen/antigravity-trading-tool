"""Owner-scoped current Paper state shown beside a stored daily report.

The report itself remains an immutable morning snapshot. This read never
generates a report, starts a bot, or interprets a saved level as an exchange
order. In particular, ``last_run`` is not proof that an exit was checked.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from backend.services.bot_service import BotService


def _json(value: Any, default: Any) -> Any:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return default
    return value if isinstance(value, type(default)) else default


def _number(value: Any) -> float | None:
    try:
        number = float(value) if value is not None else None
        return number if number is None or math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _timestamp(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


_DECISION_REASON_KEYS = {
    "Scheduled DCA amount selected from the confirmed plan": "scheduled_dca_amount",
    "Opgeslagen setupvoorwaarden passen niet bij de actuele benchmark.": "outside_conditions",
    "Opgeslagen setupvoorwaarden passen niet bij de actuele scores.": "outside_conditions",
    "Actuele benchmarkgegevens zijn onvoldoende voor deze trade.": "insufficient_data",
    "Actuele benchmarkgegevens zijn onvoldoende voor deze aankoop.": "insufficient_data",
    "Deze setup heeft geen beoordeelbare scorevoorwaarden.": "unconfigured",
}


async def current_daily_trader_status(session, user_id: int) -> dict[str, Any]:
    portfolios = await BotService(session).get_bot_portfolios(user_id)
    if not portfolios:
        return {"observed_at": datetime.now(timezone.utc).isoformat(), "bots": []}

    rows = await session.execute(text("""
        SELECT b.id AS bot_id, b.last_run, b.is_active, b.is_live, b.mode,
               st.setup_type, s.entry, s.stop_loss, s.targets, s.data AS strategy_data,
               s.name AS strategy_name, st.name AS setup_name,
               d.id AS decision_id, d.decision_kind, d.action, d.status AS decision_status,
               d.decision_ts, d.reason_json, d.scores_json
        FROM bot_configs b
        LEFT JOIN strategies s ON s.id=b.strategy_id AND s.user_id=b.user_id
        LEFT JOIN setups st ON st.id=s.setup_id AND st.user_id=b.user_id
        LEFT JOIN LATERAL (
            SELECT id, decision_kind, action, status, decision_ts, reason_json, scores_json
            FROM bot_decisions
            WHERE user_id=b.user_id AND bot_id=b.id
            ORDER BY decision_ts DESC, id DESC LIMIT 1
        ) d ON TRUE
        WHERE b.user_id=:user_id
    """), {"user_id": user_id})
    by_id = {int(row["bot_id"]): dict(row) for row in rows.mappings()}

    bots = []
    for portfolio in portfolios:
        row = by_id.get(int(portfolio["bot_id"]))
        if row is None:
            continue
        stats = portfolio.get("stats") or {}
        quantity = _number(stats.get("net_qty"))
        strategy_data = _json(row.get("strategy_data"), {})
        targets = _json(row.get("targets"), [])
        if isinstance(targets, list):
            targets = [_number(value) for value in targets]
            targets = [value for value in targets if value is not None]
        else:
            targets = []
        stop = _number(row.get("stop_loss"))
        entry = _number(row.get("entry"))
        currency = str(strategy_data.get("price_currency") or "").upper() or None
        paper_auto_trade = (
            not bool(row.get("is_live")) and bool(row.get("is_active"))
            and row.get("mode") == "auto" and row.get("setup_type") == "trade"
        )
        levels_ready = (
            paper_auto_trade and bool(strategy_data.get("price_currency_confirmed"))
            and currency in {"EUR", "USD", "USDT"}
            and entry is not None and stop is not None and bool(targets)
            and stop < entry < targets[0]
        )
        # The worker presently records an exit decision only when a level is
        # reached. Ordinary no-trigger checks have no persisted evidence.
        # Never display last_run or an assessment decision as proof of exit
        # monitoring; a separate check event is needed for that claim.
        monitoring = (
            "not_applicable" if quantity is None or quantity <= 0 or bool(row.get("is_live")) else
            "not_configured" if not paper_auto_trade else
            "levels_unconfirmed" if not levels_ready else
            "configured_check_unverified"
        )
        scores = _json(row.get("scores_json"), {})
        reasons = _json(row.get("reason_json"), [])
        if isinstance(reasons, dict):
            reasons = [reasons.get(key) for key in ("reason", "message", "detail")]
        reasons = [value.strip() for value in reasons if isinstance(value, str) and value.strip()]
        bots.append({
            "bot_id": portfolio["bot_id"], "bot_name": portfolio.get("name"),
            "symbol": portfolio.get("symbol"), "is_live": bool(row.get("is_live")),
            "is_active": bool(row.get("is_active")), "mode": row.get("mode"),
            "setup_name": row.get("setup_name"), "strategy_name": row.get("strategy_name"),
            "position_qty": quantity, "position_value_eur": stats.get("position_value_eur"),
            "valuation_status": portfolio.get("valuation_status"),
            "price_source_at": stats.get("price_source_at"), "fx_source_at": stats.get("fx_source_at"),
            "stop_loss": stop, "first_target": targets[0] if targets else None,
            "level_currency": currency, "exit_monitoring": monitoring,
            "last_run": _timestamp(row.get("last_run")),
            "latest_decision": ({
                "id": row["decision_id"], "kind": row.get("decision_kind"),
                "action": row.get("action"), "status": row.get("decision_status"),
                "at": _timestamp(row.get("decision_ts")),
                "reason": reasons[0] if reasons else None,
                "reason_key": _DECISION_REASON_KEYS.get(reasons[0]) if reasons else None,
                "block_code": scores.get("guardrail_reason") or scores.get("execution_failure"),
            } if row.get("decision_id") is not None else None),
        })
    bots.sort(key=lambda bot: (bot["position_qty"] is None or bot["position_qty"] == 0, bot["bot_id"]))
    return {"observed_at": datetime.now(timezone.utc).isoformat(), "bots": bots}
