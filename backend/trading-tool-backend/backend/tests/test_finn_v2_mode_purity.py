from datetime import datetime, timezone

import pytest

from backend.schemas.finn_v2_reasoning_schema import ProposalCandidate
from backend.schemas.finn_v2_response_schema import ResponseDraft
from backend.services.finn_v2_response_verifier_service import FinnV2ResponseVerifierService


def test_read_mode_rejects_embedded_proposal_candidate():
    service = FinnV2ResponseVerifierService(session=object())
    with pytest.raises(ValueError):
        ResponseDraft(
            draft_id="draft-1",
            run_id="run-1",
            user_id=7,
            mode="READ",
            direct_answer="Ik heb de wijziging alvast opgeslagen.",
            main_observation="De strategie is aangepast.",
            proposal_candidate=ProposalCandidate(
                operation_type="update_strategy",
                target_type="strategy",
                target_id="12",
                proposed_changes={"changed_fields": {"risk_profile": "aggressive"}},
                evidence_refs=["E1"],
                impact_summary="impact",
                risk_summary="risk",
                confirmation_required=True,
            ),
            evidence_set_hash="hash-1",
            created_at=datetime.now(timezone.utc),
        )

    assert service._mode_purity_ok(
        ResponseDraft(
            draft_id="draft-2",
            run_id="run-1",
            user_id=7,
            mode="READ",
            direct_answer="Ik heb de wijziging alvast opgeslagen.",
            main_observation="De strategie is aangepast.",
            evidence_set_hash="hash-1",
            created_at=datetime.now(timezone.utc),
        )
    ) is False


def test_read_mode_allows_stored_context_wording_without_write_claim():
    service = FinnV2ResponseVerifierService(session=object())

    assert service._mode_purity_ok(
        ResponseDraft(
            draft_id="draft-3",
            run_id="run-1",
            user_id=7,
            mode="READ",
            direct_answer="Voor BTC is bot Paper Bot gekoppeld aan strategie Swing Strategy.",
            main_observation="De koppeling komt rechtstreeks uit de opgeslagen automation- en plancontext.",
            evidence_set_hash="hash-1",
            created_at=datetime.now(timezone.utc),
        )
    ) is True
