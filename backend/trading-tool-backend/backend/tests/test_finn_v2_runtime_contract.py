from types import SimpleNamespace

import pytest

from backend.domain.finn_v2_operation_registry import FinnV2OperationContractError, FinnV2OperationRegistry
from backend.domain.finn_v2_runtime_contract import build_terminal_runtime_contract


def _artifacts():
    return {
        "orchestrator_result": {
            "interaction_mode": "EVALUATE",
            "tool_plan": {"request_plan": {
                "initial_operation_id": "evaluate_plan",
                "operation_id": "evaluate_plan",
                "target_asset": "XAU",
                "target_asset_source": "explicit_message",
                "referenced_asset": "goud",
                "conversation_reference": "previous_verified_response",
                "conversation_reference_kind": "previous_verified_response",
                "operation_state": {"state_revision": 3},
            }},
        },
        "reasoning_result": {"status": "completed", "latency_ms": 42, "result": {"reasoning_provenance": {
            "provider_status": "completed", "parse_status": "passed", "validation_status": "passed",
        }}},
        "validation_result": {"integrity_status": "valid", "validation_id": "validation-1"},
        "policy_result": {"allowed": True, "policy_class": "read"},
        "verifier_result": {"passed": True, "action": "deliver", "reason_codes": []},
    }


def test_terminal_contract_is_versioned_hashed_and_does_not_expose_raw_message():
    contract = build_terminal_runtime_contract(
        run=SimpleNamespace(id="run-1", conversation_id="conversation-1", user_id=7, trace_id="trace-1"),
        artifacts=_artifacts(),
        terminal_status="completed",
        final_mode="EVALUATE",
        terminal_response_type="verified_response",
    )

    projection = contract.public_projection()
    assert contract.public_projection_hash
    assert projection["initial_operation_id"] == projection["final_operation_id"] == "evaluate_plan"
    assert projection["canonical_target"] == "XAU"
    assert projection["target_source"] == "explicit_message"
    assert projection["conversation_reference"] == "previous_verified_response"
    assert "message" not in projection


def test_registry_allows_only_typed_safe_operation_transitions():
    registry = FinnV2OperationRegistry()
    assert registry.resolve_transition(
        initial_operation_id="evaluate_plan",
        final_operation_id="clarify_request",
        reason="lineage_contract_without_context",
    ) == ("clarify_request", "lineage_contract_without_context")
    with pytest.raises(FinnV2OperationContractError, match="operation_transition_not_allowed"):
        registry.resolve_transition(
            initial_operation_id="evaluate_plan",
            final_operation_id="off_topic",
            reason="lineage_contract_without_context",
        )
