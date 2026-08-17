from datetime import datetime, timezone

from backend.schemas.finn_v2_reasoning_schema import PersistedReasoningRecord, ReasoningClaim, ReasoningResult
from backend.services.finn_v2_response_draft_service import FinnV2ResponseDraftService


def test_response_draft_is_built_from_reasoning_result():
    service = FinnV2ResponseDraftService()
    record = PersistedReasoningRecord(
        reasoning_result_id="reasoning-1",
        run_id="run-1",
        user_id=7,
        orchestrator_result_id="orch-1",
        policy_decision_id="policy-1",
        snapshot_id="snapshot-1",
        validation_id="validation-1",
        status="ready",
        mode="FACT",
        context_version="2026-08-17.block6",
        evidence_set_hash="hash-1",
        input_hash="input-1",
        prompt_version="2026-08-17.block6",
        reasoning_version="2026-08-17.block6",
        model="gpt-test",
        result=ReasoningResult(
            reasoning_result_id="reasoning-1",
            run_id="run-1",
            user_id=7,
            mode="FACT",
            direct_answer="De setup is actief.",
            main_observation="De setup is aantoonbaar aanwezig.",
            claims=[ReasoningClaim(claim_id="C1", claim_type="fact", text="De setup is actief.", evidence_refs=["E1"], confidence="high")],
            model="gpt-test",
            created_at=datetime.now(timezone.utc),
        ),
        created_at=datetime.now(timezone.utc),
    )

    draft = service.build(reasoning_record=record)

    assert draft.reasoning_result_id == "reasoning-1"
    assert draft.claims[0].claim_id == "C1"
