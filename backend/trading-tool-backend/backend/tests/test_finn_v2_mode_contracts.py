from datetime import datetime, timezone

import pytest

from backend.domain.finn_v2_contract import INTERACTION_MODES
from backend.schemas.finn_v2_reasoning_context_schema import ReasoningContextPackage, ReasoningPolicyContext
from backend.schemas.finn_v2_reasoning_schema import ReasoningResult
from backend.schemas.finn_v2_response_schema import ResponseDraft, VerifiedResponse
from backend.services.finn_v2_reasoning_prompt_service import FinnV2ReasoningPromptService


def _policy() -> ReasoningPolicyContext:
    return ReasoningPolicyContext(
        policy_class="read",
        allowed=True,
        proposal_allowed=False,
        confirmation_required=False,
        step_up_required=False,
        execution_allowed=False,
    )


@pytest.mark.parametrize("mode", INTERACTION_MODES)
def test_reasoning_context_accepts_every_contract_interaction_mode(mode):
    context = ReasoningContextPackage(
        run_id="run-1",
        user_id=7,
        user_message="Vraag",
        locale="nl-NL",
        interaction_mode=mode,
        orchestrator_result_id="orch-1",
        snapshot_id="snapshot-1",
        validation_id="validation-1",
        policy_decision_id="policy-1",
        evidence_set_hash="hash-1",
        policy=_policy(),
    )

    assert context.interaction_mode == mode


@pytest.mark.parametrize("mode", INTERACTION_MODES)
def test_prompt_service_supports_every_contract_interaction_mode(mode):
    service = FinnV2ReasoningPromptService()
    assert service.mode_instruction_for(mode)


@pytest.mark.parametrize("mode", INTERACTION_MODES)
def test_reasoning_and_delivery_models_accept_every_contract_interaction_mode(mode):
    reasoning_common = {
        "run_id": "run-1",
        "user_id": 7,
        "direct_answer": "Kort antwoord",
        "main_observation": "Belangrijkste observatie",
        "supporting_points": [],
        "claims": [],
        "uncertainty_summary": None,
        "uncertainty_codes": [],
        "next_step": None,
        "follow_up_question": "Welke setup bedoel je precies?" if mode == "CLARIFICATION" else None,
        "created_at": datetime.now(timezone.utc),
    }
    response_common = {
        **reasoning_common,
        "evidence_set_hash": "hash-1",
    }

    reasoning = ReasoningResult(
        reasoning_result_id="reasoning-1",
        mode=mode,
        model="gpt-test",
        evidence_refs_used=[],
        **reasoning_common,
    )
    draft = ResponseDraft(
        draft_id="draft-1",
        mode=mode,
        reasoning_result_id="reasoning-1",
        **response_common,
    )
    verified = VerifiedResponse(
        verified_response_id="verified-1",
        mode=mode,
        proposal_id=None,
        confirmation_required=False,
        verifier_status="passed",
        verifier_result_id="verifier-1",
        **response_common,
    )

    assert reasoning.mode == mode
    assert draft.mode == mode
    assert verified.mode == mode
