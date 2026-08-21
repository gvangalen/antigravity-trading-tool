from datetime import datetime, timezone

import pytest

from backend.schemas.finn_v2_reasoning_schema import ProposalCandidate, ReasoningClaim, ReasoningResult
from backend.schemas.finn_v2_reasoning_context_schema import ReasoningContextPackage
from backend.services.finn_v2_reasoning_prompt_service import FinnV2ReasoningPromptService


def test_reasoning_result_rejects_proposal_candidate_outside_proposal_or_action():
    with pytest.raises(ValueError):
        ReasoningResult(
            reasoning_result_id="r1",
            run_id="run-1",
            user_id=7,
            mode="FACT",
            direct_answer="answer",
            main_observation="observation",
            claims=[],
            proposal_candidate=ProposalCandidate(
                operation_type="update_setup",
                target_type="setup",
                proposed_changes={},
                impact_summary="impact",
                risk_summary="risk",
                confirmation_required=True,
            ),
            evidence_refs_used=[],
            model="gpt-test",
            created_at=datetime.now(timezone.utc),
        )


def test_reasoning_claim_requires_schema_constrained_fields():
    claim = ReasoningClaim(
        claim_id="C1",
        claim_type="fact",
        text="The linked strategy uses BTC.",
        evidence_refs=["E1"],
        confidence="high",
    )

    assert claim.evidence_refs == ["E1"]


def test_proposal_candidate_accepts_json_encoded_proposed_changes():
    candidate = ProposalCandidate(
        operation_type="update_setup",
        target_type="setup",
        proposed_changes='{"changed_fields":{"risk_profile":"aggressive"}}',
        impact_summary="impact",
        risk_summary="risk",
        confirmation_required=True,
    )

    assert candidate.proposed_changes == {"changed_fields": {"risk_profile": "aggressive"}}


def test_reasoning_prompt_schema_keeps_proposed_changes_openai_compatible():
    schema = FinnV2ReasoningPromptService().response_schema()
    proposal_branch = schema["properties"]["proposal_candidate"]["anyOf"][1]

    assert proposal_branch["properties"]["proposed_changes"] == {"type": "string"}


def test_reasoning_prompt_includes_the_grounded_context_and_repair_contract():
    context = ReasoningContextPackage.parse_obj({
        "run_id": "run-1",
        "user_id": 7,
        "user_message": "Welke setup is actief?",
        "locale": "nl",
        "interaction_mode": "READ",
        "orchestrator_result_id": "orchestrator-1",
        "snapshot_id": "snapshot-1",
        "validation_id": "validation-1",
        "policy_decision_id": "policy-1",
        "evidence_set_hash": "hash-1",
        "evidence": [{
            "evidence_id": "E1",
            "artifact_id": "artifact-1",
            "tool_name": "read_active_setup",
            "domain": "setup",
            "entity_type": "setup",
            "entity_id": "309",
            "asset": "BTC",
            "source": "setup_repository",
            "freshness": "fresh",
            "confidence": "high",
            "facts": {"timeframe": "4H"},
        }],
        "policy": {
            "policy_class": "read",
            "allowed": True,
            "proposal_allowed": False,
            "confirmation_required": False,
            "step_up_required": False,
            "execution_allowed": False,
        },
    })

    prompt = FinnV2ReasoningPromptService().build_user_prompt(context, repair_attempt=True)

    assert '"entity_id":"309"' in prompt
    assert "previous response did not satisfy" in prompt
