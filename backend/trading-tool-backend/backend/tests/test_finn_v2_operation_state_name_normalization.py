from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService
from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry


def test_setup_name_drops_trailing_non_persistence_safety_instruction():
    assert FinnV2OperationStateService._trim_setup_name_clause(
        "Measured Accumulation without persisting it"
    ) == "Measured Accumulation"


def test_setup_name_drops_broader_english_non_persistence_clause():
    assert FinnV2OperationStateService._trim_setup_name_clause(
        "Calm Builder without writing it yet"
    ) == "Calm Builder"


def test_setup_name_drops_direct_english_do_not_write_instruction():
    assert FinnV2OperationStateService._trim_setup_name_clause(
        "Patient Builder and do not write the setup yet"
    ) == "Patient Builder"


def test_setup_name_drops_following_timeframe_clause():
    assert FinnV2OperationStateService._trim_setup_name_clause(
        "Rustige swing en het timeframe is 4 uur"
    ) == "Rustige swing"


def test_strategy_inputs_are_collected_against_the_registry_contract():
    state = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("create_strategy")

    collected = state.explicit_inputs(
        contract=contract,
        message="Maak een fixed strategie voor setup 42; bedrag: 250; name: ETH swing.",
        explicit_asset="ETH",
    )

    assert collected == {
        "setup_id": 42,
        "execution_mode": "fixed",
        "base_amount": 250.0,
        "name": "ETH swing",
    }


def test_strategy_inputs_accept_natural_dutch_base_amount_wording():
    state = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("create_strategy")

    collected = state.explicit_inputs(
        contract=contract,
        message="Maak een fixed strategie met een basisinleg van 100 euro.",
        explicit_asset=None,
    )

    assert collected == {"execution_mode": "fixed", "base_amount": 100.0}


def test_guided_state_keeps_optional_inputs_declared_by_the_action_contract():
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("create_strategy")

    state = service.resolve(
        contract=contract,
        message="maak een strategie voor setup 42",
        explicit_asset=None,
        conversation_context={},
        supplied_inputs={"name": "ETH swing", "unknown": "discard"},
    )

    assert state.collected_inputs == {"setup_id": 42, "name": "ETH swing"}
    assert state.missing_required_inputs == ["execution_mode", "base_amount"]


def test_update_flow_collects_only_an_explicit_typed_changed_fields_object():
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("update_setup")

    typed = service.resolve(
        contract=contract,
        message='Wijzig setup 42 met {"timeframe": "4h", "name": "ETH swing"}',
        explicit_asset=None,
        conversation_context={},
    )
    prose = service.resolve(
        contract=contract,
        message="Wijzig setup 42 zodat hij beter wordt",
        explicit_asset=None,
        conversation_context={},
    )

    assert typed.collected_inputs == {
        "setup_id": 42,
        "changed_fields": {"timeframe": "4h", "name": "ETH swing"},
    }
    assert typed.missing_required_inputs == []
    assert prose.collected_inputs == {"setup_id": 42}
    assert prose.missing_required_inputs == ["changed_fields"]


def test_update_flow_collects_an_explicit_natural_field_value_without_a_second_schema():
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("update_setup")

    state = service.resolve(
        contract=contract,
        message="Wijzig setup 42 timeframe naar 4H",
        explicit_asset=None,
        conversation_context={},
    )

    assert state.collected_inputs == {
        "setup_id": 42,
        "changed_fields": {"timeframe": "4H"},
    }
    assert state.missing_required_inputs == []


def test_update_flow_collects_a_natural_post_reference_change_without_json():
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("update_setup")

    state = service.resolve(
        contract=contract,
        message="Werk mijn setup vandaag bij met tijdframe 1 uur",
        explicit_asset=None,
        conversation_context={},
        supplied_inputs={"setup_id": 42},
    )

    assert state.collected_inputs == {
        "setup_id": 42,
        "changed_fields": {"timeframe": "1H"},
    }
    assert state.missing_required_inputs == []


def test_bot_name_uses_the_same_contract_slot_parser_as_setup_names():
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("create_bot")

    state = service.resolve(
        contract=contract,
        message="Maak een bot voor strategy 52 met de naam Paper Scout",
        explicit_asset=None,
        conversation_context={},
    )

    assert state.collected_inputs == {"strategy_id": 52, "name": "Paper Scout"}
