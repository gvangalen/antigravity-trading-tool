from __future__ import annotations

import logging
import math
from datetime import date
from typing import Any, Dict, Optional

from backend.engine.position_engine import calculate_position
from backend.domain.finn_dca_plan_contract import benchmark_score, is_confirmed_dca_amount_rule
from backend.engine.guardrails_engine import apply_guardrails
from backend.engine.trade_plan_engine import build_trade_plan

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# =========================================================
# Config
# =========================================================

DEFAULT_ACTION_RULES = {
    "min_confidence_to_buy": 60.0,
    "min_confidence_to_watch": 40.0,
    "min_market_score_to_buy": 55.0,
    "entry_tolerance_pct": 0.01,   # 1% boven entry nog ok
    "chase_limit_pct": 0.03,       # >3% boven entry = niet jagen
}

EXPOSURE_CAP = 1.0


# =========================================================
# Helpers
# =========================================================

def _safe_float(x: Any, fallback: Optional[float] = None) -> Optional[float]:
    try:
        if x is None:
            return fallback
        return float(x)
    except Exception:
        return fallback


def _safe_str(x: Any, fallback: str = "") -> str:
    if x is None:
        return fallback
    return str(x).strip()


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(x, hi))


def _normalize_scores(scores: Dict[str, Any]) -> Dict[str, Any]:
    availability = scores.get("_source_available") or {}

    def measured(name: str) -> Optional[float]:
        raw = scores.get(name, scores.get(name.removesuffix("_score")))
        if name in availability and availability[name] is not True:
            return None
        if isinstance(raw, bool):
            return None
        value = _safe_float(raw)
        return value if value is not None and math.isfinite(value) and 0 <= value <= 100 else None

    return {
        "macro_score": measured("macro_score"),
        "technical_score": measured("technical_score"),
        "market_score": measured("market_score"),
        # A missing setup match has no sizing effect; it is not a score of 50.
        "setup_score": measured("setup_score"),
        "_source_available": availability,
        "_benchmark_weights": scores.get("_benchmark_weights") or {},
    }


def _normalize_setup_type(setup: Dict[str, Any], snapshot: Dict[str, Any]) -> str:
    """
    SINGLE SOURCE OF TRUTH:
    - Alleen setup_type gebruiken (komt uit strategies tabel)
    - NOOIT fallback naar oude velden (strategy_type etc.)
    - Output altijd: 'dca', 'trade' of 'unknown'
    """

    raw = (
        snapshot.get("setup_type")
        or setup.get("setup_type")
    )

    setup_type = _safe_str(raw).lower()

    # 🔒 harde validatie (DB constraint aligned)
    if setup_type in {"dca", "trade"}:
        return setup_type

    # fallback = unknown (nooit silent misinterpretatie)
    return "unknown"


