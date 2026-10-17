"""Recover the UI market choice from the canonical saved score bounds.

The choice label is not a separate database field. Only an exact market band
with no macro or technical limits is a preset; every other bounded setup is
Custom. This mirrors the five inclusive bands in the web setup picker.
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
_FIELDS = tuple(
    f"{bound}_{category}_score"
    for category in ("market", "macro", "technical")
    for bound in ("min", "max")
)


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
    if any(bounds[field] is not None for field in (
        "min_macro_score", "max_macro_score", "min_technical_score", "max_technical_score",
    )):
        return result
    minimum = _number(bounds["min_market_score"])
    maximum = _number(bounds["max_market_score"])
    for key, band_min, band_max, labels in _BANDS:
        if minimum == band_min and maximum == band_max:
            return {
                **result,
                "kind": "preset",
                "key": key,
                "labels": dict(zip(("nl", "en", "de"), labels)),
                "market_score_min": band_min,
                "market_score_max": band_max,
            }
    return result
