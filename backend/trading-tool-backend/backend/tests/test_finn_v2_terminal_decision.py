from backend.services.finn_v2_response_downgrade_service import FinnV2ResponseDowngradeService
from backend.services.finn_v2_reasoning_fallback_service import FinnV2ReasoningFallbackService
from backend.schemas.finn_v2_response_schema import ResponseDraft
from datetime import datetime, timezone


def test_evaluate_repair_exhaustion_preserves_typed_intent_and_safe_next_step():
    draft = ResponseDraft(
        draft_id="draft-1", run_id="run-1", user_id=7, mode="EVALUATE",
        direct_answer="Onvolledig antwoord.", main_observation="Context.",
        evidence_refs_used=["evidence-1"], evidence_set_hash="hash-1", created_at=datetime.now(timezone.utc),
    )

    terminal = FinnV2ResponseDowngradeService().downgrade_to_contract_limited_evaluate(
        draft=draft, reason="response_field_incomplete"
    )

    assert terminal.mode == "EVALUATE"
    assert terminal.next_step is not None
    assert terminal.evidence_refs_used == ["evidence-1"]
    assert terminal.reasoning_provenance["reasoning_source"] == "contract_evidence_limitation"


def test_policy_blocked_activation_keeps_its_safe_operation_specific_terminal():
    result = FinnV2ReasoningFallbackService().safe_terminal_draft(
        run_id="run-1", user_id=7, operation_id="activate_bot", context=type("Context", (), {"request_plan": {}})(), model="test"
    )

    assert result.mode == "UNAVAILABLE"
    assert "activeren" in result.direct_answer
    assert "impliciet" in result.direct_answer
