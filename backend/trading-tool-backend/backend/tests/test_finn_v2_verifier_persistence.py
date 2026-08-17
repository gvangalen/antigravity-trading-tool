from pathlib import Path
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.schemas.finn_v2_response_schema import ResponseDraft
from backend.schemas.finn_v2_verifier_schema import CoverageVerification, VerifierResult
from backend.services.finn_v2_response_verifier_service import FinnV2ResponseVerifierService


ROOT = Path(__file__).resolve().parents[1]


def test_verifier_persistence_is_append_only_and_versioned():
    verifier_repo = (ROOT / "infrastructure" / "repositories" / "finn_v2_verifier_repository.py").read_text(encoding="utf-8")
    verified_repo = (ROOT / "infrastructure" / "repositories" / "finn_v2_verified_response_repository.py").read_text(encoding="utf-8")
    migration_source = (ROOT / "scripts" / "migrations" / "2026_08_17_finn_v2_verified_delivery.py").read_text(encoding="utf-8")

    assert "async def create" in verifier_repo
    assert ".update(" not in verifier_repo
    assert "UNIQUE (run_id, response_version)" in migration_source
    assert "async def create" in verified_repo


def test_verifier_persistence_serializes_datetime_payloads():
    service = FinnV2ResponseVerifierService(session=object())
    verifier_captured = {}
    response_captured = {}

    async def _create_verifier(**kwargs):
        verifier_captured.update(kwargs)
        return SimpleNamespace(id=kwargs["id"])

    async def _create_verified(**kwargs):
        response_captured.update(kwargs)
        return SimpleNamespace(**kwargs)

    service.verifiers.create = _create_verifier
    service.verified.create = _create_verified

    run = SimpleNamespace(id="run-1", user_id=7)
    draft = ResponseDraft(
        draft_id="draft-1",
        run_id="run-1",
        user_id=7,
        mode="UNAVAILABLE",
        direct_answer="Niet beschikbaar.",
        main_observation="Er is nog geen veilige verified output.",
        supporting_points=[],
        claims=[],
        uncertainty_summary=None,
        uncertainty_codes=[],
        next_step=None,
        follow_up_question=None,
        proposal_candidate=None,
        reasoning_result_id="reasoning-1",
        evidence_set_hash="hash-1",
        created_at=datetime.now(timezone.utc),
    )
    verifier = VerifierResult(
        verifier_result_id="verifier-1",
        run_id="run-1",
        user_id=7,
        draft_id="draft-1",
        passed=True,
        action="deliver",
        claim_results=[],
        coverage=CoverageVerification(required_scopes=[], covered_scopes=[], missing_scopes=[], coverage_ok=True),
        schema_ok=True,
        ownership_ok=True,
        evidence_ok=True,
        relevance_ok=True,
        mode_purity_ok=True,
        uncertainty_ok=True,
        follow_up_ok=True,
        proposal_ok=True,
        policy_ok=True,
        safety_ok=True,
        reason_codes=[],
        semantic_verifier_used=False,
        created_at=datetime.now(timezone.utc),
    )

    persisted = asyncio.run(
        service._persist_verified_response(
            run=run,
            draft=draft,
            verifier=verifier,
            proposal_id=None,
            confirmation_required=False,
        )
    )

    assert isinstance(verifier_captured["result_json"]["created_at"], str)
    assert isinstance(response_captured["response_json"]["created_at"], str)
    assert persisted.created_at == response_captured["created_at"]
