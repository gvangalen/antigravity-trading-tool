"""Typed DCA amount contract shared by FINN proposal and strategy execution."""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

from backend.domain.benchmark_score_zones import benchmark_zone_step_boundaries


_AMOUNT_FIELDS = frozenset({
    "dca_amount_mode", "base_amount", "score_source", "low_threshold",
    "high_threshold", "low_score_percent", "mid_score_percent", "high_score_percent",
    "benchmark_zone_percents",
})
_SCORE_SOURCES = frozenset({"benchmark_score"})
_SCORE_BAND_PERCENT_RANGE = (5, 300)
_SCORE_BAND_INTERPOLATION = "step"
_TRIGGER_MODES = frozenset({"calendar", "benchmark"})
BENCHMARK_COMPONENTS = ("market_score", "macro_score", "technical_score")
EQUAL_BENCHMARK_WEIGHTS = {component: 1 / 3 for component in BENCHMARK_COMPONENTS}


def dca_automation_capabilities() -> dict[str, Any]:
    """Model-facing facts from the same limits used to validate saved DCA plans."""
    return {
        "supported_amount_modes": ("fixed", "score_bands"),
        "score_band_input": tuple(sorted(_SCORE_SOURCES)),
        "score_band_interpolation": _SCORE_BAND_INTERPOLATION,
        "score_band_percent_range": _SCORE_BAND_PERCENT_RANGE,
        "score_band_threshold_count": 4,
        "score_band_amount_count": 5,
        "score_band_boundaries": benchmark_zone_step_boundaries(),
        "legacy_score_band_amount_count": 3,
        "score_band_percent_order": "monotonic_in_either_direction",
        "score_band_percent_orders": ("nondecreasing", "nonincreasing"),
        "supported_trigger_modes": tuple(sorted(_TRIGGER_MODES)),
        "benchmark_trigger_cadence": "at_most_once_per_period_when_complete_score_is_available",
        "minimum_score_band_percent": _SCORE_BAND_PERCENT_RANGE[0],
        "automatic_sell_rule_in_dca_plan": False,
        "separate_setup_creation": True,
    }


def validate_dca_setup_only(fields: dict[str, Any]) -> None:
    """A confirmed DCA setup may have cadence and eligibility without an amount rule."""
    if fields.get("plan_scope") not in {None, "setup_only"} or fields.get("setup_type") != "dca":
        raise ValueError("dca_setup_only_scope_invalid")
    if any(fields.get(key) is not None for key in _AMOUNT_FIELDS):
        raise ValueError("dca_setup_only_cannot_have_strategy_amounts")
    if fields.get("dca_frequency") not in {"daily", "weekly", "monthly"}:
        raise ValueError("dca_frequency_required")
    trigger_mode = fields.get("dca_trigger_mode") or "calendar"
    if trigger_mode not in _TRIGGER_MODES:
        raise ValueError("dca_trigger_mode_invalid")
    if trigger_mode == "benchmark" and (fields.get("dca_day") or fields.get("dca_month_day")):
        raise ValueError("benchmark_trigger_cannot_have_calendar_day")
    if trigger_mode == "calendar" and fields["dca_frequency"] == "weekly" and not fields.get("dca_day"):
        raise ValueError("dca_day_required")
    if trigger_mode == "calendar" and fields["dca_frequency"] == "monthly" and not fields.get("dca_month_day"):
        raise ValueError("dca_month_day_required")


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
    trigger_mode = fields.get("dca_trigger_mode") or "calendar"
    if trigger_mode not in _TRIGGER_MODES:
        raise ValueError("dca_trigger_mode_invalid")
    if trigger_mode == "benchmark" and (fields.get("dca_day") or fields.get("dca_month_day")):
        raise ValueError("benchmark_trigger_cannot_have_calendar_day")
    if trigger_mode == "calendar" and fields.get("dca_frequency") == "weekly" and not fields.get("dca_day"):
        raise ValueError("dca_day_required")
    if trigger_mode == "calendar" and fields.get("dca_frequency") == "monthly" and not fields.get("dca_month_day"):
        raise ValueError("dca_month_day_required")
    if fields.get("dca_frequency") is not None and fields.get("dca_frequency") not in {"daily", "weekly", "monthly"}:
        raise ValueError("dca_frequency_required")
    setup_fields = {key: value for key, value in fields.items() if key not in _AMOUNT_FIELDS}
    if trigger_mode == "benchmark" and setup_fields.get("min_benchmark_score") is None and setup_fields.get("max_benchmark_score") is None:
        # A score-banded amount rule needs an assessable setup for every
        # complete benchmark score. The curve determines the amount; these
        # bounds let the Paper evaluator reach that curve.
        setup_fields["min_benchmark_score"] = 0
        setup_fields["max_benchmark_score"] = 100
    mode = fields.get("dca_amount_mode")
    strategy_fields: dict[str, Any] = {
        "name": f"{str(fields.get('name') or '').strip()} Strategy",
        "execution_mode": "fixed" if mode == "fixed" else "custom",
        "dca_amount_semantics": "planned_exact",
        "base_amount": _positive_amount(fields.get("base_amount"), "base_amount"),
    }

    if mode == "fixed":
        if trigger_mode == "benchmark":
            raise ValueError("benchmark_trigger_requires_score_bands")
        if any(fields.get(key) is not None for key in _AMOUNT_FIELDS - {"dca_amount_mode", "base_amount"}):
            raise ValueError("fixed_dca_cannot_have_score_bands")
    elif mode == "score_bands":
        source = fields.get("score_source")
        if source not in _SCORE_SOURCES:
            raise ValueError("benchmark_score_required")
        zone_percents = fields.get("benchmark_zone_percents")
        if zone_percents is not None:
            if any(fields.get(key) is not None for key in (
                "low_threshold", "high_threshold", "low_score_percent",
                "mid_score_percent", "high_score_percent",
            )):
                raise ValueError("score_band_formats_mixed")
            if not isinstance(zone_percents, (list, tuple)) or len(zone_percents) != 5:
                raise ValueError("benchmark_zone_percentages_invalid")
            percents = tuple(_positive_amount(value, "benchmark_zone_percent") for value in zone_percents)
            points = [
                {"x": boundary, "y": percent / 100}
                for boundary, percent in zip(benchmark_zone_step_boundaries(), percents)
            ]
        else:
            # Already saved three-band plans retain their exact decision curve.
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
            points = [
                {"x": 0, "y": percents[0] / 100},
                {"x": float(low), "y": percents[1] / 100},
                {"x": float(high), "y": percents[2] / 100},
                {"x": 100, "y": percents[2] / 100},
            ]
        if not all(_SCORE_BAND_PERCENT_RANGE[0] <= percent <= _SCORE_BAND_PERCENT_RANGE[1] for percent in percents) or not (
            all(left <= right for left, right in zip(percents, percents[1:]))
            or all(left >= right for left, right in zip(percents, percents[1:]))
        ):
            raise ValueError("score_band_percentages_invalid")
        multipliers = tuple(percent / 100 for percent in percents)
        strategy_fields["decision_curve"] = {
            "input": source,
            "weights_policy": "current_market_benchmark_weights",
            "interpolation": _SCORE_BAND_INTERPOLATION,
            "min_multiplier": _SCORE_BAND_PERCENT_RANGE[0] / 100,
            "max_multiplier": _SCORE_BAND_PERCENT_RANGE[1] / 100,
            "points": points,
        }
    else:
        raise ValueError("dca_amount_mode_required")

    minimum = setup_fields.get("min_investment")
    if minimum is not None:
        if type(minimum) not in {int, float} or not math.isfinite(minimum) or minimum < 0:
            raise ValueError("min_investment_must_be_nonnegative_finite")
        lowest = (strategy_fields["base_amount"] if mode == "fixed" else
                  strategy_fields["base_amount"] * min(multipliers))
        if minimum > lowest:
            raise ValueError("minimum_investment_exceeds_planned_amount")
    return setup_fields, strategy_fields


