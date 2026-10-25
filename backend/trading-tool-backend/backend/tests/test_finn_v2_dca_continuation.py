from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.services.finn_v2_responses_front_door import (
    FinnResponsesFrontDoor, _explicit_create_operation_request,
)
from backend.services.finn_v2_responses_proposal_selection import FinnResponsesProposalSelection
from backend.services.finn_v2_responses_tool_catalog import FinnResponsesToolCatalog
from backend.services.finn_v2_run_service import _prior_inputs_for_open_correction


def test_same_asset_restatement_binds_to_open_dca_draft():
    registry = FinnV2OperationRegistry()
    assert FinnResponsesFrontDoor.binds_guided_slot(
        message="een wekelijkse dca setup voor eth",
        contract=registry.require_supported("create_setup"),
        registry=registry,
        requested_slot="timeframe",
        collected_inputs={
            "symbol": "ETH", "setup_type": "dca", "dca_frequency": "weekly",
        },
    )


def test_conversational_request_with_asset_starts_new_setup_draft():
    assert _explicit_create_operation_request(
        "kan je voor eth ook een setup maken?"
    ) == "create_setup"
    assert _explicit_create_operation_request(
        "kan je uitleggen hoe je een setup maakt?"
    ) is None


def test_known_asset_replacement_preserves_dca_fields_but_not_old_asset():
    origin = {
        "symbol": "ETH", "name": "ETH concept", "setup_type": "dca",
        "timeframe": "1D", "dca_frequency": "weekly", "dca_day": "monday",
        "dca_amount_mode": "fixed", "base_amount": 100,
        "min_benchmark_score": None, "setup_id": 123,
    }
    carried = _prior_inputs_for_open_correction(
        origin, retain_parent_ids=False, target_change_requested=False,
        explicit_proposal_correction=True, corrected_instrument="AAPL",
        corrected_fields={}, corrected_name=None,
    )
    assert carried == {
        "name": "ETH concept", "setup_type": "dca", "timeframe": "1D",
        "dca_frequency": "weekly", "dca_day": "monday",
        "dca_amount_mode": "fixed", "base_amount": 100,
        "min_benchmark_score": None,
    }
    assert _prior_inputs_for_open_correction(
        origin, retain_parent_ids=False, target_change_requested=True,
        explicit_proposal_correction=True, corrected_instrument="AAPL",
        corrected_fields={}, corrected_name=None,
    ) == {}
    assert _prior_inputs_for_open_correction(
        origin, retain_parent_ids=False, target_change_requested=False,
        explicit_proposal_correction=False, corrected_instrument=None,
        corrected_fields={}, corrected_name=None,
    )["dca_frequency"] == "weekly"


def test_collecting_asset_switch_keeps_prior_user_rules_for_coverage():
    call = FinnResponsesToolCatalog().validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "draft_intent": "new", "inputs": {}},
    )
    old_request = "Maak een ETH DCA-setup en koop alleen wanneer RSI onder 30 is."
    correction = (
        "Correctie: ik bedoel AAPL in plaats van ETH. Behoud 1D en wekelijks "
        "maandag; noem de setup AAPL DCA. Toon het concept."
    )
    analysis = FinnResponsesProposalSelection().from_call(
        call=call, message=correction,
        conversation_context={"proposal_correction_result": {
            "status": "cancelled", "operation_id": "create_setup",
            "previous_asset": "ETH", "requested_instrument": "AAPL",
            "prior_inputs": {
                "setup_type": "dca", "timeframe": "1D",
                "dca_frequency": "weekly", "dca_day": "monday",
            },
            "prior_user_messages": [old_request],
            "prior_history_truncated": True,
        }},
        verified_asset=None,
    )
    state = analysis.request_plan.operation_state
    assert state["collected_inputs"]["symbol"] == "AAPL"
    assert state["collected_inputs"]["dca_day"] == "monday"
    assert state["guided_user_messages"] == [old_request, correction]
    assert state["guided_history_truncated"] is True


def test_unspecified_asset_switch_asks_for_ticker_then_keeps_dca_schedule():
    call = FinnResponsesToolCatalog().validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "draft_intent": "new", "inputs": {}},
    )
    correction = {"status": "cancelled", "operation_id": "create_setup",
                  "previous_asset": "ETH", "requested_instrument": None,
                  "awaiting_instrument": True,
                  "prior_inputs": {"setup_type": "dca", "timeframe": "1D",
                                   "dca_frequency": "weekly"}}
    first = FinnResponsesProposalSelection().from_call(
        call=call, message="ik bedoel een aandeel in plaats van ETH",
        conversation_context={"proposal_correction_result": correction},
        verified_asset="ETH",
    ).request_plan.operation_state
    assert first["collected_inputs"] == {
        "setup_type": "dca", "timeframe": "1D", "dca_frequency": "weekly",
    }
    assert first["next_missing_input"] == "symbol"
    second = FinnResponsesProposalSelection().from_call(
        call=call, message="AAPL",
        conversation_context={"proposal_correction_result": correction,
                              "active_guided_operation": first},
        verified_asset=None,
    ).request_plan.operation_state
    assert second["collected_inputs"]["symbol"] == "AAPL"
    assert second["collected_inputs"]["dca_frequency"] == "weekly"
