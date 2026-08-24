"""Contract scope ledger invariants for new FINN V2 runs."""
from datetime import datetime, timezone

import pytest

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.schemas.finn_v2_evidence_schema import EvidenceArtifact
from backend.schemas.finn_v2_orchestrator_schema import RequestPlan
from backend.schemas.finn_v2_response_schema import ResponseClaim, ResponseDraft
from backend.schemas.finn_v2_tool_schema import ToolExecutionEnvelope
from backend.services.finn_v2_state_assembly_service import FinnV2StateAssemblyService
from backend.services.finn_v2_response_verifier_service import FinnV2ResponseVerifierService


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


def test_contract_coverage_uses_all_valid_persisted_artifacts_not_only_draft_references():
    """A clarification/proposal draft cannot erase valid required evidence."""
    from types import SimpleNamespace

    contract = FinnV2OperationRegistry().require_supported("evaluate_plan")
    evidence = [
        SimpleNamespace(
            evidence_id=f"E{index}",
            information_scope=scope,
            availability="available",
            facts={"scope": scope},
            domain="plan_context",
            tool_name=dict(contract.scope_tool_bindings)[scope],
            asset=None,
            entity_type="test",
            entity_id=None,
            freshness="fresh",
            confidence="high",
        )
        for index, scope in enumerate(contract.required_scopes, start=1)
    ]
    draft = ResponseDraft(
        draft_id="draft-contract-ledger",
        run_id="run-contract-ledger",
        user_id=406,
        mode="EVALUATE",
        direct_answer="Je plancontext is beschikbaar.",
        main_observation="Controleer de samenhang van je planregels.",
        claims=[
            ResponseClaim(
                claim_id="claim-profile",
                claim_type="fact",
                text="Je plancontext is beschikbaar.",
                evidence_refs=["E1"],
                confidence="high",
            )
        ],
        evidence_set_hash="contract-ledger",
        created_at=datetime.now(timezone.utc),
    )

    verifier = FinnV2ResponseVerifierService(session=object())._deterministic_verify(
        run=SimpleNamespace(
            id="run-contract-ledger",
            user_id=406,
            message="Beoordeel mijn volledige plan.",
            conversation_id="conversation-contract-ledger",
        ),
        orchestrator_result=SimpleNamespace(
            analysis=SimpleNamespace(
                subject_scopes=[],
                request_plan=RequestPlan(
                    operation_id=contract.operation_id,
                    operation_contract_version=contract.version,
                    interaction_mode=contract.mode,
                ),
            ),
            selected_clarification=None,
        ),
        policy=SimpleNamespace(allowed=True, proposal_allowed=True, confirmation_required=False, operation_type=None),
        context=SimpleNamespace(evidence=evidence, uncertainty_codes=[]),
        validation=SimpleNamespace(id="validation-contract-ledger", evidence_set_hash="contract-ledger", integrity_status="valid"),
        draft=draft,
        repair_attempt=0,
        force_action="deliver",
    )

    assert verifier.coverage.required_scopes == list(contract.required_scopes)
    assert verifier.coverage.covered_scopes == sorted(contract.required_scopes)
    assert verifier.coverage.missing_scopes == []
    assert verifier.coverage.coverage_ok is True
