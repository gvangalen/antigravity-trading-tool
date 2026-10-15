"""Fail-closed limits and ordered, user-readable reasons for bot buy proposals."""

import logging
import math
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)

BLOCK_REASON_LABELS = {
    "kill_switch": "De bot is gepauzeerd. Er wordt geen kooporder geplaatst.",
    "daily_allocation": "De ingestelde daglimiet is al bereikt.",
    "asset_exposure": "De ingestelde maximale blootstelling aan deze asset is bereikt.",
    "no_allocatable_size": "Er blijft geen geldig koopbedrag over.",
    "total_budget": "Het totale botbudget is al gebruikt.",
    "insufficient_funds": "Er is geen beschikbaar kassaldo voor deze kooporder.",
    "below_min_order": "Het bedrag dat binnen de limieten past, ligt onder de minimumorder.",
    "guardrails_error": "De veiligheidscheck kon niet betrouwbaar worden uitgevoerd. De kooporder is geblokkeerd.",
}


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else fallback
    except (TypeError, ValueError):
        return fallback


def _safe_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return fallback
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "active"}
    return bool(value)


def _round_money(value: float) -> float:
    return round(float(value), 2)


def _finite_number(value: Any, *, optional: bool = False) -> Optional[float]:
    if value is None and optional:
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError("Guardrail input must be finite and nonnegative")
    return number


def _calculate_exposure_pct(*, current_asset_value_eur: float, portfolio_value_eur: float) -> float:
    if portfolio_value_eur <= 0:
        return 0.0
    return round(current_asset_value_eur / portfolio_value_eur * 100.0, 2)


def _calculate_remaining_asset_capacity(
    *, portfolio_value_eur: float, current_asset_value_eur: float,
    max_asset_exposure_pct: float,
) -> float:
    return max(portfolio_value_eur * max_asset_exposure_pct / 100.0 - current_asset_value_eur, 0.0)


