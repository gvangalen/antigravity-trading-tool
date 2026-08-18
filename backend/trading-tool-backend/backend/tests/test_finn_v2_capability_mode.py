from datetime import datetime, timezone
from types import SimpleNamespace

from backend.schemas.finn_v2_response_schema import ResponseDraft
from backend.schemas.finn_v2_reasoning_schema import ReasoningSupportingPoint
from backend.services.finn_v2_capability_registry_service import FinnV2CapabilityRegistryService
from backend.services.finn_v2_response_verifier_service import FinnV2ResponseVerifierService


def _capability_draft(*, title: str = "Profiel en voorkeuren duiden", direct_answer: str = "Ik kan je helpen om je context te begrijpen en veilige vervolgstappen voor te bereiden."):
    return ResponseDraft(
        draft_id="draft-capability-1",
        run_id="run-capability-1",
        user_id=7,
        mode="CAPABILITY",
        direct_answer=direct_answer,
        main_observation="Met meer profiel- en plancontext kan FINN persoonlijker uitleg geven.",
        supporting_points=[
            ReasoningSupportingPoint(
                title=title,
                explanation="Ik kan uitleggen wat er al staat en wat nog ontbreekt.",
                evidence_refs=[],
            )
        ],
        claims=[],
        uncertainty_codes=[],
        evidence_set_hash="hash-1",
        created_at=datetime.now(timezone.utc),
    )


def test_capability_registry_recognizes_dutch_and_english_questions():
    service = FinnV2CapabilityRegistryService()

    assert service.is_capability_question("Hoi FINN, wat kun je voor mij doen?")
    assert service.is_capability_question("What can FINN do for me?")


def test_verifier_accepts_registry_grounded_capability_response():
    service = FinnV2ResponseVerifierService(session=object())
    draft = _capability_draft()

    result = service._deterministic_verify(
        run=SimpleNamespace(id="run-capability-1", user_id=7, message="Hoi FINN, wat kun je voor mij doen?"),
        orchestrator_result=SimpleNamespace(
            analysis=SimpleNamespace(subject_scopes=["capability"]),
            selected_clarification=None,
        ),
        policy=SimpleNamespace(allowed=True, proposal_allowed=False),
        context=SimpleNamespace(evidence=[], uncertainty_codes=[]),
        validation=SimpleNamespace(evidence_set_hash="hash-1", integrity_status="valid"),
        draft=draft,
        repair_attempt=0,
    )

    assert result.passed is True
    assert result.policy_ok is True
    assert result.coverage.coverage_ok is True
    assert result.reason_codes == []


def test_verifier_blocks_capability_claim_outside_registry():
    service = FinnV2ResponseVerifierService(session=object())
    draft = _capability_draft(title="Realtime live orders automatisch uitvoeren")

    result = service._deterministic_verify(
        run=SimpleNamespace(id="run-capability-1", user_id=7, message="Wat kun je doen?"),
        orchestrator_result=SimpleNamespace(
            analysis=SimpleNamespace(subject_scopes=["capability"]),
            selected_clarification=None,
        ),
        policy=SimpleNamespace(allowed=True, proposal_allowed=False),
        context=SimpleNamespace(evidence=[], uncertainty_codes=[]),
        validation=SimpleNamespace(evidence_set_hash="hash-1", integrity_status="valid"),
        draft=draft,
        repair_attempt=0,
    )

    assert result.passed is False
    assert "capability_claim_not_registered" in result.reason_codes


def test_capability_mode_rejects_financial_trade_advice_language():
    service = FinnV2ResponseVerifierService(session=object())
    draft = _capability_draft(direct_answer="Ik kan je helpen en je vertellen dat je nu BTC moet kopen.")

    assert service._mode_purity_ok(draft) is False
