from datetime import datetime, timezone

from backend.schemas.finn_v2_verifier_schema import CoverageVerification, VerifierResult
from backend.services.finn_v2_response_verifier_service import FinnV2ResponseVerifierService
from backend.services.finn_v2_semantic_verifier_service import FinnV2SemanticVerifierService
from backend.utils import openai_client as openai_module


def test_semantic_verifier_uses_strict_structured_output(monkeypatch):
    service = FinnV2SemanticVerifierService()
    service.flags.is_semantic_verifier_enabled = lambda: True
    service.flags.semantic_verifier_model = lambda: "gpt-test"
    service.flags.semantic_verifier_timeout_seconds = lambda: 30

    def _fake_structured_response(**kwargs):
        assert kwargs["schema"]["strict"] is True
        return {
            "parsed": {
                "passes": True,
                "relevance_ok": True,
                "scope_ok": True,
                "entailment_ok": True,
                "recommendation_ok": True,
                "mode_purity_ok": True,
                "follow_up_ok": True,
                "reason_codes": [],
            },
            "model": "gpt-test",
        }

    monkeypatch.setattr(openai_module, "ask_gpt_structured_response", _fake_structured_response)
    result = service.verify(
        mode="EVALUATION",
        user_message="Beoordeel mijn bot",
        sanitized_draft={"mode": "EVALUATION"},
        compact_evidence=[],
        deterministic_summary={"passed": True},
    )

    assert result.available is True
    assert result.passes is True


def test_disabled_semantic_verifier_does_not_downgrade_required_evaluation_mode():
    service = FinnV2ResponseVerifierService(session=object())
    service.flags.is_semantic_verifier_enabled = lambda: False
    service.flags.semantic_verifier_required_modes = lambda: {"EVALUATION", "PROPOSAL", "ACTION"}
    verifier = VerifierResult(
        verifier_result_id="verifier-1",
        run_id="run-1",
        user_id=7,
        draft_id="draft-1",
        passed=True,
        action="deliver",
        claim_results=[],
        coverage=CoverageVerification(coverage_ok=True),
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

    semantic = service.semantic.verify(
        mode="EVALUATION",
        user_message="Bekijk mijn plan",
        sanitized_draft={"mode": "EVALUATION"},
        compact_evidence=[],
        deterministic_summary={"passed": True},
    )

    merged = service._merge_semantic(verifier, semantic, "EVALUATION")

    assert merged.passed is True
    assert merged.action == "deliver"
    assert merged.reason_codes == []
    assert merged.semantic_verifier_used is False
