from datetime import datetime, timezone
from types import SimpleNamespace

from backend.schemas.finn_v2_reasoning_schema import ProposalCandidate
from backend.schemas.finn_v2_response_schema import ResponseDraft
from backend.services.finn_v2_response_verifier_service import FinnV2ResponseVerifierService


def test_proposal_candidate_must_match_policy_and_target_evidence():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-1",
        run_id="run-1",
        user_id=7,
        mode="CREATE_PROPOSAL",
        direct_answer="Ik kan een draft voorstel voorbereiden.",
        main_observation="De bot kan in paper mode worden geactiveerd.",
        proposal_candidate=ProposalCandidate(
            operation_type="activate_paper_bot",
            target_type="bot",
            target_id="12",
            proposed_changes={"bot_id": 12, "current_is_live": False},
            evidence_refs=["E1"],
            impact_summary="impact",
            risk_summary="risk",
            confirmation_required=True,
        ),
        evidence_set_hash="hash-1",
        created_at=datetime.now(timezone.utc),
    )
    evidence = {"E1": SimpleNamespace(entity_id="12", facts={"bot_id": 12, "is_live": False})}

    assert service._proposal_ok(
        draft,
        SimpleNamespace(operation_type="activate_live_bot", confirmation_required=True),
        evidence,
    ) is False


def test_create_strategy_proposal_uses_its_parent_setup_as_the_owned_target():
    service = FinnV2ResponseVerifierService(session=object())
    draft = ResponseDraft(
        draft_id="draft-strategy-1",
        run_id="run-strategy-1",
        user_id=7,
        mode="CREATE_PROPOSAL",
        direct_answer="Ik heb een strategiedraft voorbereid.",
        main_observation="De setup is geselecteerd.",
        proposal_candidate=ProposalCandidate(
            operation_type="create_strategy",
            target_type="strategy",
            target_id="12",
            proposed_changes={
                "setup_id": 12,
                "strategy_fields": {"setup_id": 12, "execution_mode": "fixed", "base_amount": 100},
            },
            evidence_refs=["E1"],
            impact_summary="impact",
            risk_summary="risk",
            confirmation_required=True,
        ),
        evidence_set_hash="hash-1",
        created_at=datetime.now(timezone.utc),
    )

    proposal = service._proposal_input_from_candidate(
        run=SimpleNamespace(id="run-strategy-1"),
        draft=draft,
        validation=SimpleNamespace(id="validation-1", snapshot_id="snapshot-1", evidence_set_hash="hash-1"),
    )

    assert proposal is not None
    assert proposal.target.target_type == "setup"
    assert proposal.target.target_id == "12"
    assert proposal.change.strategy_fields["setup_id"] == 12
