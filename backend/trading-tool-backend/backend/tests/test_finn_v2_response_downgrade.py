from datetime import datetime, timezone
from types import SimpleNamespace

from backend.schemas.finn_v2_response_schema import ResponseDraft
from backend.services.finn_v2_response_downgrade_service import FinnV2ResponseDowngradeService


def test_response_downgrade_to_clarification_builds_single_question():
    service = FinnV2ResponseDowngradeService()
    draft = ResponseDraft(
        draft_id="draft-1",
        run_id="run-1",
        user_id=7,
        mode="EVALUATION",
        direct_answer="Ik kan dit nog niet precies beoordelen.",
        main_observation="Ik mis een expliciete setupkeuze.",
        evidence_set_hash="hash-1",
        created_at=datetime.now(timezone.utc),
    )
    result = service.downgrade_to_clarification(
        draft=draft,
        orchestrator_result=SimpleNamespace(selected_clarification=SimpleNamespace(question="Welke setup bedoel je precies?")),
    )

    assert result.mode == "CLARIFICATION"
    assert result.follow_up_question == "Welke setup bedoel je precies?"
