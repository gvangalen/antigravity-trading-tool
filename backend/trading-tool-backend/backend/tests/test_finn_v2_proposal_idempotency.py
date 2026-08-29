from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
import asyncio

from backend.schemas.finn_v2_policy_schema import FinnV2PolicyDecision
from backend.schemas.finn_v2_proposal_schema import ManualOrderChange, ProposalTarget, ValidatedProposalInput
from backend.services.finn_v2_proposal_service import FinnV2ProposalService
from backend.services.finn_v2_json_safety import to_json_safe


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
