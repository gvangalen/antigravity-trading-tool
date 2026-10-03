"""Typed DCA amount contract shared by FINN proposal and strategy execution."""

from __future__ import annotations

import math
from datetime import date
from typing import Any


_AMOUNT_FIELDS = frozenset({
    "dca_amount_mode", "base_amount", "score_source", "low_threshold",
    "high_threshold", "low_score_percent", "mid_score_percent", "high_score_percent",
})
_SCORE_SOURCES = frozenset({"benchmark_score"})
BENCHMARK_COMPONENTS = ("market_score", "macro_score", "technical_score")
EQUAL_BENCHMARK_WEIGHTS = {component: 1 / 3 for component in BENCHMARK_COMPONENTS}


def normalize_benchmark_weights(preferences: Any) -> dict[str, float] | None:
    """Match Analyse's missing-field defaults without accepting invalid weights."""
    if preferences is None or preferences == {}:
        return dict(EQUAL_BENCHMARK_WEIGHTS)
    if not isinstance(preferences, dict):
        return None
    values = {}
    for component in BENCHMARK_COMPONENTS:
        category = component.removesuffix("_score")
        value = preferences.get(category, 1 / 3)
        if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
            return None
        values[component] = float(value)
    total = sum(values.values())
    if total <= 0:
        return None
    return {component: value / total for component, value in values.items()}


def benchmark_score(scores: dict[str, Any], weights: dict[str, Any], availability: dict[str, Any]) -> float | None:
    """Require all three same-report components before sizing an automated order."""
    if set(weights or {}) != set(BENCHMARK_COMPONENTS):
        return None
    if any(availability.get(component) is not True for component in BENCHMARK_COMPONENTS):
        return None
    values = [scores.get(component) for component in BENCHMARK_COMPONENTS]
    factors = [weights[component] for component in BENCHMARK_COMPONENTS]
    if any(type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value <= 100 for value in values):
        return None
    if any(type(weight) not in {int, float} or not math.isfinite(weight) or weight < 0 for weight in factors):
        return None
    total = sum(factors)
    if total <= 0 or not math.isclose(total, 1, abs_tol=1e-6):
        return None
    return round(sum(value * weight for value, weight in zip(values, factors)), 1)


def _positive_amount(value: Any, field: str) -> float:
    if type(value) not in {int, float} or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field}_must_be_positive_finite")
    return round(float(value), 2)


def split_confirmed_dca_plan(fields: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate the visible amount rule and split one confirmed plan into two records.

    No score source, threshold, or amount is defaulted. A setup-only DCA draft
    cannot be confirmed as an executable plan.
    """
    if str(fields.get("setup_type") or "").lower() != "dca":
        raise ValueError("dca_setup_required")
    setup_fields = {key: value for key, value in fields.items() if key not in _AMOUNT_FIELDS}
    mode = fields.get("dca_amount_mode")
    strategy_fields: dict[str, Any] = {
        "name": f"{str(fields.get('name') or '').strip()} Strategy",
        "execution_mode": "fixed" if mode == "fixed" else "custom",
        "dca_amount_semantics": "planned_exact",
        "base_amount": _positive_amount(fields.get("base_amount"), "base_amount"),
    }

    if mode == "fixed":
        if any(fields.get(key) is not None for key in _AMOUNT_FIELDS - {"dca_amount_mode", "base_amount"}):
            raise ValueError("fixed_dca_cannot_have_score_bands")
    elif mode == "score_bands":
        source = fields.get("score_source")
        if source not in _SCORE_SOURCES:
            raise ValueError("benchmark_score_required")
        low = fields.get("low_threshold")
        high = fields.get("high_threshold")
        if (
            type(low) not in {int, float} or type(high) not in {int, float}
            or not math.isfinite(low) or not math.isfinite(high)
            or not 0 < low < high < 100
        ):
            raise ValueError("score_band_thresholds_invalid")
        percents = tuple(
            _positive_amount(fields.get(key), key)
            for key in ("low_score_percent", "mid_score_percent", "high_score_percent")
        )
        if not 5 <= percents[0] <= percents[1] <= percents[2] <= 300:
            raise ValueError("score_band_percentages_invalid")
        multipliers = tuple(percent / 100 for percent in percents)
        strategy_fields["decision_curve"] = {
            "input": source,
            "weights_policy": "current_user_preferences",
            "interpolation": "step",
            "min_multiplier": 0.05,
            "max_multiplier": 3.0,
            "points": [
                {"x": 0, "y": multipliers[0]},
                {"x": float(low), "y": multipliers[1]},
                {"x": float(high), "y": multipliers[2]},
                {"x": 100, "y": multipliers[2]},
            ],
        }
    else:
        raise ValueError("dca_amount_mode_required")

    minimum = setup_fields.get("min_investment")
    if minimum is not None:
        if type(minimum) not in {int, float} or not math.isfinite(minimum) or minimum < 0:
            raise ValueError("min_investment_must_be_nonnegative_finite")
        lowest = (strategy_fields["base_amount"] if mode == "fixed" else
                  strategy_fields["base_amount"] * multipliers[0])
        if minimum > lowest:
            raise ValueError("minimum_investment_exceeds_planned_amount")
    return setup_fields, strategy_fields


def dca_due_on_date(setup: dict[str, Any], report_date: date) -> bool:
    """Evaluate the saved setup cadence for a nominal local report date."""
    frequency = str(setup.get("dca_frequency") or "").lower()
    if frequency == "daily":
        return True
    if frequency == "weekly":
        saved_day = str(setup.get("dca_day") or "").lower()
        # SetupService stores ISO weekdays as strings ("1" is Monday),
        # while an unconfirmed FINN draft still has the weekday name.
        if saved_day.isdigit():
            return int(saved_day) == report_date.isoweekday()
        return saved_day == (
            "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
        )[report_date.weekday()]
    if frequency == "monthly":
        try:
            return int(setup.get("dca_month_day")) == report_date.day
        except (TypeError, ValueError):
            return False
    return False
