from types import SimpleNamespace

from backend.schemas.finn_v2_reasoning_context_schema import (
    ReasoningContextPackage,
    ReasoningEvidenceItem,
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


def test_reformulation_of_degraded_lineage_reuses_only_already_visible_safe_terminal_content():
    context = _lineage_context("reformulate_previous_response").copy(deep=True)
    context.request_plan["operation_state"] = {
        "previous_degraded_run_id": "run-degraded",
        "previous_evidence_refs": ["E1"],
        "previous_degraded_released_response": {
            "direct_answer": "De beschikbare evidence ondersteunt geen geverifieerde financiële conclusie.",
            "main_observation": "De indicatorconfiguratie ontbreekt.",
            "uncertainty_summary": "Ik vul geen ontbrekende feiten in.",
            "next_step": "Leg de indicatorconfiguratie vast.",
        },
    }

    result = FinnV2ReasoningFallbackService().lineage_draft(
        run_id="run-follow-up", user_id=388, operation_id="reformulate_previous_response",
        context=context, model="deterministic",
    )

    assert result.mode == "READ"
    assert result.direct_answer == "De beschikbare evidence ondersteunt geen geverifieerde financiële conclusie."
    assert "niet geverifieerd" in result.uncertainty_summary
    assert result.evidence_refs_used == ["E1"]


def test_degraded_evidence_follow_up_explains_scopes_and_gap_without_promoting_conclusion():
    context = _lineage_context("explain_previous_evidence").copy(deep=True)
    context.request_plan["operation_state"] = {
        "previous_degraded_run_id": "run-degraded",
        "previous_evidence_refs": ["E1", "E2"],
        "previous_degraded_evidence_scopes": ["profile", "indicator_configuration", "bot_status"],
    }

    result = FinnV2ReasoningFallbackService().lineage_draft(
        run_id="run-follow-up", user_id=388, operation_id="explain_previous_evidence",
        context=context, model="deterministic",
    )

    assert result.mode == "EVALUATE"
    assert "profile" in result.direct_answer
    assert "indicator configuration" in result.direct_answer
    assert "geen volledig toetsbare beslisregel" in result.main_observation
    assert result.evidence_refs_used == ["E1", "E2"]


def test_bot_consequence_renders_a_concrete_evidence_bounded_check():
    context = _lineage_context("explain_previous_evidence").copy(deep=True)
    context.request_plan["semantic_frame"] = {"goal": "consequence", "object": "bot"}
    context.evidence = [
        ReasoningEvidenceItem(
            evidence_id="Ebot",
            artifact_id="artifact-bot",
            tool_name="read_bot_status",
            domain="automation_context",
            entity_type="bot_status",
            entity_id="170",
            source="bot_repository",
            freshness="fresh",
            confidence="high",
            facts={"is_live": False},
        )
    ]

    result = FinnV2ReasoningFallbackService().lineage_draft(
        run_id="run-follow-up", user_id=388, operation_id="explain_previous_evidence",
        context=context, model="deterministic",
    )

    assert "bot 170" in result.direct_answer
    assert "niet live" in result.direct_answer
    assert "rechtvaardigt geen botwijziging" in result.main_observation
    assert result.evidence_refs_used == ["Ebot"]


def test_contextual_bot_evaluation_keeps_its_operation_and_uses_bot_evidence_only():
    context = _lineage_context("evaluate_bot").copy(deep=True)
    context.request_plan["discourse_type"] = "contextual_follow_up"
    context.evidence = [
        ReasoningEvidenceItem(
            evidence_id="Ebotctx",
            artifact_id="artifact-bot-contextual",
            tool_name="read_bot_status",
            domain="automation_context",
            entity_type="bot_status",
            entity_id="171",
            source="bot_repository",
            freshness="fresh",
            confidence="high",
            facts={"is_live": False},
        )
    ]

    result = FinnV2ReasoningFallbackService().bot_consequence_draft(
        run_id="run-bot-contextual", user_id=388, context=context, model="deterministic"
    )

    assert result.mode == "EVALUATE"
    assert result.reasoning_provenance["operation_id"] == "evaluate_bot"
    assert "bot 171" in result.direct_answer
    assert result.evidence_refs_used == ["Ebotctx"]


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


def test_unsupported_terminal_answers_the_selected_safety_boundary():
    plan = SimpleNamespace(operation_id="unsupported_financial_operation")
    orchestrator = SimpleNamespace(
        analysis=SimpleNamespace(request_plan=plan, explicit_asset=None),
        selected_clarification=None, unavailable_codes=["financial_domain_unavailable"],
        uncertainty_codes=[], outcome="unavailable",
    )

    result = FinnV2ReasoningFallbackService().terminal_from_orchestrator(
        run_id="run-autonomy", user_id=388, orchestrator_result=orchestrator, model="deterministic",
    )

    assert result.mode == "UNAVAILABLE"
    assert "zonder bevestiging" in result.direct_answer
    assert "autonome financiële beslissingen" in result.main_observation


def test_empty_plan_evaluation_is_bounded_and_keeps_evaluate_mode():
    result = FinnV2ReasoningFallbackService().evidence_limited_evaluation_draft(
        run_id="run-empty-plan", user_id=388,
        context=_lineage_context("evaluate_plan"), model="deterministic",
        error_codes=["evidence_limitation_after_repair"],
    )

    assert result.mode == "EVALUATE"
    assert "geen opgeslagen setup" in result.direct_answer
    assert result.next_step is not None
    assert result.evidence_refs_used == []


def test_safe_terminal_boundary_explains_an_immediately_previous_off_topic_result():
    context = _lineage_context("explain_previous_evidence").copy(deep=True)
    context.request_plan["operation_state"] = {
        "previous_safe_terminal_run_id": "run-off-topic",
        "previous_safe_terminal_reason": "outside_finn_scope",
    }

    result = FinnV2ReasoningFallbackService().lineage_draft(
        run_id="run-follow-up", user_id=388, operation_id="explain_previous_evidence",
        context=context, model="deterministic",
    )

    assert result.mode == "EVALUATE"
    assert "buiten FINN" in result.direct_answer
    assert "financiële conclusie" not in result.direct_answer
