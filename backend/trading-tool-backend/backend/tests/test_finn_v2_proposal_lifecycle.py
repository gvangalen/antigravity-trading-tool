from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
import asyncio

from backend.schemas.finn_v2_policy_schema import FinnV2PolicyDecision
from backend.schemas.finn_v2_proposal_schema import ManualOrderChange, ProposalTarget, ValidatedProposalInput
from backend.services.finn_v2_proposal_service import FinnV2ProposalService


def test_proposal_creation_requires_typed_payload_and_starts_in_draft():
    service = FinnV2ProposalService(session=object())
    service.flags.is_proposals_enabled = lambda: True
    service.states.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="snapshot-1", evidence_set_hash="hash"))
    service.validations.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="validation-1", evidence_set_hash="hash"))
    service.proposals.get_by_idempotency_key_for_user = lambda **_kwargs: asyncio.sleep(0, result=None)
    service.proposals.get_by_payload_hash_for_run = lambda **_kwargs: asyncio.sleep(0, result=None)
    service.proposals.create = lambda **kwargs: asyncio.sleep(0, result=SimpleNamespace(**kwargs, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)))
    service.resolver.resolve_asset = lambda **_kwargs: asyncio.sleep(0, result={"asset": "BTC"})

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
        idempotency_key="c" * 16,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    record = asyncio.run(service.create_proposal(user_id=7, run_id="run-1", trace_id="trace-1", policy=policy, proposal_input=proposal_input))

    assert record.status == "draft"
    assert record.operation_type == "manual_order"
