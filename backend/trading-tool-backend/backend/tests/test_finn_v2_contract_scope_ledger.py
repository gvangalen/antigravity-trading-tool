"""Contract scope ledger invariants for new FINN V2 runs."""
from datetime import datetime, timezone

import pytest

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.schemas.finn_v2_evidence_schema import EvidenceArtifact
from backend.schemas.finn_v2_tool_schema import ToolExecutionEnvelope
from backend.services.finn_v2_state_assembly_service import FinnV2StateAssemblyService


SCOPE_CASES = (
    ("active_asset", "read_active_asset"),
    ("indicator_configuration", "read_indicator_configuration"),
    ("active_setup", "read_active_setup"),
    ("linked_strategy", "read_linked_strategy"),
    ("linked_bot", "read_linked_bot"),
    ("bot_status", "read_bot_status"),
)


@pytest.mark.parametrize(("scope", "tool_name"), SCOPE_CASES)
def test_contract_scope_is_identical_in_binding_tool_envelope_evidence_and_state(scope, tool_name):
    registry = FinnV2OperationRegistry()
    contract = next(contract for contract in registry.list() if scope in contract.required_scopes)
    assert dict(contract.scope_tool_bindings)[scope] == tool_name

    envelope = ToolExecutionEnvelope(
        tool_name=tool_name,
        status="completed",
        success=True,
        schema_name=None,
        operation_id=contract.operation_id,
        operation_contract_version=contract.version,
    )
    artifact = EvidenceArtifact(
        artifact_id=f"artifact-{scope}",
        run_id="run-ledger",
        user_id=406,
        tool_call_id=1,
        tool_name=tool_name,
        information_scope=envelope.information_scope,
        operation_id=envelope.operation_id,
        operation_contract_version=envelope.operation_contract_version,
        source="test",
        resolution_source="test",
        user_scoped=True,
        freshness="fresh",
        schema_name=tool_name,
        schema_version="test",
        content_hash="hash",
        availability="available",
        created_at=datetime.now(timezone.utc),
    )
    node = FinnV2StateAssemblyService(session=object())._node_for_artifact(artifact)

    assert envelope.information_scope.value == scope
    assert artifact.information_scope.value == scope
    assert artifact.operation_id == contract.operation_id
    assert artifact.operation_contract_version == contract.version
    assert node is not None
    assert node.information_scope.value == scope
    assert node.evidence[0].information_scope.value == scope


def test_evaluate_plan_contract_binds_every_required_scope_once():
    contract = FinnV2OperationRegistry().require_supported("evaluate_plan")
    bindings = dict(contract.scope_tool_bindings)

    assert set(bindings) == set(contract.required_scopes)
    assert len(bindings) == len(contract.required_scopes)

