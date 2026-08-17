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
