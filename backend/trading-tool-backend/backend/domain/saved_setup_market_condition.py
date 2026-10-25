"""Recover the UI market choice from the saved combined benchmark bounds.

The choice label is not a separate database field. An exact benchmark band is
a preset; every other bounded setup is Custom.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any, Mapping


_BANDS = (
    ("heavy_pressure", 0, 25, ("Zwaar onder druk", "Heavy pressure", "Stark unter Druck")),
    ("pressure", 26, 45, ("Onder druk", "Under pressure", "Unter Druck")),
    ("no_direction", 46, 60, ("Geen duidelijke richting", "No clear direction", "Keine klare Richtung")),
    ("gaining_strength", 61, 75, ("De markt trekt aan", "Gaining strength", "Der Markt wird stärker")),
    ("strong", 76, 100, ("Sterke markt", "Strong market", "Starker Markt")),
)
_FIELDS = ("min_benchmark_score", "max_benchmark_score")


def explicit_benchmark_bounds(text: str) -> dict[str, int]:
    """Read only a user's explicit combined-benchmark setup condition.

    This extractor does not infer a trading zone from a market description or
    from Smart DCA amount bands. It shares the preset boundaries used when
    presenting the saved setup back to the user.
    """
    request = " ".join(str(text or "").casefold().split())
    condition_cues = list(re.finditer(
        r"\b(?:koopzone|scorevoorwaarde|scorefilter|scoregrens|scorezone|"
        r"benchmarkvoorwaarde)\b", request,
    ))
    benchmark_cue = re.search(
        r"\b(?:benchmarkscore|totaalscore|total(?:e)? score)\b"
        r".{0,35}\b(?:tussen|van|moet)\b", request,
    )
    if not condition_cues and not benchmark_cue:
        return {}
    if not condition_cues and re.search(r"\b(?:smart\s*dca|staffel|basisbedrag)\b", request):
        return {}
    if re.search(r"\b(?:geen|zonder|no|without|ohne)\s+(?:extra\s+)?"
                 r"(?:scorevoorwaarde|scorefilter|scoregrens|koopzone)\b", request):
        return {}
    range_matches = list(re.finditer(
        r"\b(\d{1,3})\s*(?:-|–|—|tot(?:\s+en\s+met)?|to|bis)\s*(\d{1,3})\b",
        request,
    ))
    explicit_range = None
    cue = condition_cues[-1] if condition_cues else benchmark_cue
    range_match = min(
        range_matches,
        key=lambda match: min(abs(match.start() - cue.end()), abs(cue.start() - match.end())),
        default=None,
    )
    if range_match:
        minimum, maximum = map(int, range_match.groups())
        if 0 <= minimum <= maximum <= 100:
            explicit_range = {"min_benchmark_score": minimum, "max_benchmark_score": maximum}
    for _, minimum, maximum, labels in _BANDS:
        if any(re.search(r"(?<!\w)" + re.escape(label.casefold()) + r"(?!\w)", request)
               for label in labels):
            preset = {"min_benchmark_score": minimum, "max_benchmark_score": maximum}
            return preset if explicit_range is None or explicit_range == preset else {}
    if explicit_range is not None:
        return explicit_range
    return {}


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
