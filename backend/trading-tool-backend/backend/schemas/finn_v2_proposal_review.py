"""The exact proposed fields exposed to clients before confirmation."""

from typing import Any, Mapping

from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.infrastructure.repositories.setup_repository import SetupRepository
from backend.infrastructure.repositories.strategy_repository import StrategyRepository


_OWNED_TARGET_ID_FIELD = {
    "delete_setup": "setup_id",
    "delete_strategy": "strategy_id",
    "delete_bot": "bot_id",
    "deactivate_bot": "bot_id",
    "activate_paper_bot": "bot_id",
    "activate_live_bot": "bot_id",
}


async def verified_review_target_name(
    session: Any, *, user_id: int, operation_type: str,
    target_id: str | None, change: Mapping[str, Any],
) -> str | None:
    """Resolve a mutable target from the authenticated owner's records."""
    id_field = _OWNED_TARGET_ID_FIELD.get(operation_type)
    if not id_field:
        return None
    try:
        object_id = int(change[id_field])
    except (KeyError, TypeError, ValueError):
        return None
    if target_id is not None and str(object_id) != str(target_id):
        return None
    if id_field == "setup_id":
        record = await SetupRepository(session).get_setup_by_id(object_id, user_id)
    elif id_field == "strategy_id":
        record = await StrategyRepository(session).get_raw_strategy_with_setup(object_id, user_id)
    else:
        record = await BotRepository(session).get_bot_config(user_id, object_id)
    name = str((record or {}).get("name") or "").strip()
    return name or None


def requested_state_for_review(change: Mapping[str, Any] | None) -> dict[str, Any]:
    fields = dict(change or {})
    for key in ("requested_state", "changed_fields"):
        value = fields.get(key)
        if isinstance(value, dict) and value:
            return dict(value)

    setup = fields.get("setup_fields")
    strategy = fields.get("strategy_fields")
    if isinstance(setup, dict) and isinstance(strategy, dict) and strategy:
        return {"setup": dict(setup), "strategy": dict(strategy)}
    for key in ("setup_fields", "strategy_fields", "bot_fields", "target_allocations", "after"):
        value = fields.get(key)
        if isinstance(value, dict) and value:
            return dict(value)

    return {
        key: fields[key]
        for key in (
            "asset", "setup_id", "strategy_id", "bot_id", "plan_id", "indicator_id",
            "operation", "requested_mode", "side", "order_type", "quantity",
            "notional", "limit_price",
        )
        if fields.get(key) is not None
    }
