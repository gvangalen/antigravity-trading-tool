from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.schemas.finn_v2_proposal_schema import (
    ManualOrderChange,
    ProposalTarget,
    StrategyCreateChange,
    ValidatedProposalInput,
)


def test_manual_order_change_uses_decimal_and_forbids_floats_shape_mismatch():
    payload = ValidatedProposalInput(
        operation_type="manual_order",
        target=ProposalTarget(target_type="order", asset="btc"),
        change=ManualOrderChange(asset="btc", side="buy", order_type="limit", quantity=Decimal("1.25"), limit_price=Decimal("25000")),
        impact_summary="summary",
        risk_summary="risk",
        source_run_id="run-1",
        source_snapshot_id="snapshot-1",
        source_validation_id="validation-1",
        evidence_set_hash="hash",
        idempotency_key="a" * 16,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    assert payload.change.quantity == Decimal("1.25")
    assert payload.target.asset == "BTC"


def test_proposal_schema_rejects_operation_change_mismatch():
    with pytest.raises(ValueError):
        ValidatedProposalInput(
            operation_type="update_setup",
            target=ProposalTarget(target_type="setup", target_id="11"),
            change=ManualOrderChange(asset="BTC", side="buy", order_type="market", quantity=Decimal("1")),
            impact_summary="summary",
            risk_summary="risk",
            source_run_id="run-1",
            source_snapshot_id="snapshot-1",
            source_validation_id="validation-1",
            evidence_set_hash="hash",
            idempotency_key="b" * 16,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )


def test_create_strategy_uses_one_typed_draft_payload_before_confirmation():
    payload = ValidatedProposalInput(
        operation_type="create_strategy",
        target=ProposalTarget(target_type="strategy", target_id="91", asset="ETH"),
        change=StrategyCreateChange(
            strategy_fields={"setup_id": 91, "execution_mode": "fixed", "base_amount": 250, "name": "ETH swing"}
        ),
        impact_summary="Create an ETH strategy draft.",
        risk_summary="Confirmation is required before it is saved.",
        source_run_id="run-1",
        source_snapshot_id="snapshot-1",
        source_validation_id="validation-1",
        evidence_set_hash="hash",
        idempotency_key="c" * 16,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    assert payload.operation_type == "create_strategy"
    assert payload.change.strategy_fields["setup_id"] == 91
