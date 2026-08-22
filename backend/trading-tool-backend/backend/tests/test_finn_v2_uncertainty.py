from datetime import datetime, timezone
from types import SimpleNamespace

from backend.schemas.finn_v2_response_schema import ResponseDraft
from backend.services.finn_v2_response_verifier_service import FinnV2ResponseVerifierService


def test_uncertainty_is_required_for_stale_evidence():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-1",
        run_id="run-1",
        user_id=7,
        mode="READ",
        direct_answer="De markttrend is positief.",
        main_observation="De snapshot lijkt sterk.",
        evidence_set_hash="hash-1",
        created_at=datetime.now(timezone.utc),
    )

    assert service._uncertainty_ok(
        draft,
        SimpleNamespace(
            uncertainty_codes=[],
            evidence=[SimpleNamespace(freshness="stale", confidence="medium")],
        ),
    ) is False
