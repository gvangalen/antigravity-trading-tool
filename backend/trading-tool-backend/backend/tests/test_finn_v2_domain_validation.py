from datetime import datetime, timezone
import asyncio

from backend.schemas.finn_v2_evidence_schema import ActiveSetupData, LinkedStrategyData
from backend.schemas.finn_v2_state_schema import FinancialStateSnapshot, StateNode, ToolOutcome
from backend.services.finn_v2_evidence_validator_service import FinnV2EvidenceValidatorService


class _ValidationRepo:
    async def get_for_snapshot_version(self, **_kwargs):
        return None

    async def create(self, **kwargs):
        return kwargs


def test_domain_validation_marks_conflicting_setup_strategy_invalid():
    service = FinnV2EvidenceValidatorService(session=object())
    service.validations = _ValidationRepo()
    snapshot = FinancialStateSnapshot(
        snapshot_id="snapshot-1",
        run_id="run-1",
        user_id=7,
        revision=1,
        evidence_set_hash="hash",
        assembled_at=datetime.now(timezone.utc),
        nodes=[
            StateNode(node_id="setup:11", entity_type="setup", entity_id="11", asset="BTC", payload_type="active_setup", payload=ActiveSetupData(setup_id=11, symbol="BTC"), availability="available", freshness="unknown", confidence="high"),
            StateNode(node_id="strategy:22", entity_type="strategy", entity_id="22", asset="ETH", payload_type="linked_strategy", payload=LinkedStrategyData(strategy_id=22, setup_id=99, symbol="ETH"), availability="available", freshness="unknown", confidence="high"),
        ],
        tool_outcomes=[
            ToolOutcome(tool_name="read_active_setup", status="available", artifact_id="a1"),
            ToolOutcome(tool_name="read_linked_strategy", status="available", artifact_id="a2"),
        ],
    )

    validation = asyncio.run(service.validate_snapshot(snapshot))

    assert validation.integrity_status == "invalid"
    assert any(issue.code == "conflict_setup_strategy" for issue in validation.issues)
