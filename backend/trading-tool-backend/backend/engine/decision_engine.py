from typing import Dict, Any

from backend.engine.curve_engine import calculate_position_size
from backend.domain.finn_dca_plan_contract import benchmark_score, is_confirmed_dca_amount_rule


class DecisionEngineError(Exception):
    pass


def decide_amount(
    setup: Dict[str, Any],
    scores: Dict[str, float],
) -> Dict[str, Any]:
    """
    Master allocation decision.

    Flow:
        1) Base sizing via curve_engine
        2) Setup conviction adjustment
        3) Return structured result; cash and exposure limits are applied
           separately by the bot guardrails.

    Decision engine rekent NOOIT zelf (alleen orkestratie).
    """

    if not setup:
        raise DecisionEngineError("Setup ontbreekt")
    if (setup.get("dca_amount_semantics") == "planned_exact"
            and not is_confirmed_dca_amount_rule(setup)):
        if (setup.get("execution_mode") == "custom"
                and (setup.get("decision_curve") or {}).get("input") != "benchmark_score"):
            raise DecisionEngineError("Smart DCA requires the total benchmark score")
        raise DecisionEngineError("Ongeldige DCA-bedragregel")

    base_amount = setup.get("base_amount")
    execution_mode = setup.get("execution_mode", "fixed")

    if not isinstance(base_amount, (int, float)) or base_amount <= 0:
        raise DecisionEngineError("Ongeldig base_amount")

    # =================================================
    # 1️⃣ Base Position Size
    # =================================================

    if execution_mode == "fixed":

        sized_amount = float(base_amount)

    elif execution_mode == "custom":

        curve = setup.get("decision_curve")
        if not curve:
            raise DecisionEngineError("Custom mode vereist decision_curve")

        input_key = curve.get("input", "market_score")
        if (
            setup.get("setup_type") == "dca"
            and setup.get("dca_amount_semantics") == "planned_exact"
            and input_key != "benchmark_score"
        ):
            raise DecisionEngineError("Smart DCA requires the total benchmark score")
        if input_key == "benchmark_score" and curve.get("weights_policy") not in {
            "current_user_preferences", "current_market_benchmark_weights",
        }:
            raise DecisionEngineError("Benchmark requires current preference weights")
        score_value = (
            benchmark_score(scores, scores.get("_benchmark_weights") or {}, scores.get("_source_available") or {})
            if input_key == "benchmark_score" else scores.get(input_key)
        )

        if not isinstance(score_value, (int, float)):
            raise DecisionEngineError(
                f"Score '{input_key}' ontbreekt of ongeldig"
            )

        sized_amount = calculate_position_size(
            base_amount=base_amount,
            curve=curve,
            score=score_value,
            min_multiplier=curve.get("min_multiplier", 0.1),
            max_multiplier=curve.get("max_multiplier", 3.0),
        )

    else:
        raise DecisionEngineError(
            f"Onbekende execution_mode: {execution_mode}"
        )

    # =================================================
    # Setup match is eligibility only. Proximity inside a saved score band is
    # not conviction and must never silently change the order amount.
    # =================================================

    exact_dca_amount = is_confirmed_dca_amount_rule(setup)
    if exact_dca_amount:
        setup_reason = "DCA planned amount; setup conviction cannot raise or lower its score band"
    else:
        setup_reason = "Setup match is an eligibility check, not a size multiplier"

    # 🔥 FIX: clamp sized_amount (voorkomt extremes)
    max_planned_multiplier = (
        float((setup.get("decision_curve") or {}).get("max_multiplier", 3.0))
        if exact_dca_amount else 2.0
    )
    sized_amount = max(0.0, min(float(sized_amount), float(base_amount) * max_planned_multiplier))

    sized_amount = round(float(sized_amount), 2)

    return {
        "base_amount": round(float(base_amount), 2),
        "sized_amount": sized_amount,
        "exposure_multiplier": 1.0,
        "final_amount": sized_amount,
        "risk_mode": None,
        "exposure_reason": None,
        "exposure_components": {},
        "setup_reason": setup_reason,
    }
