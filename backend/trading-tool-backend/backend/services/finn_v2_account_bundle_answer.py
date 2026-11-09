"""Render an ID-coherent account read from owner-scoped tool results."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.services.finn_v2_tool_adapters.display_source_moment import amsterdam_source_moment


_SCOPES = {"read_active_setup", "read_linked_strategy", "read_bot_status", "read_portfolio"}
_CADENCE_NL = {"daily": "dagelijks", "weekly": "wekelijks", "monthly": "maandelijks"}
_ACTION_NL = {"hold": "aanhouden", "buy": "kopen", "sell": "verkopen"}


def _number(value: Any) -> str | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite():
        return None
    return format(number.normalize(), "f")


def render_account_bundle_answer(tool_trace: tuple[dict[str, Any], ...], *, locale: str) -> str | None:
    """Return an exact answer only when the requested reads are ID-coherent."""
    if not locale.lower().startswith("nl"):
        return None
    collected: dict[str, dict[str, Any]] = {}
    for call in tool_trace:
        result = call.get("result") if isinstance(call, dict) else None
        for item in (result or {}).get("results") or []:
            if not isinstance(item, dict) or item.get("scope") not in _SCOPES:
                continue
            if item.get("status") != "completed" or not isinstance(item.get("data"), dict):
                return None
            scope, data = item["scope"], item["data"]
            if scope in collected and collected[scope] != data:
                return None
            collected[scope] = data
    if set(collected) != _SCOPES:
        return None

    setup = collected["read_active_setup"]
    strategy = collected["read_linked_strategy"]
    bot = collected["read_bot_status"]
    portfolio = collected["read_portfolio"]
    setup_id, strategy_id, bot_id = setup.get("setup_id"), strategy.get("strategy_id"), bot.get("bot_id")
    if (not all(isinstance(value, int) and value > 0 for value in (setup_id, strategy_id, bot_id))
            or strategy.get("setup_id") != setup_id
            or type(bot.get("is_active")) is not bool or type(bot.get("is_live")) is not bool):
        return None
    positions = [row for row in portfolio.get("bots", [])
                 if isinstance(row, dict) and row.get("bot_id") == bot_id]
    if len(positions) != 1 or positions[0].get("strategy_id") != strategy_id:
        return None
    position = positions[0]
    # A default portfolio read is a Paper ledger. It does not reconcile a Live
    # bot against the broker, so never turn that ledger into a Live holding.
    if (position.get("setup_id") != setup_id or bot["is_live"] is not False
            or position.get("is_live") is not False):
        return None
    symbols = {str(value).upper() for value in (
        setup.get("symbol"), strategy.get("symbol"), position.get("symbol"),
    ) if value}
    if len(symbols) != 1:
        return None
    for field in ("market_id", "quote_currency"):
        left, right = setup.get(field), strategy.get(field)
        if left is not None and right is not None and str(left).upper() != str(right).upper():
            return None

    cadence = setup.get("dca_frequency")
    amount = _number(strategy.get("base_amount"))
    currency = str(strategy.get("currency") or "EUR").upper()
    quantity = _number(position.get("position_qty"))
    decision = bot.get("latest_decision")
    if (not isinstance(cadence, str) or not cadence.strip()
            or amount is None or currency not in {"EUR", "USD", "USDT"}
            or quantity is None or not isinstance(decision, dict)
            or not isinstance(decision.get("action"), str) or not decision["action"].strip()):
        return None
    if Decimal(quantity) < 0:
        return None
    raw_at = decision.get("decision_at")
    try:
        at = raw_at if isinstance(raw_at, datetime) else datetime.fromisoformat(str(raw_at).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if at.tzinfo is None:
        return None
    utc_at = at.astimezone(timezone.utc).replace(microsecond=0)
    local_at = amsterdam_source_moment(utc_at)
    if not local_at:
        return None
    bot_mode = "actief" if bot["is_active"] else "gepauzeerd"
    execution_mode = "Paper (niet live)"
    position_state = "wel" if Decimal(quantity) > 0 else "geen"
    cadence_label = _CADENCE_NL.get(cadence.casefold())
    cadence_text = f"{cadence_label} ({cadence})" if cadence_label else cadence
    action = decision["action"].strip()
    action_label = _ACTION_NL.get(action.casefold())
    action_text = f"{action} ({action_label})" if action_label else action
    return (
        f"Volgens je opgeslagen gegevens: de DCA-setup heeft ritme {cadence_text} "
        f"en het basisbedrag is {amount} {currency}. De gekoppelde bot is {bot_mode} "
        f"en staat in {execution_mode}-modus. Je hebt {position_state} Paper-positie: "
        f"{quantity} {position.get('symbol') or setup.get('symbol') or 'eenheden'}. "
        f"De laatst opgeslagen botbeslissing is {action_text} op "
        f"{utc_at.strftime('%Y-%m-%d %H:%M:%S')} UTC ({local_at}, Europe/Amsterdam)."
    )
