from types import SimpleNamespace

from backend.schemas.finn_v2_reasoning_context_schema import (
    ReasoningContextPackage,
    ReasoningPolicyContext,
)
from backend.services.finn_v2_reasoning_fallback_service import FinnV2ReasoningFallbackService


def _lineage_context(operation_id: str) -> ReasoningContextPackage:
    return ReasoningContextPackage(
        run_id="run-follow-up",
        user_id=388,
        user_message="Formuleer die conclusie korter.",
        locale="nl-NL",
        interaction_mode="READ",
        orchestrator_result_id="orchestrator-follow-up",
        snapshot_id="snapshot-follow-up",
        validation_id="validation-follow-up",
        policy_decision_id="policy-follow-up",
        evidence_set_hash="lineage-hash",
        evidence=[],
        policy=ReasoningPolicyContext(
            policy_class="read", allowed=True, proposal_allowed=False,
            confirmation_required=False, step_up_required=False,
            execution_allowed=False,
        ),
        request_plan={
            "operation_id": operation_id,
            "operation_state": {
                "previous_verified_response_id": "verified-plan",
                "previous_verified_run_id": "run-plan",
                "previous_verified_conclusion": "De entryvoorwaarde is onvoldoende toetsbaar.",
                "previous_verified_response": (
                    "Je plan mist een toetsbare entryvoorwaarde. "
                    "Leg eerst de beslisregel vast."
                ),
                "previous_evidence_refs": ["E1", "E2"],
            },
        },
    )


def test_reformulation_uses_previous_verified_response_without_tools_or_provider():
    result = FinnV2ReasoningFallbackService().lineage_draft(
        run_id="run-follow-up", user_id=388,
        operation_id="reformulate_previous_response",
        context=_lineage_context("reformulate_previous_response"),
        model="deterministic",
    )

    assert result.mode == "READ"
    assert result.direct_answer == "Je plan mist een toetsbare entryvoorwaarde."
    assert result.evidence_refs_used == ["E1", "E2"]


def test_reformulation_of_degraded_lineage_uses_only_released_non_conclusive_sections():
    context = _lineage_context("reformulate_previous_response").copy(deep=True)
    context.request_plan["operation_state"] = {
        "previous_degraded_run_id": "run-degraded",
        "previous_evidence_refs": ["E1"],
        "previous_degraded_released_sections": [
            {"kind": "verification_limitation", "text": "De beoordeling is niet geverifieerd."},
            {"kind": "evidence_availability", "text": "Beschikbare evidence kan worden toegelicht."},
        ],
    }

    result = FinnV2ReasoningFallbackService().lineage_draft(
        run_id="run-follow-up", user_id=388, operation_id="reformulate_previous_response",
        context=context, model="deterministic",
    )

    assert result.mode == "READ"
    assert "niet geverifieerd" in result.direct_answer
    assert "vorige geverifieerde conclusie" not in result.main_observation


def test_off_topic_terminal_answers_off_topic_instead_of_financial_unavailable():
    plan = SimpleNamespace(operation_id="off_topic")
    orchestrator = SimpleNamespace(
        analysis=SimpleNamespace(request_plan=plan, explicit_asset=None),
        selected_clarification=None,
        unavailable_codes=["financial_domain_unavailable"],
        uncertainty_codes=[],
        outcome="unavailable",
    )

    result = FinnV2ReasoningFallbackService().terminal_from_orchestrator(
        run_id="run-weather", user_id=388,
        orchestrator_result=orchestrator, model="deterministic",
    )

    assert result.mode == "UNAVAILABLE"
    assert "buiten FINN" in result.main_observation
    assert "trade aanwijzen" not in result.direct_answer
