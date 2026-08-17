from datetime import datetime, timezone
from types import SimpleNamespace

from backend.schemas.finn_v2_response_schema import ResponseClaim, ResponseDraft
from backend.services.finn_v2_response_verifier_service import FinnV2ResponseVerifierService


def test_scope_coverage_fails_when_a1_reduces_to_indicator_only():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-1",
        run_id="run-1",
        user_id=7,
        mode="EVALUATION",
        direct_answer="Je RSI staat goed.",
        main_observation="De indicatoren ogen sterk.",
        claims=[ResponseClaim(claim_id="C1", claim_type="evaluation", text="RSI is sterk.", evidence_refs=["E1"], confidence="high")],
        evidence_set_hash="hash-1",
        created_at=datetime.now(timezone.utc),
    )
    verifier = service._deterministic_verify(
        run=SimpleNamespace(id="run-1", user_id=7, message="Beoordeel profiel, indicators, setup, strategy en bot", conversation_id="conv-1"),
        orchestrator_result=SimpleNamespace(analysis=SimpleNamespace(subject_scopes=["profile", "indicators", "setup", "strategy", "bot"]), selected_clarification=None),
        policy=SimpleNamespace(allowed=True, proposal_allowed=True, confirmation_required=False, operation_type=None),
        context=SimpleNamespace(
            evidence=[SimpleNamespace(evidence_id="E1", domain="market_context", tool_name="read_indicator_configuration", entity_type="indicator_configuration", entity_id=None, asset="BTC", freshness="fresh", confidence="high", facts={"configured_indicators": [{"indicator": "rsi"}]})],
            uncertainty_codes=[],
        ),
        validation=SimpleNamespace(id="validation-1", evidence_set_hash="hash-1", integrity_status="valid"),
        draft=draft,
        repair_attempt=0,
    )

    assert verifier.coverage.coverage_ok is False
    assert "response_scope_incomplete" in verifier.reason_codes
