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


@pytest.mark.parametrize(
    ("message", "selector_name", "expected"),
    (
        (
            "Maak een paper-bot met naam Rustige Paper Bot voor strategie Rustige Strategie.",
            "Rustige Paper Bot voor strategie Rustige Strategie",
            "Rustige Paper Bot",
        ),
        (
            "Create a paper bot named Calm Paper Bot for strategy Calm Strategy.",
            "Calm Paper Bot for strategy Calm Strategy",
            "Calm Paper Bot",
        ),
        (
            "Erstelle einen Paper-Bot namens Ruhiger Bot für Strategie Ruhige Strategie.",
            "Ruhiger Bot für Strategie Ruhige Strategie",
            "Ruhiger Bot",
        ),
    ),
)
def test_create_bot_name_excludes_linked_strategy_clause(message, selector_name, expected):
    contract = FinnV2OperationRegistry().require_supported("create_bot")

    collected = FinnV2OperationStateService().explicit_inputs(
        contract=contract,
        message=message,
        explicit_asset=None,
    )
    resolved = FinnV2OperationStateService().resolve(
        contract=contract,
        message=message,
        explicit_asset=None,
        conversation_context={},
        supplied_inputs={"name": selector_name},
        derived_inputs={"strategy_id": 42},
    )

    assert FinnV2OperationStateService._trim_linked_strategy_clause(
        str(collected.get("name") or selector_name)
    ) == expected
    assert resolved.collected_inputs["name"] == expected


def test_strategy_inputs_are_collected_against_the_registry_contract():
    state = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("create_strategy")

    collected = state.explicit_inputs(
        contract=contract,
        message="Maak een fixed strategie voor setup id 42; bedrag: 250; name: ETH swing.",
        explicit_asset="ETH",
    )

    assert collected == {
        "setup_id": 42,
        "execution_mode": "fixed",
        "base_amount": 250.0,
        "name": "ETH swing",
        # An explicitly selected asset is a strategy override, while an
        # omitted asset is deliberately defaulted from the parent setup.
        "symbol": "ETH",
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


@pytest.mark.parametrize(
    ("message", "expected"),
    (
        ("Voeg RSI toe aan Technisch bewijs.", {"name": "rsi", "category": "technical"}),
        ("Voeg DXY toe aan Macro.", {"name": "dxy", "category": "macro"}),
        ("Voeg Price toe aan Marktindicatoren.", {"name": "price", "category": "market"}),
        ("Verwijder Prijs als marktindicator voor MSFT.", {"name": "price", "category": "market"}),
        ("Entferne Preis als Marktindikator für MSFT.", {"name": "price", "category": "market"}),
        ("Add MA 200 to technical evidence.", {"name": "ma_200", "category": "technical"}),
    ),
)
def test_indicator_inputs_use_every_canonical_catalog(message, expected):
    assert FinnV2OperationStateService._indicator_input_from_text(message) == expected


def test_completed_indicator_state_is_not_reused_for_a_fresh_indicator_request():
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("create_indicator_configuration")

    state = service.resolve(
        contract=contract,
        message="Voeg RSI toe aan Technisch bewijs voor BTC.",
        explicit_asset="BTC",
        conversation_context={
            "active_guided_operation": {
                "operation_id": contract.operation_id,
                "contract_version": contract.version,
                "collected_inputs": {"asset": "BTC", "category": "macro", "indicator": "dxy"},
                "missing_required_inputs": [],
                "status": "proposed",
            }
        },
    )

    assert state.collected_inputs["indicator"] == "rsi"
    assert state.collected_inputs["category"] == "technical"


@pytest.mark.parametrize(
    ("message", "expected_name"),
    (
        (
            "Maak strategie Final BTC Strategy voor setup Final BTC Setup 2, BTC 4H, fixed €100 per "
            "uitvoering, entry €76.000, stop-loss €72.000, targets €82.000 en €86.000, "
            "risicostijl gebalanceerd.",
            "Final BTC Strategy",
        ),
        (
            "Create strategy Final BTC Strategy for setup Final BTC Setup 2, fixed EUR 100 per execution, "
            "entry EUR 76,000, stop-loss EUR 72,000, targets EUR 82,000 and EUR 86,000, risk style balanced.",
            "Final BTC Strategy",
        ),
        (
            "Erstelle Strategie Final BTC Strategy für Setup Final BTC Setup 2, feste 100 EUR je Ausführung, "
            "Einstieg 76000 EUR, Stop-Loss 72000 EUR, Ziele 82000 und 86000, Risikostil ausgewogen.",
            "Final BTC Strategy",
        ),
    ),
)
def test_complete_natural_strategy_request_collects_typed_contract_inputs(message, expected_name):
    contract = FinnV2OperationRegistry().require_supported("create_strategy")

    collected = FinnV2OperationStateService().explicit_inputs(
        contract=contract,
        message=message,
        explicit_asset="BTC",
    )

    assert collected["name"] == expected_name
    assert collected["execution_mode"] == "fixed"
    assert collected["base_amount"] == 100.0
    assert collected["entry"] == 76000.0
    assert collected["stop_loss"] == 72000.0
    assert collected["targets"] == [82000.0, 86000.0]
    assert collected["risk_profile"] == "balanced"


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
    assert resolved.missing_required_inputs == ["name", "entry", "stop_loss", "targets", "risk_profile"]


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
        "changed_fields": {"budget_total_eur": 100},
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
        ("update_setup", "Wijzig setup FINN DCA Flow 0917 naar timeframe 1D.", {"timeframe": "1D"}),
        ("update_setup", "Wijzig deze setup naar timeframe 1D.", {"timeframe": "1D"}),
        ("update_strategy", "Aktualisiere meine Strategie und setze den Basisbetrag auf 120 Euro.", {"base_amount": 120}),
        ("update_strategy", "Wijzig deze strategie en zet het bedrag naar €150.", {"base_amount": 150}),
        ("update_strategy", "Wijzig het bedrag van mijn BTC strategie naar 300 euro.", {"base_amount": 300}),
        ("update_strategy", "Change the amount of my BTC strategy to 300 euro.", {"base_amount": 300}),
        ("update_strategy", "Ändere den Betrag meiner BTC Strategie auf 300 Euro.", {"base_amount": 300}),
    ),
)
def test_natural_update_clauses_use_existing_domain_field_keys(operation_id, message, expected):
    contract = FinnV2OperationRegistry().require_supported(operation_id)

    collected = FinnV2OperationStateService().explicit_inputs(
        contract=contract, message=message, explicit_asset=None,
    )

    assert collected["changed_fields"] == expected


