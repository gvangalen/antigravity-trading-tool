from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
import asyncio
import pytest

from backend.schemas.finn_v2_policy_schema import FinnV2PolicyDecision
from backend.schemas.finn_v2_proposal_schema import BotChange, ManualOrderChange, ProposalTarget, ValidatedProposalInput
from backend.services.finn_v2_proposal_service import FinnV2ProposalService
from backend.services.finn_v2_json_safety import to_json_safe


@pytest.mark.parametrize(
    ("changed_fields", "expected_error"),
    [({"unsupported_field": "weekly"}, "invalid_bot_change_fields"),
     ({"is_live": True}, "live_bot_update_not_allowed"),
     ({"budget_total_eur": 150}, None),
     ({"cadence": "wekelijks"}, None)],
)
def test_bot_update_fields_are_checked_before_confirmation(changed_fields, expected_error):
    service = FinnV2ProposalService(session=object())
    proposal_input = ValidatedProposalInput(
        operation_type="update_bot",
        target=ProposalTarget(target_type="bot", target_id="42", asset="BTC"),
        change=BotChange(bot_id=42, changed_fields=changed_fields),
        impact_summary="impact", risk_summary="risk", source_run_id="run-1",
        source_snapshot_id="snapshot-1", source_validation_id="validation-1",
        evidence_set_hash="hash", idempotency_key="b" * 16,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    if expected_error:
        with pytest.raises(ValueError, match=expected_error):
            asyncio.run(service._hydrate_domain_change(user_id=7, proposal_input=proposal_input))
    else:
        result = asyncio.run(service._hydrate_domain_change(user_id=7, proposal_input=proposal_input))
        assert result.change.changed_fields == (
            {"cadence": "weekly"} if "cadence" in changed_fields else changed_fields
        )


def test_proposal_creation_is_idempotent_per_user():
    service = FinnV2ProposalService(session=object())
    service.flags.is_proposals_enabled = lambda: True
    policy = FinnV2PolicyDecision(
        policy_decision_id="policy-1",
        run_id="run-1",
        user_id=7,
        policy_class="proposal",
        operation_type="manual_order",
        allowed=True,
        proposal_allowed=True,
        proposal_input_required=True,
        confirmation_required=True,
        step_up_required=False,
        execution_allowed=False,
        shadow_safe=True,
        created_at=datetime.now(timezone.utc),
    )
    proposal_input = ValidatedProposalInput(
        operation_type="manual_order",
        target=ProposalTarget(target_type="order", asset="BTC"),
        change=ManualOrderChange(asset="BTC", side="buy", order_type="market", quantity=Decimal("1")),
        impact_summary="impact",
        risk_summary="risk",
        source_run_id="run-1",
        source_snapshot_id="snapshot-1",
        source_validation_id="validation-1",
        evidence_set_hash="hash",
        idempotency_key="d" * 16,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    existing = SimpleNamespace(
        id="proposal-1",
        run_id="run-1",
        user_id=7,
        policy_decision_id="policy-1",
        status="draft",
        operation_type="manual_order",
        target_type="order",
        target_id=None,
        asset="BTC",
        payload_json=to_json_safe(proposal_input.dict()),
        payload_hash=service._payload_hash(to_json_safe(proposal_input.dict())),
        evidence_set_hash="hash",
        idempotency_key="d" * 16,
        requires_step_up_auth=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    service.proposals.get_by_idempotency_key_for_user = lambda **_kwargs: asyncio.sleep(0, result=existing)
    service.runs.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(conversation_id="conversation-1"))

    result = asyncio.run(service.create_proposal(user_id=7, run_id="run-1", trace_id="trace-1", policy=policy, proposal_input=proposal_input))

    assert result.proposal_id == "proposal-1"


def test_equivalent_active_draft_is_reused_across_distinct_runs():
    service = FinnV2ProposalService(session=object())
    service.flags.is_proposals_enabled = lambda: True
    key = FinnV2ProposalService.canonical_idempotency_key(
        operation_type="manual_order",
        target=ProposalTarget(target_type="order", asset="ADA"),
        change=ManualOrderChange(asset="ADA", side="buy", order_type="market", quantity=Decimal("1")),
    )
    first_input = ValidatedProposalInput(
        operation_type="manual_order",
        target=ProposalTarget(target_type="order", asset="ADA"),
        change=ManualOrderChange(asset="ADA", side="buy", order_type="market", quantity=Decimal("1")),
        impact_summary="impact", risk_summary="risk", source_run_id="run-1",
        source_snapshot_id="snapshot-1", source_validation_id="validation-1",
        evidence_set_hash="hash-1", idempotency_key=key,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    existing = SimpleNamespace(
        id="proposal-ada", run_id="run-1", user_id=7, policy_decision_id="policy-1", status="draft",
        operation_type="manual_order", target_type="order", target_id=None, asset="ADA",
        payload_json=to_json_safe(first_input.dict()), payload_hash="full-run-scoped-hash",
        evidence_set_hash="hash-1", idempotency_key=key, requires_step_up_auth=False,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    service.proposals.get_by_idempotency_key_for_user = lambda **_kwargs: asyncio.sleep(0, result=existing)
    service.runs.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(conversation_id="conversation-1"))
    second_input = first_input.copy(update={
        "source_run_id": "run-2", "source_snapshot_id": "snapshot-2",
        "source_validation_id": "validation-2", "evidence_set_hash": "hash-2",
    })
    policy = FinnV2PolicyDecision(
        policy_decision_id="policy-2", run_id="run-2", user_id=7, policy_class="proposal",
        operation_type="manual_order", allowed=True, proposal_allowed=True,
        proposal_input_required=True, confirmation_required=True, step_up_required=False,
        execution_allowed=False, shadow_safe=True, created_at=datetime.now(timezone.utc),
    )

    result = asyncio.run(service.create_proposal(
        user_id=7, run_id="run-2", trace_id="trace-2", policy=policy, proposal_input=second_input,
    ))

    assert result.proposal_id == "proposal-ada"
    assert second_input.idempotency_key == key


def test_equivalent_active_draft_is_not_reused_across_conversations():
    service = FinnV2ProposalService(session=object())
    service.flags.is_proposals_enabled = lambda: True
    policy = FinnV2PolicyDecision(
        policy_decision_id="policy-2", run_id="run-2", user_id=7, policy_class="proposal",
        operation_type="manual_order", allowed=True, proposal_allowed=True,
        proposal_input_required=True, confirmation_required=True, step_up_required=False,
        execution_allowed=False, shadow_safe=True, created_at=datetime.now(timezone.utc),
    )
    proposal_input = ValidatedProposalInput(
        operation_type="manual_order", target=ProposalTarget(target_type="order", asset="ADA"),
        change=ManualOrderChange(asset="ADA", side="buy", order_type="market", quantity=Decimal("1")),
        impact_summary="impact", risk_summary="risk", source_run_id="run-2",
        source_snapshot_id="snapshot-2", source_validation_id="validation-2",
        evidence_set_hash="hash-2", idempotency_key="k" * 16,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    existing = SimpleNamespace(
        id="proposal-old", run_id="run-1", user_id=7, status="draft",
        payload_json={}, idempotency_key="k" * 16,
    )
    created = SimpleNamespace(
        id="proposal-new", run_id="run-2", user_id=7, policy_decision_id="policy-2",
        status="draft", operation_type="manual_order", target_type="order", target_id=None,
        asset="ADA", payload_json={}, payload_hash="new", evidence_set_hash="hash-2",
        idempotency_key="", requires_step_up_auth=False,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    service.proposals.get_by_idempotency_key_for_user = lambda **_kwargs: asyncio.sleep(0, result=existing)
    service.runs.get_by_id_for_user = lambda **kwargs: asyncio.sleep(
        0, result=SimpleNamespace(conversation_id="conversation-1" if kwargs["run_id"] == "run-1" else "conversation-2")
    )
    service.proposals.get_by_payload_hash_for_run = lambda **_kwargs: asyncio.sleep(0, result=None)
    service.states.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(evidence_set_hash="hash-2"))
    service.validations.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(evidence_set_hash="hash-2"))
    service._validate_target_user_scope = lambda **_kwargs: asyncio.sleep(0)

    async def create(**kwargs):
        created.idempotency_key = kwargs["idempotency_key"]
        created.payload_json = kwargs["payload_json"]
        return created

    service.proposals.create = create
    result = asyncio.run(service.create_proposal(
        user_id=7, run_id="run-2", trace_id="trace-2", policy=policy, proposal_input=proposal_input,
    ))

    assert result.proposal_id == "proposal-new"
    assert created.idempotency_key == service.run_scoped_idempotency_key(canonical_key="k" * 16, run_id="run-2")
    assert existing.status == "draft"


def test_completed_equivalent_proposal_is_not_reused_by_a_new_run():
    service = FinnV2ProposalService(session=object())
    service.flags.is_proposals_enabled = lambda: True
    policy = FinnV2PolicyDecision(
        policy_decision_id="policy-2", run_id="run-2", user_id=7, policy_class="proposal",
        operation_type="manual_order", allowed=True, proposal_allowed=True,
        proposal_input_required=True, confirmation_required=True, step_up_required=False,
        execution_allowed=False, shadow_safe=True, created_at=datetime.now(timezone.utc),
    )
    canonical_key = FinnV2ProposalService.canonical_idempotency_key(
        operation_type="manual_order",
        target=ProposalTarget(target_type="order", asset="SOL"),
        change=ManualOrderChange(asset="SOL", side="buy", order_type="market", quantity=Decimal("1")),
    )
    proposal_input = ValidatedProposalInput(
        operation_type="manual_order", target=ProposalTarget(target_type="order", asset="SOL"),
        change=ManualOrderChange(asset="SOL", side="buy", order_type="market", quantity=Decimal("1")),
        impact_summary="impact", risk_summary="risk", source_run_id="run-2",
        source_snapshot_id="snapshot-2", source_validation_id="validation-2",
        evidence_set_hash="hash-2", idempotency_key=canonical_key,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    completed = SimpleNamespace(
        id="proposal-confirmed", run_id="run-1", user_id=7, policy_decision_id="policy-1",
        status="confirmed", operation_type="manual_order", target_type="order", target_id=None,
        asset="SOL", payload_json=to_json_safe(proposal_input.dict()), payload_hash="old",
        evidence_set_hash="hash-1", idempotency_key=canonical_key, requires_step_up_auth=False,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    created = SimpleNamespace(**{**completed.__dict__, "id": "proposal-new", "run_id": "run-2", "status": "draft"})
    created_key = {}

    service.proposals.get_by_idempotency_key_for_user = lambda **_kwargs: asyncio.sleep(0, result=completed)
    service.runs.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(conversation_id="conversation-1"))
    service.proposals.get_by_payload_hash_for_run = lambda **_kwargs: asyncio.sleep(0, result=None)
    service.states.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(evidence_set_hash="hash-2"))
    service.validations.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(evidence_set_hash="hash-2"))
    service._validate_target_user_scope = lambda **_kwargs: asyncio.sleep(0)

    async def create(**kwargs):
        created_key["value"] = kwargs["idempotency_key"]
        created.idempotency_key = kwargs["idempotency_key"]
        return created

    service.proposals.create = create
    result = asyncio.run(service.create_proposal(
        user_id=7, run_id="run-2", trace_id="trace-2", policy=policy, proposal_input=proposal_input,
    ))

    assert result.proposal_id == "proposal-new"
    assert created_key["value"] != canonical_key
    assert created_key["value"] == FinnV2ProposalService.run_scoped_idempotency_key(
        canonical_key=canonical_key, run_id="run-2",
    )
