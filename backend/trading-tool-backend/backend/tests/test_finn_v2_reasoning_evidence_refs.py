from datetime import datetime, timezone

import pytest

from backend.schemas.finn_v2_reasoning_context_schema import ReasoningContextPackage, ReasoningEvidenceItem, ReasoningPolicyContext
from backend.schemas.finn_v2_reasoning_schema import ReasoningClaim, ReasoningResult
from backend.services.finn_v2_reasoning_service import FinnV2ReasoningService


def test_reasoning_result_rejects_invalid_evidence_refs():
    service = FinnV2ReasoningService(session=object())
    context = ReasoningContextPackage(
        run_id="run-1",
        user_id=7,
        user_message="Vraag",
        locale="nl-NL",
        interaction_mode="FACT",
        orchestrator_result_id="o-1",
        snapshot_id="s-1",
        validation_id="v-1",
        policy_decision_id="p-1",
        evidence_set_hash="hash",
        evidence=[ReasoningEvidenceItem(evidence_id="E1", artifact_id="a1", tool_name="read_active_setup", domain="plan_context", entity_type="setup", source="internal", freshness="unknown", confidence="high")],
        policy=ReasoningPolicyContext(policy_class="read", allowed=True, proposal_allowed=False, confirmation_required=False, step_up_required=False, execution_allowed=False),
    )
    result = ReasoningResult(
        reasoning_result_id="r-1",
        run_id="run-1",
        user_id=7,
        mode="FACT",
        direct_answer="Antwoord",
        main_observation="Observatie",
        claims=[ReasoningClaim(claim_id="C1", claim_type="fact", text="Tekst", evidence_refs=["E9"], confidence="high")],
        evidence_refs_used=["E9"],
        model="gpt-test",
        created_at=datetime.now(timezone.utc),
    )

    with pytest.raises(ValueError):
        service._validate_refs(result, context)


def test_integrated_plan_reasoning_requires_evidence_from_each_required_scope():
    service = FinnV2ReasoningService(session=object())
    context = ReasoningContextPackage(
        run_id="run-1", user_id=7, user_message="Evalueer mijn plan", locale="nl-NL", interaction_mode="EVALUATE",
        subject_scopes=["profile", "indicators", "setup", "strategy", "bot"], orchestrator_result_id="o-1", snapshot_id="s-1",
        validation_id="v-1", policy_decision_id="p-1", evidence_set_hash="hash",
        evidence=[
            ReasoningEvidenceItem(evidence_id="E1", artifact_id="a1", tool_name="read_profile", domain="identity_context", entity_type="profile", source="internal", freshness="fresh", confidence="high"),
            ReasoningEvidenceItem(evidence_id="E2", artifact_id="a2", tool_name="read_indicator_configuration", domain="market_context", entity_type="indicator_configuration", source="internal", freshness="fresh", confidence="high"),
            ReasoningEvidenceItem(evidence_id="E3", artifact_id="a3", tool_name="read_active_setup", domain="plan_context", entity_type="setup", source="internal", freshness="fresh", confidence="high"),
            ReasoningEvidenceItem(evidence_id="E4", artifact_id="a4", tool_name="read_linked_strategy", domain="plan_context", entity_type="strategy", source="internal", freshness="fresh", confidence="high"),
            ReasoningEvidenceItem(evidence_id="E5", artifact_id="a5", tool_name="read_linked_bot", domain="automation_context", entity_type="bot", source="internal", freshness="fresh", confidence="high"),
        ],
        policy=ReasoningPolicyContext(policy_class="advice", allowed=True, proposal_allowed=False, confirmation_required=False, step_up_required=False, execution_allowed=False),
    )
    result = ReasoningResult(
        reasoning_result_id="r-1", run_id="run-1", user_id=7, mode="EVALUATE", direct_answer="Antwoord", main_observation="Observatie",
        evidence_refs_used=["E1", "E2", "E3", "E4"], model="gpt-test", created_at=datetime.now(timezone.utc),
    )

    with pytest.raises(ValueError, match="missing_required_scope_refs:bot"):
        service._validate_refs(result, context)


def test_integrated_plan_reasoning_requires_visible_grounding_for_each_scope():
    service = FinnV2ReasoningService(session=object())
    context = ReasoningContextPackage(
        run_id="run-1", user_id=7, user_message="Evalueer mijn plan", locale="nl-NL", interaction_mode="EVALUATE",
        subject_scopes=["profile", "indicators", "setup", "strategy", "bot"], orchestrator_result_id="o-1", snapshot_id="s-1",
        validation_id="v-1", policy_decision_id="p-1", evidence_set_hash="hash", uncertainty_codes=["bot_status_stale"],
        evidence=[
            ReasoningEvidenceItem(evidence_id="E1", artifact_id="a1", tool_name="read_profile", domain="identity_context", entity_type="profile", source="internal", freshness="fresh", confidence="high", facts={"trader_profile": {"risk_profile": "balanced"}}),
            ReasoningEvidenceItem(evidence_id="E2", artifact_id="a2", tool_name="read_indicator_configuration", domain="market_context", entity_type="indicator_configuration", source="internal", freshness="fresh", confidence="high", facts={"configured_indicators": [{"indicator": "rsi"}]}),
            ReasoningEvidenceItem(evidence_id="E3", artifact_id="a3", tool_name="read_active_setup", domain="plan_context", entity_type="setup", entity_id="309", source="internal", freshness="fresh", confidence="high", facts={"setup_id": 309, "timeframe": "4H"}),
            ReasoningEvidenceItem(evidence_id="E4", artifact_id="a4", tool_name="read_linked_strategy", domain="plan_context", entity_type="strategy", entity_id="325", source="internal", freshness="fresh", confidence="high", facts={"strategy_id": 325}),
            ReasoningEvidenceItem(evidence_id="E5", artifact_id="a5", tool_name="read_linked_bot", domain="automation_context", entity_type="bot", entity_id="186", source="internal", freshness="fresh", confidence="high", facts={"bot_id": 186}),
        ],
        policy=ReasoningPolicyContext(policy_class="advice", allowed=True, proposal_allowed=False, confirmation_required=False, step_up_required=False, execution_allowed=False),
    )
    result = ReasoningResult(
        reasoning_result_id="r-1", run_id="run-1", user_id=7, mode="EVALUATE", direct_answer="RSI ondersteunt je plan.", main_observation="De setup heeft aandacht nodig.",
        evidence_refs_used=["E1", "E2", "E3", "E4", "E5"], model="gpt-test", created_at=datetime.now(timezone.utc),
    )

    with pytest.raises(ValueError, match="missing_required_scope_grounding"):
        service._validate_refs(result, context)

    grounded = result.copy(
        update={
            "direct_answer": "Je balanced profiel met RSI, setup 309 op 4H, strategie 325 en bot 186 heeft een duidelijke vervolgstap.",
            "uncertainty_summary": "De botstatus is mogelijk verouderd.",
        }
    )
    service._validate_refs(grounded, context)
