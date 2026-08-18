from datetime import datetime, timezone
from types import SimpleNamespace

from backend.schemas.finn_v2_response_schema import ResponseClaim, ResponseDraft
from backend.services.finn_v2_response_verifier_service import FinnV2ResponseVerifierService


def _draft(text: str, refs: list[str], *, asset: str = "AAPL") -> ResponseDraft:
    return ResponseDraft(
        draft_id="draft-1",
        run_id="run-1",
        user_id=7,
        mode="FACT",
        direct_answer=text,
        main_observation=text,
        claims=[ResponseClaim(claim_id="C1", claim_type="fact", text=text, evidence_refs=refs, confidence="high")],
        evidence_set_hash="hash-1",
        created_at=datetime.now(timezone.utc),
    )


def _context(is_live: bool = False, asset: str = "AAPL"):
    evidence = [
        SimpleNamespace(
            evidence_id="E1",
            domain="automation_context",
            tool_name="read_bot_status",
            entity_type="bot",
            entity_id="12",
            asset=asset,
            freshness="fresh",
            confidence="high",
            facts={"bot_id": 12, "is_live": is_live, "symbol": asset},
        )
    ]
    return SimpleNamespace(evidence=evidence, uncertainty_codes=[])


def _common():
    service = FinnV2ResponseVerifierService(session=object())
    run = SimpleNamespace(id="run-1", user_id=7, message="Staat mijn AAPL bot live?", conversation_id="conv-1")
    orchestrator = SimpleNamespace(analysis=SimpleNamespace(subject_scopes=["bot"]), selected_clarification=None)
    policy = SimpleNamespace(allowed=True, proposal_allowed=True, confirmation_required=False, operation_type=None)
    validation = SimpleNamespace(id="validation-1", evidence_set_hash="hash-1", integrity_status="valid")
    return service, run, orchestrator, policy, validation


def test_claim_grounding_detects_invalid_evidence_ref():
    service, run, orchestrator, policy, validation = _common()
    verifier = service._deterministic_verify(
        run=run,
        orchestrator_result=orchestrator,
        policy=policy,
        context=_context(),
        validation=validation,
        draft=_draft("De bot staat live.", ["E9"]),
        repair_attempt=0,
    )

    assert verifier.evidence_ok is False
    assert "invalid_evidence_ref" in verifier.claim_results[0].reason_codes


def test_claim_grounding_detects_paper_live_contradiction():
    service, run, orchestrator, policy, validation = _common()
    verifier = service._deterministic_verify(
        run=run,
        orchestrator_result=orchestrator,
        policy=policy,
        context=_context(is_live=False),
        validation=validation,
        draft=_draft("De bot staat live.", ["E1"]),
        repair_attempt=0,
    )

    assert "paper_live_mismatch" in verifier.reason_codes


def test_claim_grounding_does_not_treat_is_live_field_name_as_live_assertion():
    service, run, orchestrator, policy, validation = _common()
    draft = ResponseDraft(
        draft_id="draft-2",
        run_id="run-1",
        user_id=7,
        mode="EVALUATION",
        direct_answer="Je bot staat in paper mode.",
        main_observation="Bot 12 heeft is_live false en is_active true.",
        claims=[
            ResponseClaim(
                claim_id="C2",
                claim_type="fact",
                text="Bot 12 heeft is_live false en is_active true.",
                evidence_refs=["E1"],
                confidence="high",
            )
        ],
        evidence_set_hash="hash-1",
        created_at=datetime.now(timezone.utc),
    )

    verifier = service._deterministic_verify(
        run=run,
        orchestrator_result=orchestrator,
        policy=policy,
        context=_context(is_live=False),
        validation=validation,
        draft=draft,
        repair_attempt=0,
    )

    assert "paper_live_mismatch" not in verifier.reason_codes
