from datetime import datetime, timezone

from backend.schemas.finn_v2_response_schema import ResponseDraft
from backend.services.finn_v2_response_verifier_service import FinnV2ResponseVerifierService


def test_follow_up_contract_rejects_double_question():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-1",
        run_id="run-1",
        user_id=7,
        mode="CLARIFICATION",
        direct_answer="Ik heb een keuze nodig.",
        main_observation="Er zijn twee mogelijke setups.",
        follow_up_question="Bedoel je setup A? En wil je ook strategy B bekijken?",
        evidence_set_hash="hash-1",
        created_at=datetime.now(timezone.utc),
    )

    assert service._follow_up_ok(draft) is False
