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
