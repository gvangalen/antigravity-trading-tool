"""The exact proposed fields exposed to clients before confirmation."""

from typing import Any, Mapping


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
        for key in ("asset", "setup_id", "strategy_id", "bot_id", "plan_id", "indicator_id", "operation", "requested_mode")
        if fields.get(key) is not None
    }
