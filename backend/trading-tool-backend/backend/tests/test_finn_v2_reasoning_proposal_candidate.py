from datetime import datetime, timezone

import pytest

from backend.schemas.finn_v2_reasoning_context_schema import ReasoningContextPackage, ReasoningEvidenceItem, ReasoningPolicyContext
from backend.schemas.finn_v2_reasoning_schema import ProposalCandidate, ReasoningResult
from backend.services.finn_v2_reasoning_service import FinnV2ReasoningService


def test_reasoning_proposal_candidate_must_match_allowed_operation():
    service = FinnV2ReasoningService(session=object())
    context = ReasoningContextPackage(
        run_id="run-1",
        user_id=7,
        user_message="Voeg DXY toe",
        locale="nl-NL",
        interaction_mode="PROPOSAL",
        orchestrator_result_id="o-1",
        snapshot_id="s-1",
        validation_id="v-1",
        policy_decision_id="p-1",
        evidence_set_hash="hash",
        evidence=[ReasoningEvidenceItem(evidence_id="E1", artifact_id="a1", tool_name="read_indicator_configuration", domain="market_context", entity_type="indicator_configuration", source="internal", freshness="unknown", confidence="high")],
        policy=ReasoningPolicyContext(policy_class="proposal", allowed=True, proposal_allowed=True, confirmation_required=True, step_up_required=False, execution_allowed=False, operation_type="update_indicator_configuration"),
        allowed_operation_types=["update_indicator_configuration"],
    )
    result = ReasoningResult(
        reasoning_result_id="r-1",
        run_id="run-1",
        user_id=7,
        mode="PROPOSAL",
        direct_answer="Conceptvoorstel.",
        main_observation="DXY ontbreekt.",
        claims=[],
        proposal_candidate=ProposalCandidate(
            operation_type="activate_live_bot",
            target_type="bot",
            proposed_changes={"mode": "live"},
            impact_summary="impact",
            risk_summary="risk",
            confirmation_required=True,
        ),
        evidence_refs_used=["E1"],
        model="gpt-test",
        created_at=datetime.now(timezone.utc),
    )

    with pytest.raises(ValueError):
        service._validate_refs(result, context)
