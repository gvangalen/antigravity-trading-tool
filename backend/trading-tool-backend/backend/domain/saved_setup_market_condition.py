"""Recover the UI market choice from the saved combined benchmark bounds.

The choice label is not a separate database field. An exact benchmark band is
a preset; every other bounded setup is Custom.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


_BANDS = (
    ("heavy_pressure", 0, 25, ("Zwaar onder druk", "Heavy pressure", "Stark unter Druck")),
    ("pressure", 26, 45, ("Onder druk", "Under pressure", "Unter Druck")),
    ("no_direction", 46, 60, ("Geen duidelijke richting", "No clear direction", "Keine klare Richtung")),
    ("gaining_strength", 61, 75, ("De markt trekt aan", "Gaining strength", "Der Markt wird stärker")),
    ("strong", 76, 100, ("Sterke markt", "Strong market", "Starker Markt")),
)
_FIELDS = ("min_benchmark_score", "max_benchmark_score")


def _number(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def saved_setup_market_condition(setup: Mapping[str, Any]) -> dict[str, Any]:
    """Return semantic read evidence without inventing a current score or buy."""
    bounds = {field: setup.get(field) for field in _FIELDS}
    has_bounds = any(value is not None for value in bounds.values())
    result: dict[str, Any] = {
        "kind": "custom" if has_bounds else "none",
        "source": "saved_score_bounds",
        "effect": "setup_eligibility_only" if has_bounds else "no_score_filter",
        "purchase_guaranteed": False,
    }
    if result["kind"] == "none":
        return result
    minimum = _number(bounds["min_benchmark_score"])
    maximum = _number(bounds["max_benchmark_score"])
    for key, band_min, band_max, labels in _BANDS:
        if minimum == band_min and maximum == band_max:
            return {
                **result,
                "kind": "preset",
                "key": key,
                "labels": dict(zip(("nl", "en", "de"), labels)),
                "benchmark_score_min": band_min,
                "benchmark_score_max": band_max,
            }
    return {
        **result,
        "benchmark_score_min": float(minimum) if minimum is not None else None,
        "benchmark_score_max": float(maximum) if maximum is not None else None,
    }
