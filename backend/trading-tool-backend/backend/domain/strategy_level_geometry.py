"""Static strategy level geometry; never a live trade or suitability signal."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Iterable


def strategy_level_geometry(
    entry: Any, stop_loss: Any, targets: Iterable[Any] | None,
) -> dict[str, Any]:
    try:
        entry_value = Decimal(str(entry))
        stop_value = Decimal(str(stop_loss))
        target_values = [Decimal(str(target)) for target in (targets or ())]
    except (InvalidOperation, TypeError, ValueError):
        return {"status": "unavailable", "reason": "levels_invalid"}
    if not target_values or not all(value.is_finite() for value in (entry_value, stop_value, *target_values)):
        return {"status": "unavailable", "reason": "levels_missing_or_invalid"}
    risk = abs(entry_value - stop_value)
    if risk == 0 or entry_value <= 0:
        return {"status": "unavailable", "reason": "risk_not_positive"}
    direction = "long" if stop_value < entry_value else "short"
    if any((target <= entry_value if direction == "long" else target >= entry_value)
           for target in target_values):
        return {"status": "unavailable", "reason": "target_wrong_side_of_entry"}
    return {
        "status": "completed",
        "direction": direction,
        "risk_per_unit": format(risk.normalize(), "f"),
        "entry_stop_distance_percent": str(((risk / entry_value) * 100).quantize(Decimal("0.01"))),
        "targets": [
            {
                "price": format(target.normalize(), "f"),
                "reward_per_unit": format(abs(target - entry_value).normalize(), "f"),
                "reward_to_risk": str((abs(target - entry_value) / risk).quantize(Decimal("0.01"))),
            }
            for target in target_values
        ],
        "boundary": "Static arithmetic from saved levels, not current market evidence or suitability.",
    }