def test_numeric_suffix_with_leading_zero_remains_part_of_natural_strategy_name():
    contract = FinnV2OperationRegistry().require_supported("delete_strategy")

    collected = FinnV2OperationStateService().explicit_inputs(
        contract=contract,
        message="Verwijder strategie FINN Trend Strategy 0917.",
        explicit_asset=None,
    )

    assert "strategy_id" not in collected


def test_guided_state_keeps_optional_inputs_declared_by_the_action_contract():
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("create_strategy")

    state = service.resolve(
        contract=contract,
        message="maak een strategie voor setup id 42",
        explicit_asset=None,
        conversation_context={},
        supplied_inputs={"name": "ETH swing", "unknown": "discard"},
    )

    assert state.collected_inputs == {"setup_id": 42, "name": "ETH swing"}
    assert state.missing_required_inputs == [
        "execution_mode", "base_amount", "entry", "stop_loss", "targets", "risk_profile"
    ]


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
    assert state.missing_required_inputs == ["name", "entry", "stop_loss", "targets", "risk_profile"]


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


@pytest.mark.parametrize(
    "message",
    (
        "Maak strategie Momentum met entry 62000, stop-loss 59800, targets 64500 en 67000 en risicoprofiel defensief.",
        "Create strategy Momentum with entry 62000, stop loss 59800, targets 64500 and 67000 and risk profile defensive.",
        "Erstelle Strategie Momentum mit Einstieg 62000, Stop-Loss 59800, Ziele 64500 und 67000 und Risikoprofil defensiv.",
    ),
)
def test_create_strategy_extracts_explicit_trade_contract_fields(message):
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("create_strategy")

    state = service.resolve(
        contract=contract,
        message=message,
        explicit_asset=None,
        conversation_context={},
        supplied_inputs={"setup_id": 42, "name": "Momentum", "execution_mode": "fixed", "base_amount": 100},
    )

    assert state.collected_inputs["entry"] == 62000.0
    assert state.collected_inputs["stop_loss"] == 59800.0
    assert state.collected_inputs["targets"] == [64500.0, 67000.0]
    assert state.collected_inputs["risk_profile"] == "conservative"
    assert state.missing_required_inputs == []


def test_create_strategy_does_not_treat_risk_percentage_as_a_target():
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("create_strategy")

    state = service.resolve(
        contract=contract,
        message=(
            "Maak strategie Budget Flow met entry 76000 euro, stop-loss op 72000 euro, "
            "target op 84000 euro en maximaal 1 procent risico."
        ),
        explicit_asset="BTC",
        conversation_context={},
        supplied_inputs={
            "setup_id": 42,
            "name": "Budget Flow",
            "execution_mode": "fixed",
            "base_amount": 100,
        },
    )

    assert state.collected_inputs["targets"] == [84000.0]
    assert "risk_profile" not in state.collected_inputs
    assert state.missing_required_inputs == ["risk_profile"]