def apply_guardrails(
    *,
    proposed_amount_eur: float,
    portfolio_value_eur: float = 0.0,
    current_asset_value_eur: float = 0.0,
    invested_eur: float = 0.0,
    today_allocated_eur: float = 0.0,
    cash_balance_eur: float = 0.0,
    kill_switch: bool = True,
    max_trade_risk_eur: Optional[float] = None,
    daily_allocation_eur: Optional[float] = None,
    max_asset_exposure_pct: Optional[float] = None,
    total_budget_eur: Optional[float] = None,
    min_order_eur: Optional[float] = None,
    backtest_mode: bool = False,
    global_macro_score: Optional[float] = None,
) -> Dict[str, Any]:
    """Cap a buy proposal. Explicit zero exposure disallows any new buy."""
    try:
        original = _finite_number(proposed_amount_eur)
        portfolio = _finite_number(portfolio_value_eur)
        asset = _finite_number(current_asset_value_eur)
        invested = _finite_number(invested_eur)
        today = _finite_number(today_allocated_eur)
        cash = _finite_number(cash_balance_eur)
        max_order = _finite_number(max_trade_risk_eur, optional=True)
        daily = _finite_number(daily_allocation_eur, optional=True)
        exposure = _finite_number(max_asset_exposure_pct, optional=True)
        budget = _finite_number(total_budget_eur, optional=True)
        minimum = _finite_number(min_order_eur, optional=True)
        macro = _finite_number(global_macro_score, optional=True)
        if exposure is not None and exposure > 100:
            raise ValueError("Invalid asset exposure")
        if macro is not None and macro > 100:
            raise ValueError("Invalid macro score")
    except (TypeError, ValueError, OverflowError):
        logger.warning("Guardrail input invalid; blocking proposal")
        return {
            "allowed": False, "adjusted_amount_eur": 0.0,
            "original_amount_eur": _round_money(_safe_float(proposed_amount_eur)),
            "warnings": ["guardrails_error"], "blocked_by": "guardrails_error",
            "reason": BLOCK_REASON_LABELS["guardrails_error"],
            "debug_code": "guardrails_error", "guardrails": {},
            "explanations": [{"code": "guardrails_error", "message": BLOCK_REASON_LABELS["guardrails_error"]}],
        }

    original = _round_money(original)
    adjusted = original
    warnings = []
    explanations = []
    limits = {
        "kill_switch": _safe_bool(kill_switch, True),
        "cash_balance_eur": _round_money(cash),
        "max_trade_risk_eur": _round_money(max_order) if max_order is not None else None,
        "daily_allocation_eur": _round_money(daily) if daily is not None else None,
        "remaining_daily_eur": _round_money(max(daily - today, 0)) if daily else None,
        "max_asset_exposure_pct": exposure if exposure is not None else 100.0,
        "current_asset_exposure_pct": _calculate_exposure_pct(
            current_asset_value_eur=asset, portfolio_value_eur=portfolio),
        "remaining_asset_capacity_eur": (
            _round_money(_calculate_remaining_asset_capacity(
                portfolio_value_eur=portfolio, current_asset_value_eur=asset,
                max_asset_exposure_pct=exposure)) if exposure is not None else None),
        "total_budget_eur": _round_money(budget) if budget is not None else None,
        "invested_eur": _round_money(invested),
        "remaining_budget_eur": _round_money(max(budget - invested, 0)) if budget else None,
        "min_order_eur": _round_money(minimum) if minimum is not None else None,
    }

    def finish(blocked_by=None):
        allowed = blocked_by is None and adjusted > 0
        if blocked_by:
            message = BLOCK_REASON_LABELS[blocked_by]
            explanations.append({"code": blocked_by, "message": message})
        elif explanations:
            message = " ".join(item["message"] for item in explanations)
        elif allowed:
            message = "Het voorgestelde bedrag past binnen de ingestelde limieten."
        else:
            message = "Er is voor deze beslissing geen koopvoorstel."
        return {
            "allowed": allowed,
            "adjusted_amount_eur": _round_money(adjusted) if allowed else 0.0,
            "original_amount_eur": original,
            "warnings": warnings, "blocked_by": blocked_by,
            "reason": message, "debug_code": blocked_by,
            "guardrails": limits, "explanations": explanations,
        }

    def trim(code, capacity, message):
        nonlocal adjusted
        capacity = _round_money(max(capacity, 0))
        if adjusted > capacity:
            previous = adjusted
            adjusted = capacity
            warnings.append(code)
            explanations.append({
                "code": code, "message": message,
                "from_amount_eur": previous, "to_amount_eur": adjusted,
            })

    # Hold is a normal no-proposal state, not a safety failure.
    if original <= 0:
        return finish()
    if not limits["kill_switch"]:
        warnings.append("kill_switch_off")
        return finish("kill_switch")
    if not backtest_mode:
        if cash <= 0:
            warnings.append("insufficient_funds")
            return finish("insufficient_funds")
        trim("cash_balance_trimmed", cash,
             f"Beschikbaar kassaldo: €{cash:.2f}. Het koopbedrag is daarop verlaagd.")
        if macro is not None and macro < 35:
            trim("defensive_macro_override_active", adjusted * 0.2,
                 f"De macroscore is {macro:g} (onder 35). Het koopbedrag is defensief verlaagd tot 20%.")
        if budget is not None and budget > 0:
            remaining = max(budget - invested, 0)
            if remaining <= 0:
                warnings.append("total_budget_reached")
                return finish("total_budget")
            trim("total_budget_trimmed", remaining,
                 f"Van het totale botbudget is nog €{remaining:.2f} beschikbaar.")

    if max_order is not None and max_order > 0:
        trim("max_trade_risk_trimmed", max_order,
             f"De maximale ordergrootte is €{max_order:.2f}.")
    if daily is not None and daily > 0:
        remaining = max(daily - today, 0)
        if remaining <= 0:
            warnings.append("daily_allocation_reached")
            return finish("daily_allocation")
        trim("daily_allocation_trimmed", remaining,
             f"Van de daglimiet is nog €{remaining:.2f} beschikbaar.")
    if exposure is not None:
        if exposure == 0:
            warnings.append("asset_exposure_limit_reached")
            return finish("asset_exposure")
        if portfolio <= 0:
            warnings.append("guardrails_error")
            return finish("guardrails_error")
        remaining = _calculate_remaining_asset_capacity(
            portfolio_value_eur=portfolio, current_asset_value_eur=asset,
            max_asset_exposure_pct=exposure)
        if remaining <= 0:
            warnings.append("asset_exposure_limit_reached")
            return finish("asset_exposure")
        trim("asset_exposure_trimmed", remaining,
             f"Binnen de assetlimiet van {exposure:g}% past nog €{remaining:.2f}.")

    adjusted = _round_money(adjusted)
    if adjusted <= 0:
        return finish("no_allocatable_size")
    if not backtest_mode and minimum is not None and minimum > 0 and adjusted < minimum:
        warnings.append("below_min_order_size")
        explanations.append({
            "code": "below_min_order_size",
            "message": f"De minimumorder is €{minimum:.2f}; binnen de limieten past slechts €{adjusted:.2f}.",
        })
        return finish("below_min_order")
    return finish()
