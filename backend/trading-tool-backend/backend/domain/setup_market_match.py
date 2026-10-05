"""Match an owner's saved setup conditions against measured benchmark components.

This is a read-only assessment of plan fit, never an entry or execution signal.
"""

from __future__ import annotations

from math import isfinite
from typing import Any, Mapping


COMPONENTS = ("macro", "technical", "market")


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) and 0 <= result <= 100 else None


def match_setup(
    setup: Mapping[str, Any], scores: Mapping[str, Any] | None,
    weights: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Return a score and status with explicit missing-data and rule boundaries."""
    conditions = {}
    for component in COMPONENTS:
        minimum = _number(setup.get(f"min_{component}_score"))
        maximum = _number(setup.get(f"max_{component}_score"))
        if minimum is not None or maximum is not None:
            conditions[component] = (minimum, maximum)

    result = {
        "setup_id": setup.get("id") or setup.get("setup_id"),
        "name": setup.get("name"),
        "symbol": setup.get("symbol"),
        "timeframe": setup.get("timeframe"),
        "setup_type": setup.get("setup_type"),
        "trend": setup.get("trend"),
        "action": setup.get("action"),
        "min_investment": setup.get("min_investment"),
        "tags": setup.get("tags"),
        "favorite": setup.get("favorite"),
        "setup_explanation": setup.get("explanation"),
        "score": None,
        "status": "unconfigured",
        "is_active": False,
        "is_best": False,
        "components": {},
        "reasons": [],
    }
    if not conditions:
        result["reasons"].append("Geen markt-, macro- of technische scorevoorwaarden opgeslagen.")
        return result
    if scores is None or any(_number(scores.get(component)) is None for component in COMPONENTS):
        result["status"] = "insufficient_data"
        result["reasons"].append("De actuele markt-, macro- en technische scores zijn niet volledig beschikbaar.")
        return result

    contributions = []
    for component, (minimum, maximum) in conditions.items():
        value = _number(scores[component])
        assert value is not None
        within = (minimum is None or value >= minimum) and (maximum is None or value <= maximum)
        if not within:
            result["reasons"].append(f"{component}: {value:g} valt buiten de opgeslagen voorwaarden.")
        if minimum is not None and value < minimum:
            proximity = max(0, min(59, 60 - 2 * (minimum - value)))
        elif maximum is not None and value > maximum:
            proximity = max(0, min(59, 60 - 2 * (value - maximum)))
        elif minimum is not None and maximum is not None and maximum > minimum:
            midpoint = (minimum + maximum) / 2
            proximity = 60 + 40 * (1 - abs(value - midpoint) / ((maximum - minimum) / 2))
        elif minimum is not None and maximum is None:
            proximity = 100 if minimum == 100 else 60 + 40 * (value - minimum) / (100 - minimum)
        elif maximum is not None and minimum is None:
            proximity = 100 if maximum == 0 else 60 + 40 * (maximum - value) / maximum
        else:
            proximity = 100
        weight = (weights or {}).get(f"{component}_score", 1 / 3)
        contributions.append((proximity, weight))
        result["components"][component] = {
            "score": value,
            "minimum": minimum,
            "maximum": maximum,
            "within_range": within,
            "match": round(proximity),
        }

    total_weight = sum(weight for _, weight in contributions)
    # A user may give a component zero benchmark weight while still using it
    # as a hard setup condition. Keep that condition assessable.
    result["score"] = round(
        sum(score * weight for score, weight in contributions) / total_weight
    ) if total_weight > 0 else round(sum(score for score, _ in contributions) / len(contributions))
    result["is_active"] = not result["reasons"]
    result["status"] = "matches" if result["is_active"] else "outside_conditions"
    return result


def match_setup_from_daily_scores(
    setup: Mapping[str, Any], scores: Mapping[str, Any],
    weights: Mapping[str, float] | None,
) -> dict[str, Any]:
    """Shared boundary for execution/report adapters that already read daily scores."""
    availability = scores.get("_source_available") or {}
    if not weights or any(availability.get(f"{key}_score") is not True for key in COMPONENTS):
        return match_setup(setup, None, weights)
    return match_setup(
        setup,
        {key: scores.get(key, scores.get(f"{key}_score")) for key in COMPONENTS},
        weights,
    )


def rank_matches(
    setups: list[Mapping[str, Any]], scores: Mapping[str, Any] | None,
    weights: Mapping[str, float] | None = None,
) -> list[dict[str, Any]]:
    matches = [match_setup(setup, scores, weights) for setup in setups]
    matches.sort(key=lambda item: (item["is_active"], item["score"] if item["score"] is not None else -1), reverse=True)
    winner = next((item for item in matches if item["is_active"]), None)
    if winner is not None:
        winner["is_best"] = True
    return matches
