from types import SimpleNamespace

import pytest

from backend.domain.finn_v2_operation_registry import FinnV2OperationContractError, FinnV2OperationRegistry
from backend.domain.finn_v2_runtime_contract import build_terminal_runtime_contract
from backend.domain.finn_v2_runtime_contract import terminal_projection


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


def test_terminal_projection_exposes_safe_phase_timings_when_persisted():
    projection = terminal_projection(
        {
            "identity": {"run_id": "run-1", "conversation_id": "conversation-1"},
            "phase_timestamps": {
                "created_at": "2026-09-05T10:00:00+00:00",
                "queued": "2026-09-05T10:00:00.100000+00:00",
                "collecting": "2026-09-05T10:00:00.300000+00:00",
                "terminal_at": "2026-09-05T10:00:01+00:00",
            },
        },
        status="completed",
        mode="READ",
        response={},
    )

    assert projection["timings_ms"] == {"total": 1000, "until_queued": 100, "until_collecting": 200, "terminal_persist": 700}


def test_terminal_projection_keeps_dispatch_selector_and_fast_path_boundaries():
    projection = terminal_projection(
        {
            "identity": {"run_id": "run-1"},
            "phase_timestamps": {
                "created_at": "2026-09-05T10:00:00+00:00",
                "dispatch_published": "2026-09-05T10:00:00.100000+00:00",
                "dispatch_claimed": "2026-09-05T10:00:00.300000+00:00",
                "context_loaded": "2026-09-05T10:00:00.500000+00:00",
                "selector_started": "2026-09-05T10:00:00.600000+00:00",
                "selector_completed": "2026-09-05T10:00:01.000000+00:00",
                "selection_persisted": "2026-09-05T10:00:01.050000+00:00",
                "fast_path_completed": "2026-09-05T10:00:01.060000+00:00",
                "terminal_at": "2026-09-05T10:00:01.100000+00:00",
            },
        },
        status="completed",
        mode="CAPABILITY",
        response={},
    )

    assert projection["timings_ms"] == {
        "total": 1100,
        "until_dispatch_published": 100,
        "until_dispatch_claimed": 200,
        "until_context_loaded": 200,
        "until_selector_started": 100,
        "until_selector_completed": 400,
        "until_selection_persisted": 50,
        "until_fast_path_completed": 10,
        "terminal_persist": 40,
    }