def test_create_bot_preserves_an_explicit_optional_budget():
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("create_bot")

    state = service.resolve(
        contract=contract,
        message="Maak paper-bot Budget Bot voor mijn strategie met een budget van 500 euro.",
        explicit_asset="BTC",
        conversation_context={},
        supplied_inputs={"strategy_id": 84, "name": "Budget Bot"},
    )

    assert state.collected_inputs == {
        "budget_total_eur": 500.0,
        "strategy_id": 84,
        "name": "Budget Bot",
    }
    assert state.missing_required_inputs == []


def test_update_bot_extracts_budget_without_exposing_setup_copy():
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("update_bot")

    state = service.resolve(
        contract=contract,
        message="Wijzig het budget van mijn paper-bot Budget Bot naar 1000 euro.",
        explicit_asset="BTC",
        conversation_context={},
        supplied_inputs={"bot_id": 7},
    )

    assert state.collected_inputs == {
        "changed_fields": {"budget_total_eur": 1000},
        "bot_id": 7,
    }
    assert state.missing_required_inputs == []
    assert service.clarification_question("changed_fields", contract=contract) == (
        "Wat wil je aan deze paper-bot wijzigen?"
    )


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Wijzig het budget van paper-bot Audit BTC Paper naar €1.000.", 1000),
        ("Set the budget of Audit BTC Paper to EUR 1,000.", 1000),
        ("Setze das Budget von Audit BTC Paper auf 1.000 Euro.", 1000),
        ("Wijzig het budget naar €1,5.", 1.5),
        ("Wijzig het budget van paper-bot BTC Paper 6mtjwt naar 1000 euro.", 1000),
        ("Wijzig het budget van paper-bot BTC Paper 6mtjwt naar duizend euro.", 1000),
        ("Set the budget of BTC Paper 6mtjwt to one thousand euro.", 1000),
    ],
)
def test_update_bot_preserves_localized_budget_magnitude(message, expected):
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("update_bot")

    state = service.resolve(
        contract=contract,
        message=message,
        explicit_asset="BTC",
        conversation_context={},
        supplied_inputs={"bot_id": 4},
    )

    assert state.collected_inputs == {
        "changed_fields": {"budget_total_eur": expected},
        "bot_id": 4,
    }
    assert state.missing_required_inputs == []


@pytest.mark.parametrize(
    "message",
    (
        "Wijzig deze setup van timeframe 4H naar 1D.",
        "Zet het timeframe van BTC Setup op 1D.",
    ),
)
def test_update_setup_extracts_only_the_new_timeframe(message):
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("update_setup")

    state = service.resolve(
        contract=contract,
        message=message,
        explicit_asset="BTC",
        conversation_context={},
        supplied_inputs={"setup_id": 42},
    )

    assert state.collected_inputs == {
        "setup_id": 42,
        "changed_fields": {"timeframe": "1D"},
    }
    assert state.missing_required_inputs == []


def test_complete_dutch_strategy_prompt_extracts_execution_and_risk_synonyms():
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("create_strategy")

    state = service.resolve(
        contract=contract,
        message=(
            "Maak strategie BTC Vast voor setup BTC Basis met vaste uitvoering, "
            "100 euro, entry 76000, stop-loss 72000, targets 82000 en 86000 "
            "en gebalanceerd risico."
        ),
        explicit_asset="BTC",
        conversation_context={"previous_action_result": {
            "entity_type": "setup", "entity_id": 42, "result_status": "succeeded"
        }},
    )

    assert state.collected_inputs["execution_mode"] == "fixed"
    assert state.collected_inputs["risk_profile"] == "balanced"
    assert "execution_mode" not in state.missing_required_inputs
    assert "risk_profile" not in state.missing_required_inputs


@pytest.mark.parametrize(
    ("slot", "question"),
    (
        ("base_amount", "Welk bedrag wil je per uitvoering inzetten?"),
        ("entry", "Bij welke koers wil je instappen?"),
        ("stop_loss", "Waar wil je je stop-loss zetten?"),
        ("targets", "Welke koersdoelen wil je gebruiken?"),
        ("risk_profile", "Welke risicostijl wil je gebruiken: voorzichtig, gebalanceerd of offensief?"),
    ),
)
def test_strategy_guided_questions_use_human_slot_copy(slot, question):
    contract = FinnV2OperationRegistry().require_supported("create_strategy")
    assert FinnV2OperationStateService.clarification_question(slot, contract=contract) == question


