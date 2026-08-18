from datetime import datetime, timezone

import pytest

from backend.schemas.finn_v2_reasoning_schema import ProposalCandidate, ReasoningClaim, ReasoningResult
from backend.services.finn_v2_reasoning_prompt_service import FinnV2ReasoningPromptService


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


def test_proposal_candidate_accepts_json_encoded_proposed_changes():
    candidate = ProposalCandidate(
        operation_type="update_setup",
        target_type="setup",
        proposed_changes='{"changed_fields":{"risk_profile":"aggressive"}}',
        impact_summary="impact",
        risk_summary="risk",
        confirmation_required=True,
    )

    assert candidate.proposed_changes == {"changed_fields": {"risk_profile": "aggressive"}}


def test_reasoning_prompt_schema_keeps_proposed_changes_openai_compatible():
    schema = FinnV2ReasoningPromptService().response_schema()
    proposal_branch = schema["properties"]["proposal_candidate"]["anyOf"][1]

    assert proposal_branch["properties"]["proposed_changes"] == {"type": "string"}
