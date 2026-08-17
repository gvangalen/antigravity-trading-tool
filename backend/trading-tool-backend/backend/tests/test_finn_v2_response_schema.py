from datetime import datetime, timezone

import pytest

from backend.schemas.finn_v2_response_schema import ResponseClaim, ResponseDraft


def test_response_draft_schema_requires_question_for_clarification():
    with pytest.raises(ValueError):
        ResponseDraft(
            draft_id="draft-1",
            run_id="run-1",
            user_id=7,
            mode="CLARIFICATION",
            direct_answer="Ik heb nog een keuze nodig.",
            main_observation="Er zijn meerdere mogelijke doelen.",
            evidence_set_hash="hash-1",
            created_at=datetime.now(timezone.utc),
        )


def test_response_claim_schema_supports_grounded_fact():
    claim = ResponseClaim(
        claim_id="C1",
        claim_type="fact",
        text="De bot staat in paper mode.",
        evidence_refs=["E1"],
        confidence="high",
    )

    assert claim.evidence_refs == ["E1"]