def test_strategy_guided_slot_reply_preserves_prior_contract_inputs():
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("create_strategy")
    context = {
        "operation_state": {
            "operation_id": "create_strategy",
            "contract_version": contract.version,
            "state_revision": 4,
            "collected_inputs": {
                "setup_id": 42,
                "name": "Momentum",
                "execution_mode": "fixed",
                "base_amount": 100,
                "entry": 62000,
                "stop_loss": 59800,
            },
            "input_sources": {},
            "resolved_entities": {},
            "target_entities": {},
            "missing_required_inputs": ["targets", "risk_profile"],
            "next_missing_input": "targets",
        }
    }

    state = service.resolve(
        contract=contract,
        message="64500 en 67000",
        explicit_asset=None,
        conversation_context=context,
    )

    assert state.collected_inputs["base_amount"] == 100
    assert state.collected_inputs["targets"] == [64500.0, 67000.0]
    assert state.missing_required_inputs == ["risk_profile"]


def test_compound_german_strategy_does_not_parse_namespaced_name_as_target_or_risk():
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("create_strategy")
    state = service.resolve(
        contract=contract,
        message=(
            "Erstelle dafuer eine fixed Strategie mit einem Grundbetrag von 100 Euro, "
            "Einstieg 62, Stop-Loss 59, Zielen 65 und 68, Risikoprofil defensiv "
            "und dem Namen Chain Strategy visiblecore-1789631146."
        ),
        explicit_asset=None,
        conversation_context={},
        supplied_inputs={"setup_id": 42},
    )

    assert state.collected_inputs["targets"] == [65.0, 68.0]
    assert state.collected_inputs["risk_profile"] == "conservative"
    assert state.collected_inputs["name"] == "Chain Strategy visiblecore-1789631146"
    assert state.missing_required_inputs == []


def test_update_flow_collects_only_an_explicit_typed_changed_fields_object():
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("update_setup")

    typed = service.resolve(
        contract=contract,
        message='Wijzig setup id 42 met {"timeframe": "4h", "name": "ETH swing"}',
        explicit_asset=None,
        conversation_context={},
    )
    prose = service.resolve(
        contract=contract,
        message="Wijzig setup id 42 zodat hij beter wordt",
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
        message="Wijzig setup id 42 naar timeframe 4H",
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
        message="Maak een bot voor strategy id 52 met de naam Paper Scout",
        explicit_asset=None,
        conversation_context={},
    )

    assert state.collected_inputs == {"strategy_id": 52, "name": "Paper Scout"}


@pytest.mark.parametrize(
    ("message", "expected"),
    (
        ("Maak paper-bot Atlas 0918 voor strategie BTC Swing.", "Atlas 0918"),
        ("Create paper bot Atlas 0918 for strategy BTC Swing.", "Atlas 0918"),
        ("Erstelle Paper-Bot Atlas 0918 für Strategie BTC Swing.", "Atlas 0918"),
    ),
)
def test_create_bot_retains_natural_name_from_complete_initial_prompt(message, expected):
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("create_bot")

    state = service.resolve(
        contract=contract,
        message=message,
        explicit_asset=None,
        conversation_context={},
        supplied_inputs={"strategy_id": 52},
    )

    assert state.collected_inputs["name"] == expected
    assert "name" not in state.missing_required_inputs


@pytest.mark.parametrize(
    "message",
    (
        "Maak een paper-bot met de naam BTC Bot q390 gekoppeld aan strategie BTC Plan q390, "
        "met een budget van 1000 euro en Paper mode. Activeer geen live trading.",
        "Create a paper bot named BTC Bot q390 linked to strategy BTC Plan q390, "
        "with a budget of 1000 euros in paper mode. Do not activate live trading.",
        "Erstelle einen Paper-Bot namens BTC Bot q390 verknuepft mit Strategie BTC Plan q390, "
        "mit einem Budget von 1000 Euro im Paper-Modus. Aktiviere keinen Live-Handel.",
    ),
)
def test_complete_safe_bot_prompt_collects_only_registry_inputs(message):
    service = FinnV2OperationStateService()
    contract = FinnV2OperationRegistry().require_supported("create_bot")

    state = service.resolve(
        contract=contract,
        message=message,
        explicit_asset=None,
        conversation_context={},
        supplied_inputs={"strategy_id": 52},
    )

    assert state.collected_inputs == {
        "strategy_id": 52,
        "name": "BTC Bot q390",
        "budget_total_eur": 1000.0,
    }
    assert state.missing_required_inputs == []


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
    assert state.missing_required_inputs == ["name", "entry", "stop_loss", "targets", "risk_profile"]


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


def test_shared_name_parser_stops_before_asset_and_timeframe_context():
    assert FinnV2OperationStateService._name_input_from_text(
        "Maak een DCA-setup met naam FINN DCA Flow 1759B voor BTC op 4H, wekelijks op maandag."
    ) == "FINN DCA Flow 1759B"


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


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("entry rond 200 euro", 200),
        ("entry around 201 USD", 201),
        ("Einstieg ungefähr 202 Euro", 202),
    ],
)
def test_strategy_entry_accepts_natural_approximation_words(message, expected):
    assert FinnV2OperationStateService._strategy_trade_inputs(message)["entry"] == expected
