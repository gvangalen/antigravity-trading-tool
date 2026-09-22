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
    assert projection["action_polarity"] == "evaluate"
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


def test_terminal_projection_exposes_safe_provider_and_asset_observability():
    projection = terminal_projection(
        {
            "identity": {"run_id": "run-provider", "conversation_id": "conversation-provider"},
            "canonical_target": "MSFT",
            "target_source": "workspace_context",
        },
        status="completed",
        mode="EVALUATE",
        response={
            "mode": "EVALUATE",
            "reasoning_provenance": {
                "provider_called": True,
                "provider_status": "completed",
                "provider_response_id": "private-provider-id",
            },
        },
    )

    assert projection["target_asset"] == "MSFT"
    assert projection["target_asset_source"] == "workspace_context"
    assert projection["modelcall_attempted"] is True
    assert projection["modelcall_outcome"] == "completed"
    assert projection["response_type"] == "EVALUATE"
    assert "provider_response_id" not in projection


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


def test_terminal_projection_exposes_typed_contract_input_and_reason_metadata():
    projection = terminal_projection(
        {
            "contract_id": "contract-1",
            "contract_revision": 7,
            "identity": {"run_id": "run-1", "conversation_id": "conversation-1"},
            "initial_operation_id": "create_setup",
            "final_operation_id": "clarify_request",
            "conversation_reference_kind": "verified_response",
            "supplied_inputs": {"asset": "BTC"},
            "missing_inputs": ["timeframe"],
            "terminal_reason": "missing_required_input",
        },
        status="downgraded",
        mode="CLARIFY",
        response={},
    )

    assert projection["contract_revision"] == 7
    assert projection["supplied_inputs"] == {"asset": "BTC"}
    assert projection["missing_inputs"] == ["timeframe"]
    assert projection["terminal_reason"] == "missing_required_input"


def test_terminal_projection_exposes_safe_persisted_setup_draft():
    projection = terminal_projection(
        {
            "identity": {"run_id": "run-setup", "conversation_id": "conversation-setup"},
            "initial_operation_id": "create_setup",
            "final_operation_id": "create_setup",
            "setup_draft": {
                "operation_id": "create_setup",
                "draft_status": "collecting",
                "supplied_inputs": {"symbol": "BTC", "name": "FINN DCA Flow 0914"},
                "missing_inputs": ["dca_frequency"],
                "requested_slot": "dca_frequency",
                "field_sources": {"symbol": "context", "name": "explicit"},
            },
        },
        status="clarification_required",
        mode="CREATE_PROPOSAL",
        response={},
    )

    assert projection["setup_draft"]["requested_slot"] == "dca_frequency"
    assert projection["setup_draft"]["supplied_inputs"]["name"] == "FINN DCA Flow 0914"


def test_guided_strategy_and_bot_state_is_persisted_on_the_runtime_contract():
    from backend.domain.finn_v2_runtime_contract import record_guided_draft

    for operation_id, requested_slot in (
        ("create_strategy", "execution_mode"),
        ("create_bot", "name"),
    ):
        state = {
            "initial_operation_id": operation_id,
            "final_operation_id": operation_id,
        }
        guided_state = {
            "operation_id": operation_id,
            "collected_inputs": {"symbol": "BTC"},
            "missing_required_inputs": [requested_slot],
            "next_missing_input": requested_slot,
        }

        persisted = record_guided_draft(state, guided_state=guided_state)

        assert persisted["guided_state"] == guided_state
        assert persisted["action_draft"]["operation_id"] == operation_id
        assert persisted["action_draft"]["requested_slot"] == requested_slot
        assert persisted["action_draft"]["supplied_inputs"] == {"symbol": "BTC"}
        projection = terminal_projection(
            persisted,
            status="clarification_required",
            mode="CREATE_PROPOSAL",
            response={},
        )
        assert projection["action_draft"] == persisted["action_draft"]


@pytest.mark.parametrize(
    ("operation_id", "requested_slot"),
    [
        ("update_setup", "setup_id"),
        ("delete_setup", "setup_id"),
        ("update_strategy", "strategy_id"),
        ("delete_strategy", "strategy_id"),
        ("update_bot", "bot_id"),
        ("deactivate_bot", "bot_id"),
        ("delete_bot", "bot_id"),
    ],
)
def test_disambiguating_write_actions_persist_the_original_operation(operation_id, requested_slot):
    from backend.domain.finn_v2_runtime_contract import record_guided_draft

    guided_state = {
        "operation_id": operation_id,
        "collected_inputs": {"changed_fields": {"timeframe": "1D"}},
        "missing_required_inputs": [requested_slot],
        "next_missing_input": requested_slot,
        "status": "collecting",
    }
    persisted = record_guided_draft(
        {"initial_operation_id": operation_id, "final_operation_id": operation_id},
        guided_state=guided_state,
    )

    assert persisted["guided_state"]["operation_id"] == operation_id
    assert persisted["action_draft"]["requested_slot"] == requested_slot


def test_terminal_projection_derives_required_inputs_and_polarity_from_registry():
    projection = terminal_projection(
        {
            "identity": {"run_id": "run-1"},
            "initial_operation_id": "create_setup",
            "supplied_inputs": {"symbol": "SOL", "setup_type": "swing"},
        },
        status="clarification_required",
        mode="CLARIFICATION",
        response={},
    )

    assert projection["action_polarity"] == "create"
    assert projection["required_inputs"] == list(
        FinnV2OperationRegistry().require_supported("create_setup").required_inputs_for(
            {"symbol": "SOL", "setup_type": "swing"}
        )
    )
    assert projection["missing_inputs"] == []


def test_terminal_projection_exposes_one_outbox_dispatch_and_attempt_count():
    projection = terminal_projection(
        {
            "identity": {"run_id": "run-1"},
            "dispatch": {
                "dispatch_id": "dispatch-1", "dispatch_count": 1,
                "attempt_count": 1, "status": "completed",
            },
        },
        status="completed", mode="READ", response={},
    )

    assert projection["dispatch_id"] == "dispatch-1"
    assert projection["dispatch_count"] == projection["attempt_count"] == 1
