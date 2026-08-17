from datetime import datetime, timezone

import pytest

from backend.schemas.finn_v2_reasoning_schema import ProposalCandidate, ReasoningClaim, ReasoningResult


def test_reasoning_result_rejects_proposal_candidate_outside_proposal_or_action():
    with pytest.raises(ValueError):
        ReasoningResult(
            reasoning_result_id="r1",
            run_id="run-1",
            user_id=7,
            mode="FACT",
            direct_answer="answer",
            main_observation="observation",
            claims=[],
            proposal_candidate=ProposalCandidate(
                operation_type="update_setup",
                target_type="setup",
                proposed_changes={},
                impact_summary="impact",
                risk_summary="risk",
                confirmation_required=True,
            ),
            evidence_refs_used=[],
            model="gpt-test",
            created_at=datetime.now(timezone.utc),
        )


def test_reasoning_claim_requires_schema_constrained_fields():
    claim = ReasoningClaim(
        claim_id="C1",
        claim_type="fact",
        text="The linked strategy uses BTC.",
        evidence_refs=["E1"],
        confidence="high",
    )

    assert claim.evidence_refs == ["E1"]