def _extract_snapshot(portfolio_context: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = portfolio_context.get("active_strategy") or portfolio_context.get("strategy_snapshot") or {}
    return snapshot if isinstance(snapshot, dict) else {}


def _extract_levels(setup: Dict[str, Any], snapshot: Dict[str, Any]) -> Dict[str, Any]:
    entry = _safe_float(snapshot.get("entry"), _safe_float(setup.get("entry")))
    stop_loss = _safe_float(snapshot.get("stop_loss"), _safe_float(setup.get("stop_loss")))

    raw_targets = snapshot.get("targets")
    if raw_targets is None:
        raw_targets = setup.get("targets") or []

    if not isinstance(raw_targets, list):
        raw_targets = []

    targets = []
    for t in raw_targets:
        tv = _safe_float(t)
        if tv is not None:
            targets.append(tv)

    return {
        "entry": entry,
        "stop_loss": stop_loss,
        "targets": targets,
    }


def _build_fallback_trade_plan(
    *,
    symbol: str,
    action: str,
    levels: Dict[str, Any],
    reason: str,
) -> Dict[str, Any]:
    entry = levels.get("entry")
    stop = levels.get("stop_loss")
    targets = levels.get("targets") or []

    entry_plan = []
    if entry is not None:
        entry_plan.append({
            "type": "reference",
            "label": "Primary entry",
            "price": entry,
        })

    formatted_targets = []
    for i, t in enumerate(targets):
        formatted_targets.append({
            "label": f"TP{i+1}",
            "price": t,
        })

    return {
        "symbol": (symbol or "BTC").upper(),
        "side": (action or "hold").lower(),
        "entry_plan": entry_plan,
        "stop_loss": {"price": stop},
        "targets": formatted_targets,
        "position": {"units": None},
        "risk": {
            "risk_per_unit": None,
            "reward_per_unit": None,
            "risk_eur": None,
            "rr": None,
            "regime": None,
            "note": reason,
        },
    }


def _build_action_decision(
    *,
    setup_type: str,
    snapshot: Dict[str, Any],
    levels: Dict[str, Any],
    normalized_scores: Dict[str, Any],
    rules: Dict[str, float],
    live_price: Optional[float],
    final_amount: float,
    planned_dca_amount: bool = False,
    confirmed_trade_match: bool = False,
    saved_trade_match_status: Optional[str] = None,
) -> Dict[str, Any]:
    confidence_score = _safe_float(
        snapshot.get("confidence_score") or snapshot.get("confidence"),
        0.0
    ) or 0.0
    market_score = normalized_scores.get("market_score")
    technical_score = normalized_scores.get("technical_score")

    entry = levels.get("entry")
    stop_loss = levels.get("stop_loss")
    targets = levels.get("targets") or []

    min_confidence_to_buy = _safe_float(rules.get("min_confidence_to_buy"), 60.0) or 60.0
    min_confidence_to_watch = _safe_float(rules.get("min_confidence_to_watch"), 40.0) or 40.0
    min_market_score_to_buy = _safe_float(rules.get("min_market_score_to_buy"), 55.0) or 55.0
    entry_tolerance_pct = _safe_float(rules.get("entry_tolerance_pct"), 0.01) or 0.01
    chase_limit_pct = _safe_float(rules.get("chase_limit_pct"), 0.03) or 0.03

    if final_amount <= 0:
        return {
            "action": "hold",
            "reason": "No executable size from position engine",
            "intent_note": "Position sizing returned zero",
            "confidence_score": confidence_score,
        }

    if setup_type == "dca" and planned_dca_amount:
        # The confirmed cadence and score band already define the purchase
        # intent. Generic trade confidence/market gates must not silently
        # turn a low-score DCA band into a hold. Cash, budget, exposure and
        # kill-switch limits are still applied by guardrails below.
        return {
            "action": "buy",
            "reason": "Scheduled DCA amount selected from the confirmed plan",
            "intent_note": "Pending independent cash and risk guardrails",
            "confidence_score": confidence_score,
        }

    if setup_type == "trade" and saved_trade_match_status and not confirmed_trade_match:
        reasons = {
            "outside_conditions": "Opgeslagen setupvoorwaarden passen niet bij de actuele benchmark.",
            "insufficient_data": "Actuele benchmarkgegevens zijn onvoldoende voor deze trade.",
            "unconfigured": "Deze setup heeft geen beoordeelbare scorevoorwaarden.",
        }
        return {
            "action": "hold", "reason": reasons.get(saved_trade_match_status, "Setupmatch is niet bevestigd."),
            "intent_note": "Controleer de opgeslagen scorevoorwaarden.",
            "confidence_score": confidence_score,
        }

    if confidence_score < min_confidence_to_watch and not confirmed_trade_match:
        return {
            "action": "hold",
            "reason": f"Confidence too low ({confidence_score:.1f})",
            "intent_note": "Snapshot confidence below watch threshold",
            "confidence_score": confidence_score,
        }

    if market_score is None:
        return {
            "action": "hold",
            "reason": "Verified market score unavailable",
            "intent_note": "Wait for current Score 2.0 market evidence",
            "confidence_score": confidence_score,
        }

    if market_score is not None and market_score < min_market_score_to_buy:
        return {
            "action": "hold",
            "reason": f"Market score too weak ({market_score:.1f})",
            "intent_note": "Market score below buy threshold",
            "confidence_score": confidence_score,
        }

    if setup_type == "dca":
        if confidence_score >= min_confidence_to_buy:
            return {
                "action": "buy",
                "reason": f"DCA strategy active with strong confidence ({confidence_score:.1f})",
                "intent_note": "Scheduled DCA selected as active strategy",
                "confidence_score": confidence_score,
            }

        return {
            "action": "hold",
            "reason": f"DCA active but confidence not strong enough ({confidence_score:.1f})",
            "intent_note": "Wait for cleaner conditions",
            "confidence_score": confidence_score,
        }

    if setup_type == "trade":
        if entry is None or stop_loss is None or not targets:
            return {
                "action": "hold",
                "reason": "Trade strategy missing entry/stop/targets",
                "intent_note": "Snapshot levels incomplete",
                "confidence_score": confidence_score,
            }

        if live_price is None:
            return {
                "action": "observe",
                "reason": "Trade setup ready, waiting for live price",
                "intent_note": "No live price available",
                "confidence_score": confidence_score,
            }

        upper_buy_zone = entry * (1.0 + entry_tolerance_pct)
        chase_limit = entry * (1.0 + chase_limit_pct)

        if live_price < entry:
            return {
                "action": "observe",
                "reason": f"Trade setup valid, waiting for entry zone ({entry:.2f})",
                "intent_note": f"Live price {live_price:.2f} still below entry",
                "confidence_score": confidence_score,
            }

        if entry <= live_price <= upper_buy_zone and (confirmed_trade_match or confidence_score >= min_confidence_to_buy):
            return {
                "action": "buy",
                "reason": f"Trade setup confirmed near entry ({live_price:.2f} vs {entry:.2f})",
                "intent_note": (
                    f"Technical={technical_score:.1f}, market={market_score:.1f}"
                    if technical_score is not None else f"Market={market_score:.1f}; technical unavailable"
                ),
                "confidence_score": confidence_score,
            }

        if upper_buy_zone < live_price <= chase_limit:
            return {
                "action": "observe",
                "reason": f"Price extended above entry but still near zone ({live_price:.2f})",
                "intent_note": "Wait for controlled pullback or renewed confirmation",
                "confidence_score": confidence_score,
            }

        return {
            "action": "hold",
            "reason": f"Price too extended above entry ({live_price:.2f})",
            "intent_note": "Do not chase trade",
            "confidence_score": confidence_score,
        }

    return {
        "action": "hold",
        "reason": f"Unknown setup type: {setup_type}",
        "intent_note": "No valid execution model",
        "confidence_score": confidence_score,
    }


# =========================================================
# Core brain
# =========================================================

def run_bot_brain(
    *,
    user_id: int,
    setup: Dict[str, Any],
    scores: Dict[str, Any],
    action_rules: Optional[Dict[str, float]] = None,
    portfolio_context: Optional[Dict[str, Any]] = None,
    backtest_mode: bool = False,
) -> Dict[str, Any]:
    portfolio_context = portfolio_context or {}
    setup = setup or {}
    scores = scores or {}

    rules = {**DEFAULT_ACTION_RULES, **(action_rules or {})}
    normalized_scores = _normalize_scores(scores)

    snapshot = _extract_snapshot(portfolio_context)
    setup_type = _normalize_setup_type(setup, snapshot)

    # The bot's score context is the owner- and asset-scoped Score 2.0
    # snapshot. Old user-wide regime memory and historical daily-score
    # overlays must not decide eligibility or silently alter order size.
    verified_benchmark = benchmark_score(
        normalized_scores,
        normalized_scores.get("_benchmark_weights") or {},
        normalized_scores.get("_source_available") or {},
    )
    score_evidence_complete = verified_benchmark is not None
    market_intelligence = {
        "source_status": "available" if score_evidence_complete else "insufficient_score_evidence",
        "source": "score_2_0",
        "benchmark_score": verified_benchmark,
    }

    # -------------------------------------------------
    # 3️⃣ Position Engine
    # -------------------------------------------------
    try:
        position = calculate_position(
            setup=setup,
            scores=normalized_scores,
        )

        base_amount = _safe_float(position.get("base_amount"), 0.0) or 0.0
        suggested_amount = _safe_float(position.get("final_amount"), 0.0) or 0.0
        position_size = _safe_float(position.get("position_size"), 0.0) or 0.0
        exposure_multiplier = _safe_float(position.get("exposure_multiplier"), 1.0) or 1.0
        decision_result = position.get("raw") or {}
        base_reason = decision_result.get("setup_reason") or "Position engine result"

        logger.info(
            "📊 PositionEngine result | setup_type=%s | base=%.2f final=%.2f size=%.3f exposure=%.2f",
            setup_type or "unknown",
            base_amount,
            suggested_amount,
            position_size,
            exposure_multiplier,
        )

    except Exception as e:
        logger.warning("PositionEngine fallback triggered: %s", e)
        base_amount = 0.0
        suggested_amount = 0.0
        position_size = 0.0
        exposure_multiplier = 1.0
        decision_result = {}
        base_reason = f"PositionEngine fallback: {e}"

    # -------------------------------------------------
    # 4️⃣ Levels from snapshot (source of truth)
    # -------------------------------------------------
    levels = _extract_levels(setup, snapshot)
    entry_value = levels["entry"]
    stop_value = levels["stop_loss"]
    clean_targets = levels["targets"]

    live_price = _safe_float(
        portfolio_context.get("live_price")
        or portfolio_context.get("current_price")
    )

    monitoring = (
        entry_value is not None
        or stop_value is not None
        or bool(clean_targets)
    )
    alerts_active = monitoring

    # -------------------------------------------------
    # 6️⃣ Action Decision
    # -------------------------------------------------
    setup_result = _build_action_decision(
        setup_type=setup_type,
        snapshot=snapshot,
        levels=levels,
        normalized_scores=normalized_scores,
        rules=rules,
        live_price=live_price,
        final_amount=suggested_amount,
        planned_dca_amount=is_confirmed_dca_amount_rule(setup),
        confirmed_trade_match=(
            setup_type == "trade"
            and setup.get("confirmed_trade_match") is True
            and score_evidence_complete
        ),
        saved_trade_match_status=setup.get("saved_trade_match_status"),
    )
    if (
        setup_type == "dca"
        and setup.get("dca_amount_semantics") == "planned_exact"
        and setup.get("execution_mode") == "custom"
    ):
        score_source = (setup.get("decision_curve") or {}).get("input")
        source_availability = scores.get("_source_available") or {}
        if score_source == "benchmark_score":
            score_ready = benchmark_score(
                normalized_scores,
                scores.get("_benchmark_weights") or {},
                source_availability,
            ) is not None
        else:
            score_ready = False
        if not score_ready:
            # No verified benchmark means no score-selected purchase amount.
            suggested_amount = 0.0
            position_size = 0.0
            unsupported_source = score_source != "benchmark_score"
            setup_result = {
                "action": "hold",
                "reason": (
                    "Smart DCA requires the total benchmark score"
                    if unsupported_source else "Smart DCA score for this report date is unavailable"
                ),
                "intent_note": (
                    "Update the old market-only Smart DCA plan before buying"
                    if unsupported_source else "No verified score for the selected amount band"
                ),
                "confidence_score": 0.0,
            }

    action = setup_result.get("action", "hold")
    strategy_reason = setup_result.get("reason", "No setup reason")
    setup_intent_note = setup_result.get("intent_note", "")
    confidence_score = _safe_float(setup_result.get("confidence_score"), 0.0) or 0.0
    if (setup_type == "dca" and setup.get("dca_amount_semantics") == "planned_exact"
            and not is_confirmed_dca_amount_rule(setup)):
        # Old or directly written malformed amount rules must never fall
        # through to ordinary DCA sizing or bypass the execution guardrail.
        action = "hold"
        suggested_amount = 0.0
        position_size = 0.0
        strategy_reason = (
            "Smart DCA requires the total benchmark score"
            if setup.get("execution_mode") == "custom"
            and (setup.get("decision_curve") or {}).get("input") != "benchmark_score"
            else "Invalid saved DCA amount rule"
        )
        setup_intent_note = "Review the saved DCA plan before execution"
        confidence_score = 0.0

    # Snapshot confidence is the only confidence source. A missing value is
    # not reconstructed from old regime or market-pressure estimates.
    if confidence_score <= 0:
        confidence = 0.0
    else:
        confidence = round(_clamp(confidence_score / 100.0, 0.0, 1.0), 3)

    # -------------------------------------------------
    # 7️⃣ Guardrails
    # -------------------------------------------------
    try:
        proposed_amount = suggested_amount if action == "buy" else 0.0
        # A confirmed DCA plan already encodes the score policy in its fixed
        # amount or benchmark curve. Do not apply the generic trade macro
        # multiplier again; cash, budget, exposure and kill-switch still apply.
        planned_dca = is_confirmed_dca_amount_rule(setup)
        macro_score_for_guardrail = None if planned_dca else normalized_scores.get("macro_score")

        guardrails_result = apply_guardrails(
            proposed_amount_eur=proposed_amount,
            portfolio_value_eur=_safe_float(portfolio_context.get("portfolio_value_eur"), 0.0) or 0.0,
            current_asset_value_eur=_safe_float(portfolio_context.get("current_asset_value_eur"), 0.0) or 0.0,
            invested_eur=_safe_float(portfolio_context.get("invested_eur"), 0.0) or 0.0,
            today_allocated_eur=_safe_float(portfolio_context.get("today_allocated_eur"), 0.0) or 0.0,
            cash_balance_eur=_safe_float(portfolio_context.get("cash_balance_eur"), 0.0) or 0.0,
            kill_switch=portfolio_context.get("kill_switch", True),
            max_trade_risk_eur=_safe_float(
                portfolio_context.get("max_trade_risk_eur") if portfolio_context.get("max_trade_risk_eur") is not None
                else setup.get("max_risk_per_trade"),
                None,
            ),
            daily_allocation_eur=_safe_float(portfolio_context.get("daily_allocation_eur"), None),
            max_asset_exposure_pct=_safe_float(portfolio_context.get("max_asset_exposure_pct"), None),
            total_budget_eur=_safe_float(portfolio_context.get("total_budget_eur"), None),
            min_order_eur=_safe_float(portfolio_context.get("min_order_eur"), None),
            backtest_mode=backtest_mode,
            global_macro_score=macro_score_for_guardrail,
        )

    except Exception:
        logger.exception("Guardrails failed; blocking buy proposal")
        guardrails_result = {
            "allowed": False,
            "adjusted_amount_eur": 0.0,
            "original_amount_eur": round(float(suggested_amount), 2),
            "warnings": ["guardrails_error"],
            "blocked_by": "guardrails_error",
            "reason": "De veiligheidscheck kon niet betrouwbaar worden uitgevoerd. De kooporder is geblokkeerd.",
            "debug_code": "guardrails_error",
            "guardrails": {},
            "explanations": [{"code": "guardrails_error", "message": "De veiligheidscheck kon niet betrouwbaar worden uitgevoerd. De kooporder is geblokkeerd."}],
        }

    adjusted_amount = _safe_float(
        guardrails_result.get("adjusted_amount_eur"),
        suggested_amount,
    ) or 0.0
    if guardrails_result.get("allowed") is not True:
        adjusted_amount = 0.0
    if is_confirmed_dca_amount_rule(setup):
        adjusted_amount = (
            max(0.0, min(adjusted_amount, suggested_amount))
            if action == "buy" and guardrails_result.get("allowed") is True else 0.0
        )

    guardrail_reason = (
        guardrails_result.get("blocked_by")
        or guardrails_result.get("reason")
        or (
            guardrails_result.get("warnings")[0]
            if guardrails_result.get("warnings")
            else None
        )
    )

    if action == "buy" and adjusted_amount <= 0:
        action = "hold"
        if guardrail_reason:
            strategy_reason = f"{strategy_reason} Blocked by guardrails: {guardrail_reason}"
        else:
            strategy_reason = f"{strategy_reason} Blocked by guardrails."

    # -------------------------------------------------
    # 8️⃣ Position size split
    # -------------------------------------------------
    intent_position_size = round(_clamp(position_size, 0.0, EXPOSURE_CAP), 3)

    execution_position_size = 0.0
    if base_amount > 0:
        execution_position_size = round(
            _clamp(adjusted_amount / base_amount, 0.0, EXPOSURE_CAP),
            3,
        )

    # -------------------------------------------------
    # 9️⃣ 🔥 CONTEXT (GEEN SCORE)
    # -------------------------------------------------
    trade_context = {
        "benchmark_score_reference": verified_benchmark,
        "setup_score_reference": normalized_scores.get("setup_score"),
    }

    # -------------------------------------------------
    # 🔟 Trade Plan
    # -------------------------------------------------
    snapshot_payload = {
        "entry": entry_value,
        "stop_loss": stop_value,
        "targets": clean_targets,
    }

    decision_payload = {
        "action": action,
        "symbol": (
            setup.get("symbol")
            or snapshot.get("symbol")
            or portfolio_context.get("symbol")
            or "BTC"
        ),
        "live_price": live_price,
    }

    bot_payload = {
        "min_rr": _safe_float(setup.get("min_rr"), 1.5) or 1.5,
        "max_risk_per_trade": _safe_float(
            portfolio_context.get("max_trade_risk_eur")
            or setup.get("max_risk_per_trade"),
            None,
        ),
        "strategy_type": setup_type,
    }

    brain_context = {
        "regime": None,
        "reason": strategy_reason,
    }

    try:
        trade_plan = build_trade_plan(
            snapshot=snapshot_payload,
            brain=brain_context,
            decision=decision_payload,
            bot=bot_payload,
        )
    except Exception as e:
        logger.warning("Trade plan engine error: %s", e)
        trade_plan = None

    # -------------------------------------------------
    # Final output
    # -------------------------------------------------
    return {
        "date": date.today().isoformat(),
        "action": action,
        "amount_eur": round(float(adjusted_amount), 2),
        "confidence": confidence,
        "reason": strategy_reason,

        "setup_type": setup_type,
        "setup_intent_note": setup_intent_note,

        "regime": None,
        "cycle": None,
        "temperature": None,

        "trend": {
            "short": None,
            "mid": None,
            "long": None,
        },

        "market_pressure": None,
        "transition_risk": None,
        "volatility_state": None,
        "trend_strength": None,
        "structure_bias": None,
        "risk_environment": None,
        "risk_state": None,

        "base_amount": round(float(base_amount), 2),
        "exposure_multiplier": exposure_multiplier,

        "position_size": intent_position_size,
        "execution_position_size": execution_position_size,

        # ✅ NIEUW: context, GEEN alternatieve score
        "trade_context": trade_context,

        "watch_levels": levels,
        "monitoring": monitoring,
        "alerts_active": alerts_active,

        "guardrails_result": guardrails_result,
        "guardrail_reason": guardrail_reason,

        "trade_plan": trade_plan,

        "metrics": {
            "benchmark_score": verified_benchmark,
            "position_size": intent_position_size,
            "execution_position_size": execution_position_size,
        },

        "debug": {
            "scores": normalized_scores,
            "market_intelligence": market_intelligence,
            "decision_result": decision_result,
            "base_amount": base_amount,
            "suggested_amount": suggested_amount,
            "adjusted_amount": adjusted_amount,
            "base_reason": base_reason,
            "levels": levels,
            "guardrails_result": guardrails_result,
            "intent_position_size": intent_position_size,
            "execution_position_size": execution_position_size,
            "setup_type": setup_type,
            "setup_intent_note": setup_intent_note,
            "snapshot": snapshot,
            "setup_result": setup_result,
            "trade_context": trade_context,
        },
    }