def is_confirmed_dca_amount_rule(strategy: dict[str, Any]) -> bool:
    """Accept the exact-amount exemption only for a valid saved amount rule.

    The JSON marker is user supplied on general strategy routes, so it cannot
    establish this exception by itself. Reconstruct the canonical curve before
    the decision and guardrail engines trust it.
    """
    if (str(strategy.get("setup_type") or "").lower() != "dca"
            or strategy.get("dca_amount_semantics") != "planned_exact"):
        return False
    mode = strategy.get("execution_mode")
    base = strategy.get("base_amount")
    if mode == "fixed":
        fields = {"setup_type": "dca", "dca_amount_mode": "fixed", "base_amount": base}
    elif mode == "custom":
        curve = strategy.get("decision_curve")
        if not isinstance(curve, dict):
            return False
        points = curve.get("points")
        if not isinstance(points, list) or len(points) not in {4, 5} or any(not isinstance(p, dict) for p in points):
            return False
        try:
            fields = {"setup_type": "dca", "dca_amount_mode": "score_bands",
                      "base_amount": base, "score_source": curve.get("input")}
            if len(points) == 5:
                fields["benchmark_zone_percents"] = [point["y"] * 100 for point in points]
            else:
                fields.update({
                    "low_threshold": points[1]["x"], "high_threshold": points[2]["x"],
                    "low_score_percent": points[0]["y"] * 100,
                    "mid_score_percent": points[1]["y"] * 100,
                    "high_score_percent": points[2]["y"] * 100,
                })
        except (KeyError, TypeError):
            return False
    else:
        return False
    try:
        _, canonical = split_confirmed_dca_plan(fields)
    except (ValueError, TypeError):
        return False
    if mode == "fixed":
        return not strategy.get("decision_curve") and math.isclose(float(base), canonical["base_amount"], abs_tol=0.005)
    return curve == canonical["decision_curve"] and math.isclose(float(base), canonical["base_amount"], abs_tol=0.005)


def dca_due_on_date(setup: dict[str, Any], report_date: date) -> bool:
    """Evaluate the saved setup cadence for a nominal local report date."""
    frequency = str(setup.get("dca_frequency") or "").lower()
    if setup.get("dca_trigger_mode") == "benchmark":
        return frequency in {"daily", "weekly", "monthly"}
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


def dca_execution_period(setup: dict[str, Any], report_date: date) -> tuple[date, date]:
    """Return the half-open local period used to enforce a saved DCA cadence."""
    frequency = str(setup.get("dca_frequency") or "").lower()
    if frequency == "weekly":
        start = report_date - timedelta(days=report_date.weekday())
        return start, start + timedelta(days=7)
    if frequency == "monthly":
        start = report_date.replace(day=1)
        end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
        return start, end
    return report_date, report_date + timedelta(days=1)
