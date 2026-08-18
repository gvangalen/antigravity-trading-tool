from backend.services.finn_v2_reasoning_fallback_service import FinnV2ReasoningFallbackService
from backend.schemas.finn_v2_orchestrator_schema import OrchestratorResult, RequestAnalysisResult, DomainRequirementPlan, ToolPlan
from datetime import datetime, timezone


def test_clarification_and_unavailable_do_not_need_model_call():
    fallback = FinnV2ReasoningFallbackService()
    orchestrator = OrchestratorResult(
        orchestrator_result_id="o-1",
        run_id="run-1",
        user_id=7,
        analysis=RequestAnalysisResult(interaction_mode="FACT", subject_scopes=["setup"], confidence="medium", reasoning_required=False),
        domain_requirements=DomainRequirementPlan(),
        tool_plan=ToolPlan(run_id="run-1", interaction_mode="FACT", max_tool_calls=15),
        outcome="clarification_required",
        selected_clarification={"code": "ambiguous_setup", "domain": "plan_context", "question": "Welke setup bedoel je precies?", "entity_type": "setup"},
        created_at=datetime.now(timezone.utc),
    )

    draft = fallback.deterministic_draft(run_id="run-1", user_id=7, orchestrator_result=orchestrator, model="gpt-test")

    assert draft.mode == "CLARIFICATION"
    assert "nog geen verantwoorde trade" in draft.direct_answer
    assert draft.follow_up_question == "Welke setup bedoel je precies?"


def test_unavailable_draft_offers_single_safe_next_step():
    fallback = FinnV2ReasoningFallbackService()
    orchestrator = OrchestratorResult(
        orchestrator_result_id="o-2",
        run_id="run-2",
        user_id=7,
        analysis=RequestAnalysisResult(
            interaction_mode="UNAVAILABLE",
            subject_scopes=["unknown"],
            explicit_asset="BTC",
            confidence="none",
            reasoning_required=False,
        ),
        domain_requirements=DomainRequirementPlan(),
        tool_plan=ToolPlan(run_id="run-2", interaction_mode="UNAVAILABLE", max_tool_calls=15),
        outcome="unavailable",
        unavailable_codes=["insufficient_trade_context"],
        created_at=datetime.now(timezone.utc),
    )

    draft = fallback.deterministic_draft(run_id="run-2", user_id=7, orchestrator_result=orchestrator, model="gpt-test")

    assert draft.mode == "UNAVAILABLE"
    assert "geen verantwoorde trade" in draft.direct_answer
    assert draft.follow_up_question == "Wil je eerst je huidige setup voor BTC laten beoordelen?"
