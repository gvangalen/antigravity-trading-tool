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


def test_integrated_plan_recognizes_preferences_alias_as_the_canonical_scope():
    service = FinnV2ReasoningService(session=object())
    context = ReasoningContextPackage(
        run_id="run-preferences", user_id=7, user_message="Beoordeel mijn BTC-plan", locale="nl-NL", interaction_mode="EVALUATE",
        orchestrator_result_id="o", snapshot_id="s", validation_id="v", policy_decision_id="p", evidence_set_hash="hash",
        request_plan={"required_information_scopes": ["preferences"]},
        evidence=[ReasoningEvidenceItem(evidence_id="Eprefs", artifact_id="prefs", tool_name="read_user_preferences", information_scope="trading_preferences", domain="identity_context", entity_type="preferences", source="internal", freshness="fresh", confidence="high", facts={"risk_profile": "balanced"})],
        policy=ReasoningPolicyContext(policy_class="advice", allowed=True, proposal_allowed=False, confirmation_required=False, step_up_required=False, execution_allowed=False),
    )
    result = ReasoningResult(reasoning_result_id="r", run_id="run-preferences", user_id=7, mode="EVALUATE", direct_answer="Je voorkeur is balanced.", main_observation="De voorkeur is beschikbaar.", evidence_refs_used=["Eprefs"], model="gpt-test", created_at=datetime.now(timezone.utc))

    service._validate_refs(result, context)
    assert context.evidence[0].information_scope.value == "preferences"


def test_integrated_plan_reasoning_accepts_complete_scope_coverage_without_metadata_claims():
    service = FinnV2ReasoningService(session=object())
    context = ReasoningContextPackage(
        run_id="run-1", user_id=7, user_message="Evalueer mijn plan", locale="nl-NL", interaction_mode="EVALUATE",
        subject_scopes=["profile", "indicators", "setup", "strategy", "bot"], orchestrator_result_id="o-1", snapshot_id="s-1",
        validation_id="v-1", policy_decision_id="p-1", evidence_set_hash="hash", uncertainty_codes=["evidence_freshness_stale:read_bot_status"],
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
        uncertainty_summary="De botstatus is mogelijk verouderd.",
        evidence_refs_used=["E1", "E2", "E3", "E4", "E5"], model="gpt-test", created_at=datetime.now(timezone.utc),
    )

    service._validate_refs(result, context)


def test_integrated_plan_reasoning_still_requires_scope_coverage_from_model_refs():
    service = FinnV2ReasoningService(session=object())
    context = ReasoningContextPackage(
        run_id="run-1", user_id=7, user_message="Evalueer mijn plan", locale="nl-NL", interaction_mode="EVALUATE",
        subject_scopes=["profile", "indicators", "setup", "strategy", "bot"], orchestrator_result_id="o-1", snapshot_id="s-1",
        validation_id="v-1", policy_decision_id="p-1", evidence_set_hash="hash",
        evidence=[
            ReasoningEvidenceItem(evidence_id="E1", artifact_id="a1", tool_name="read_profile", domain="identity_context", entity_type="profile", source="internal", freshness="fresh", confidence="high", facts={"trader_profile": {"risk_profile": "balanced"}}),
            ReasoningEvidenceItem(evidence_id="E2", artifact_id="a2", tool_name="read_indicator_configuration", domain="market_context", entity_type="indicator_configuration", source="internal", freshness="fresh", confidence="high", facts={"configured_indicators": [{"indicator": "rsi"}, {"indicator": "ma_200"}]}),
            ReasoningEvidenceItem(evidence_id="E3", artifact_id="a3", tool_name="read_active_setup", domain="plan_context", entity_type="setup", entity_id="309", source="internal", freshness="fresh", confidence="high", facts={"setup_id": 309, "timeframe": "4H"}),
            ReasoningEvidenceItem(evidence_id="E4", artifact_id="a4", tool_name="read_linked_strategy", domain="plan_context", entity_type="strategy", entity_id="325", source="internal", freshness="fresh", confidence="high", facts={"strategy_id": 325}),
            ReasoningEvidenceItem(evidence_id="E5", artifact_id="a5", tool_name="read_linked_bot", domain="automation_context", entity_type="bot", entity_id="186", source="internal", freshness="fresh", confidence="high", facts={"bot_id": 186}),
        ],
        policy=ReasoningPolicyContext(policy_class="advice", allowed=True, proposal_allowed=False, confirmation_required=False, step_up_required=False, execution_allowed=False),
    )
    result = ReasoningResult(
        reasoning_result_id="r-1", run_id="run-1", user_id=7, mode="EVALUATE", direct_answer="Je balanced profiel met setup 309, strategie 325 en bot 186 heeft aandacht nodig.", main_observation="Leg je regel vast.",
        claims=[
            ReasoningClaim(claim_id="C1", claim_type="fact", text="Je profiel is balanced.", evidence_refs=["E1"], confidence="high"),
            ReasoningClaim(claim_id="C2", claim_type="fact", text="Setup 309 gebruikt 4H.", evidence_refs=["E3"], confidence="high"),
            ReasoningClaim(claim_id="C3", claim_type="fact", text="Strategie 325 is gekoppeld.", evidence_refs=["E4"], confidence="high"),
            ReasoningClaim(claim_id="C4", claim_type="fact", text="Bot 186 is gekoppeld.", evidence_refs=["E5"], confidence="high"),
        ],
        evidence_refs_used=["E1", "E3", "E4", "E5"], model="gpt-test", created_at=datetime.now(timezone.utc),
    )

    with pytest.raises(ValueError) as exc_info:
        service._validate_refs(result, context)

    assert exc_info.value.code == "missing_required_scope_refs"
    assert exc_info.value.missing_scopes == ["indicators"]


def test_integrated_plan_reasoning_accepts_grounded_claims_with_valid_evidence_refs():
    service = FinnV2ReasoningService(session=object())
    context = ReasoningContextPackage(
        run_id="run-1", user_id=7, user_message="Evalueer mijn plan", locale="nl-NL", interaction_mode="EVALUATE",
        subject_scopes=["profile", "indicators", "setup", "strategy", "bot"], orchestrator_result_id="o-1", snapshot_id="s-1",
        validation_id="v-1", policy_decision_id="p-1", evidence_set_hash="hash",
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
        reasoning_result_id="r-1", run_id="run-1", user_id=7, mode="EVALUATE", direct_answer="Leg een beslisregel vast.", main_observation="Je plan heeft een concrete vervolgstap.",
        claims=[
            ReasoningClaim(claim_id="C1", claim_type="fact", text="Je profiel is balanced.", evidence_refs=["E1"], confidence="high"),
            ReasoningClaim(claim_id="C2", claim_type="fact", text="Je indicator is rsi.", evidence_refs=["E2"], confidence="high"),
            ReasoningClaim(claim_id="C3", claim_type="fact", text="Setup 309 gebruikt 4H.", evidence_refs=["E3"], confidence="high"),
            ReasoningClaim(claim_id="C4", claim_type="fact", text="Strategie 325 is gekoppeld.", evidence_refs=["E4"], confidence="high"),
            ReasoningClaim(claim_id="C5", claim_type="fact", text="Bot 186 is gekoppeld.", evidence_refs=["E5"], confidence="high"),
        ],
        evidence_refs_used=["E1", "E2", "E3", "E4", "E5"], model="gpt-test", created_at=datetime.now(timezone.utc),
    )

    service._validate_refs(result, context)
