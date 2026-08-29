from datetime import datetime, timezone

from backend.schemas.finn_v2_response_schema import ResponseDraft
from backend.services.finn_v2_response_repair_service import FinnV2ResponseRepairService


def test_response_repair_adds_uncertainty_and_removes_invalid_follow_up():
    service = FinnV2ResponseRepairService()
    draft = ResponseDraft(
        draft_id="draft-1",
        run_id="run-1",
        user_id=7,
        mode="READ",
        direct_answer="De context is goed.",
        main_observation="Er is weinig risico.",
        follow_up_question="Wil je meer weten?",
        evidence_set_hash="hash-1",
        created_at=datetime.now(timezone.utc),
    )

    repaired = service.repair(
        draft=draft,
        reason_codes=["missing_uncertainty", "follow_up_invalid"],
        uncertainty_summary="De botstatus is verouderd.",
    )

    assert repaired.uncertainty_summary == "De botstatus is verouderd."
    assert repaired.follow_up_question is None


def test_evaluate_repair_restores_a_safe_concrete_next_step():
    draft = ResponseDraft(
        draft_id="draft-2", run_id="run-2", user_id=7, mode="EVALUATE",
        direct_answer="De huidige onderbouwing is beperkt.",
        main_observation="De setupgegevens zijn ouder dan de overige evidence.",
        evidence_set_hash="hash-2", created_at=datetime.now(timezone.utc),
    )

    repaired = FinnV2ResponseRepairService().repair(
        draft=draft, reason_codes=["response_field_incomplete"], uncertainty_summary=None,
    )

    assert repaired.next_step
    assert "gegevens" in repaired.next_step.instruction
