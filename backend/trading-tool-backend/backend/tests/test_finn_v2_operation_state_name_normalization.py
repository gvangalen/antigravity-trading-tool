import pytest

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


def test_declassified_strategy_create_prompt_collects_manual_mode_and_amount():
    state = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("create_strategy")

    resolved = state.resolve(
        contract=contract,
        message="Maak voor die setup een strategie met execution mode handmatig en een basisbedrag van 100 euro.",
        explicit_asset=None,
        conversation_context={
            "previous_action_result": {
                "entity_type": "setup",
                "entity_id": 316,
                "owner_user_id": 7,
                "result_status": "succeeded",
            }
        },
    )

    # The existing persistence schema calls its deterministic manual mode
    # ``fixed``. The source prompt is still a complete, typed action request.
    assert resolved.collected_inputs == {
        "setup_id": 316,
        "execution_mode": "fixed",
        "base_amount": 100.0,
    }
    assert resolved.missing_required_inputs == []


def test_declassified_strategy_and_bot_updates_parse_set_field_op_value_without_ids():
    state = FinnV2OperationStateService()
    registry = FinnV2OperationRegistry()

    strategy = state.resolve(
        contract=registry.require_supported("update_strategy"),
        message="Wijzig die strategie en zet execution mode op automatisch.",
        explicit_asset=None,
        conversation_context={
            "previous_action_result": {
                "entity_type": "strategy",
                "entity_id": 41,
                "owner_user_id": 7,
                "result_status": "succeeded",
            }
        },
    )
    bot = state.resolve(
        contract=registry.require_supported("update_bot"),
        message="Wijzig die bot en zet het budget op 100 euro.",
        explicit_asset=None,
        conversation_context={
            "previous_action_result": {
                "entity_type": "bot",
                "entity_id": 61,
                "owner_user_id": 7,
                "result_status": "succeeded",
            }
        },
    )

    assert strategy.collected_inputs == {
        "strategy_id": 41,
        "changed_fields": {"execution_mode": "automatisch"},
    }
    assert strategy.missing_required_inputs == []
    assert bot.collected_inputs == {
        "bot_id": 61,
        "changed_fields": {"budget": 100},
    }
    assert bot.missing_required_inputs == []


@pytest.mark.parametrize("message", [
    "Maak een automatische strategie met een basisinleg van 100 euro.",
    "Create an automatic strategy with a base amount of 100.",
    "Erstelle eine automatisierte Strategie mit Grundbetrag 100.",
])
def test_strategy_execution_mode_normalizes_nl_en_de_automatic_variants(message):
    state = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("create_strategy")

    collected = state.explicit_inputs(contract=contract, message=message, explicit_asset=None)

    assert collected["execution_mode"] == "fixed"
    assert collected["base_amount"] == 100.0


def test_german_fixed_strategy_sentence_collects_contract_required_inputs():
    contract = FinnV2OperationRegistry().require_supported("create_strategy")

    collected = FinnV2OperationStateService().explicit_inputs(
        contract=contract,
        message="Erstelle eine feste Strategie mit einem Basisbetrag von 100 Euro.",
        explicit_asset=None,
    )

    assert collected["execution_mode"] == "fixed"
    assert collected["base_amount"] == 100.0


@pytest.mark.parametrize(
    ("operation_id", "message", "expected"),
    (
        ("update_setup", "Update my setup and set its timeframe to 1 hour.", {"timeframe": "1H"}),
        ("update_setup", "Aktualisiere mein Setup und setze den Zeitrahmen auf 1 Stunde.", {"timeframe": "1H"}),
        ("update_strategy", "Aktualisiere meine Strategie und setze den Basisbetrag auf 120 Euro.", {"base_amount": 120}),
    ),
)
def test_natural_update_clauses_use_existing_domain_field_keys(operation_id, message, expected):
    contract = FinnV2OperationRegistry().require_supported(operation_id)

    collected = FinnV2OperationStateService().explicit_inputs(
        contract=contract, message=message, explicit_asset=None,
    )

    assert collected["changed_fields"] == expected


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


def test_cross_conversation_action_result_fills_only_contract_declared_parent_slot():
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("create_strategy")

    state = service.resolve(
        contract=contract,
        message="Maak een fixed strategie met een basisinleg van 100.",
        explicit_asset=None,
        conversation_context={
            "previous_action_result": {
                "entity_type": "setup",
                "entity_id": 42,
                "owner_user_id": 7,
                "result_status": "succeeded",
            }
        },
    )

    assert state.collected_inputs == {
        "setup_id": 42,
        "execution_mode": "fixed",
        "base_amount": 100.0,
    }
    assert state.missing_required_inputs == []


def test_parent_action_result_continues_a_downstream_delete_without_injecting_ids():
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("delete_strategy")

    state = service.resolve(
        contract=contract,
        message="Verwijder de gekoppelde strategie.",
        explicit_asset=None,
        conversation_context={
            "previous_action_result": {
                "entity_type": "bot",
                "entity_id": 93,
                "parent_entity_type": "strategy",
                "parent_entity_id": 54,
                "owner_user_id": 7,
                "result_status": "succeeded",
            }
        },
    )

    assert state.collected_inputs == {"strategy_id": 54}
    assert state.missing_required_inputs == []


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


def test_update_flow_prefers_an_explicit_english_change_clause_after_the_object_reference():
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("update_setup")

    state = service.resolve(
        contract=contract,
        message="Update that setup and change the timeframe to one hour.",
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


def test_create_strategy_canonicalizes_a_natural_german_base_amount():
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("create_strategy")

    state = service.resolve(
        contract=contract,
        message="Erstelle eine fixed Strategie mit einem Grundbetrag von 100 Euro.",
        explicit_asset=None,
        conversation_context={},
        supplied_inputs={"setup_id": 42},
    )

    assert state.collected_inputs["execution_mode"] == "fixed"
    assert state.collected_inputs["base_amount"] == 100.0
    assert state.missing_required_inputs == []


def test_create_strategy_uses_the_shared_german_name_introducer_without_prefix_truncation():
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("create_strategy")

    state = service.resolve(
        contract=contract,
        message="Erstelle eine fixed Strategie mit dem Namen Geduldiger Aufbau.",
        explicit_asset=None,
        conversation_context={},
        supplied_inputs={"setup_id": 42, "base_amount": 100},
    )

    assert state.collected_inputs["name"] == "Geduldiger Aufbau"


def test_shared_name_parser_accepts_a_german_coordinated_name_clause():
    assert FinnV2OperationStateService._name_input_from_text(
        "Erstelle eine Strategie und dem Namen Geduldiger Aufbau."
    ) == "Geduldiger Aufbau"


def test_clarification_follow_up_persists_the_requested_change():
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("clarify_request")
    initial = service.resolve(
        contract=contract, message="Ik wil iets wijzigen.", explicit_asset=None, conversation_context={},
    )
    follow_up = service.resolve(
        contract=contract,
        message="Mijn watchlist aanpassen.",
        explicit_asset=None,
        conversation_context={"active_guided_operation": initial.dict()},
    )

    assert initial.missing_required_inputs == ["requested_change"]
    assert follow_up.collected_inputs["requested_change"] == "Mijn watchlist aanpassen."
    assert follow_up.missing_required_inputs == []
