from backend.services.finn_v2_request_analysis_service import FinnV2RequestAnalysisService
from backend.services.finn_v2_request_preprocessor_service import FinnV2RequestPreprocessorService
from backend.services.finn_v2_operation_classification_service import SemanticOperationClassification
from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.domain.finn_v2_setup_input_catalog import FinnV2SetupInputCatalog
from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService


def test_preprocessor_treats_current_symbol_as_asset_entity():
    facts = FinnV2RequestPreprocessorService().preprocess(message="Welk symbool heb ik momenteel geselecteerd?")

    assert "asset" in facts.explicit_entities


SERVICE = FinnV2RequestAnalysisService()


def test_request_analysis_handles_integral_plan_evaluation():
    result = SERVICE.analyze(
        message=(
            "Bekijk mijn BTC-profiel, indicatoren, setup, strategie en gekoppelde bot. "
            "Wat is volgens jou op dit moment het belangrijkste ontbrekende onderdeel van mijn plan?"
        )
    )

    assert result.interaction_mode == "EVALUATE"
    assert result.subject_scopes == ["profile", "indicators", "setup", "strategy", "bot"]
    assert result.explicit_asset == "BTC"
    assert result.requires_gap_analysis is True


def test_request_analysis_handles_strategy_fit_question():
    result = SERVICE.analyze(message="Past mijn huidige BTC-strategie bij mijn risicoprofiel en tradingstijl?")

    assert result.interaction_mode == "EVALUATE"
    assert result.subject_scopes == ["profile", "strategy"]
    assert result.explicit_asset == "BTC"


def test_request_analysis_handles_indicator_gap_question():
    result = SERVICE.analyze(message="Welke indicatoren heb ik ingesteld en welk belangrijk perspectief ontbreekt nog?")

    assert result.interaction_mode == "EVALUATE"
    assert result.subject_scopes == ["indicators"]
    assert result.requires_gap_analysis is True


def test_request_analysis_explicit_bitcoin_overrides_stale_conversation_asset():
    result = SERVICE.analyze(
        message="Met welke signalen analyseer ik Bitcoin momenteel?",
        conversation_context={"resolved_asset": "AAPL"},
    )

    assert result.explicit_asset == "BTC"
    assert result.request_plan.referenced_entities["asset"] == "BTC"


def test_lineage_contract_rehydrates_verified_context_when_selector_omits_reference(monkeypatch):
    service = FinnV2RequestAnalysisService()
    monkeypatch.setattr(
        service.classifier,
        "classify",
        lambda **_kwargs: SemanticOperationClassification(
            operation_id="reformulate_previous_response",
            action="read",
            domain="system",
            discourse="reformulation",
            confidence="high",
            selector_source="structured",
        ),
    )
    result = service.analyze(
        message="Kun je dat beknopter formuleren?",
        conversation_context={
            "last_verified_context": {
                "verified_response_id": "verified-1",
                "run_id": "run-1",
                "response": "Een eerdere geverifieerde conclusie.",
                "conclusion": "Een eerdere conclusie.",
                "evidence_refs": ["E1"],
            },
        },
    )

    assert result.request_plan.operation_id == "reformulate_previous_response"
    assert result.request_plan.conversation_reference == "verified-1"
    assert result.request_plan.operation_state["previous_verified_run_id"] == "run-1"


def test_request_analysis_keeps_context_target_and_reference_assets_distinct():
    result = SERVICE.analyze(
        message="Voeg Cardano toe aan mijn watchlist.",
        workspace_hints={"symbol": "BTC"},
        conversation_context={"resolved_asset": "AAPL"},
    )

    assert result.request_plan.operation_id == "watchlist_add"
    assert result.request_plan.context_asset == "BTC"
    assert result.request_plan.target_asset == "ADA"
    assert result.request_plan.referenced_asset == "ADA"
    assert result.request_plan.operation_state["collected_inputs"]["asset"] == "ADA"


def test_preprocessor_canonicalizes_natural_asset_names_before_contract_selection():
    facts = FinnV2RequestPreprocessorService().preprocess(
        message="Voeg Avalanche toe aan mijn watchlist."
    )

    assert facts.referenced_asset == "AVAX"
    assert facts.explicit_target_asset == "AVAX"


def test_request_analysis_keeps_capability_discourse_when_it_mentions_plan_features():
    result = SERVICE.analyze(message="Hoi FINN, wat kun je voor mijn plan, setup en bot doen?")

    assert result.request_plan.operation_id == "capability"
    assert result.interaction_mode == "CAPABILITY"
    assert result.request_plan.required_information_scopes == ["capability"]


def test_request_analysis_handles_setup_strategy_and_bot_facts(monkeypatch):
    service = FinnV2RequestAnalysisService()
    selected = {
        "Welke setup gebruik ik voor BTC?": "read_active_setup",
        "Welke strategie is aan mijn actieve setup gekoppeld?": "read_linked_strategy",
        "Welke bot is aan deze strategie gekoppeld?": "read_linked_bot",
        "Staat mijn gekoppelde bot live?": "read_bot_status",
    }
    monkeypatch.setattr(
        service.classifier,
        "classify",
        lambda *, message, **_kwargs: SemanticOperationClassification(
            operation_id=selected[message],
            action="read",
            domain=FinnV2OperationRegistry().require_supported(selected[message]).domain,
            discourse="information_request",
            confidence="high",
            selector_source="structured",
        ),
    )
    context = {"last_verified_context": {"verified_response_id": "verified-plan", "evidence_refs": ["E1"]}}
    setup_result = service.analyze(message="Welke setup gebruik ik voor BTC?", conversation_context=context)
    strategy_result = service.analyze(message="Welke strategie is aan mijn actieve setup gekoppeld?", conversation_context=context)
    bot_result = service.analyze(message="Welke bot is aan deze strategie gekoppeld?", conversation_context=context)
    status_result = service.analyze(message="Staat mijn gekoppelde bot live?", conversation_context=context)

    assert setup_result.interaction_mode == "READ"
    assert setup_result.subject_scopes == ["setup"]
    assert strategy_result.subject_scopes == ["setup", "strategy"]
    assert bot_result.subject_scopes == ["setup", "strategy", "bot"]
    assert status_result.subject_scopes == ["bot"]

def test_request_analysis_routes_setup_create_and_watchlist_action_to_proposals():
    setup_result = SERVICE.analyze(message="Maak een setup voor BTC swing trading met daily trend en 4H entry.")
    watchlist_result = SERVICE.analyze(message="Voeg ETH toe aan mijn watchlist.")

    assert setup_result.interaction_mode == "CREATE_PROPOSAL"
    assert setup_result.primary_subject == "setup"
    assert watchlist_result.interaction_mode == "ACTION_PROPOSAL"
    assert watchlist_result.primary_subject == "watchlist"


def test_request_analysis_keeps_natural_integrated_plan_paraphrases_in_evaluate_mode():
    for message in [
        "Bekijk het hele plaatje en zeg waar het wringt.",
        "Waar zit momenteel het zwakste punt in mijn hele plan?",
        "Welke voorwaarde ontbreekt voordat ik dit plan kan vertrouwen?",
    ]:
        result = SERVICE.analyze(message=message)

        assert result.interaction_mode == "EVALUATE"
        assert result.subject_scopes == ["profile", "indicators", "setup", "strategy", "bot"]


def test_request_analysis_routes_complete_asset_plan_to_full_plan_contract():
    result = SERVICE.analyze(message="Beoordeel mijn volledige BTC-plan en benoem het belangrijkste zwakke punt.")

    assert result.request_plan.operation_id == "evaluate_plan"
    assert result.interaction_mode == "EVALUATE"
    assert result.request_plan.required_information_scopes == [
        "profile", "preferences", "active_asset", "indicator_configuration",
        "active_setup", "linked_strategy", "linked_bot", "bot_status",
    ]


def test_request_analysis_recognizes_natural_plan_and_write_grammar():
    plan = SERVICE.analyze(message="Waar wringt mijn huidige aanpak financieel gezien het meest?")
    setup = SERVICE.analyze(message="Werk een nieuwe positie-opzet voor SOL uit.")
    remove = SERVICE.analyze(message="Ik wil LINK niet langer op mijn gevolgde-marktenlijst.")

    assert plan.request_plan.operation_id == "evaluate_plan"
    assert setup.request_plan.operation_id == "create_setup"
    assert remove.request_plan.operation_id == "watchlist_remove"


def test_request_analysis_treats_safe_setup_concepts_as_create_proposals():
    for message in [
        "Maak een veilig concept voor een betere setup bij mijn huidige plan; nog niet opslaan.",
        "Stel een passende nieuwe setup voor mijn BTC-plan voor, maar voer niets uit.",
        "Welke setup zou jij als voorstel toevoegen aan mijn huidige BTC-aanpak? Alleen voorbereiden.",
    ]:
        result = SERVICE.analyze(message=message)

        assert result.interaction_mode == "CREATE_PROPOSAL"
        assert result.primary_subject == "setup"


def test_request_analysis_routes_live_bot_activation_to_action_proposal():
    result = SERVICE.analyze(message="Activeer deze bot live.")

    assert result.interaction_mode == "ACTION_PROPOSAL"
    assert result.primary_subject == "bot"
    assert result.action_risk_class == "live_action"
def test_request_analysis_marks_non_financial_question_unavailable():
    result = SERVICE.analyze(message="Wat is het weer morgen in Amsterdam?")

    assert result.interaction_mode == "UNAVAILABLE"
    assert result.subject_scopes == ["unknown"]
    assert "financial_domain_unavailable" in result.unresolved_signals


def test_request_analysis_routes_dutch_capability_question_to_capability_mode():
    result = SERVICE.analyze(message="Hoi FINN, wat kun je voor mij doen?")

    assert result.interaction_mode == "CAPABILITY"
    assert result.subject_scopes == ["capability"]
    assert result.reasoning_required is False


def test_request_analysis_preserves_financial_concept_in_request_plan():
    result = SERVICE.analyze(message="Wat betekent RSI?")

    assert result.request_plan.operation_id == "explain_financial_concept"
    assert result.interaction_mode == "READ"
    assert result.reasoning_required is False
    assert result.request_plan.referenced_entities["concept"] == "RSI"


def test_financial_concept_is_a_resolved_contract_input_not_a_guided_slot():
    result = FinnV2RequestAnalysisService().analyze(message="Wat betekent RSI?")

    assert result.request_plan.operation_id == "explain_financial_concept"
    assert result.request_plan.skip_canonical_context_graph is True
    assert result.missing_essential_inputs == []


def test_request_analysis_routes_english_capability_question_to_capability_mode():
    result = SERVICE.analyze(message="What can FINN do for me?")

    assert result.interaction_mode == "CAPABILITY"
    assert result.subject_scopes == ["capability"]


def test_request_analysis_keeps_incomplete_financial_question_unavailable():
    result = SERVICE.analyze(message="Wat is nu de beste trade voor mij zonder verdere context?")

    assert result.interaction_mode == "UNAVAILABLE"
    assert result.subject_scopes == ["unknown"]
    assert "financial_domain_unavailable" in result.unresolved_signals
    assert "insufficient_trade_context" in result.unresolved_signals


def test_request_analysis_routes_setup_creation_and_watchlist_actions_to_typed_modes():
    setup_result = SERVICE.analyze(message="Maak een setup voor BTC swing trading met daily trend en 4H entry.")
    watchlist_result = SERVICE.analyze(message="Voeg ETH toe aan mijn watchlist.")

    assert setup_result.interaction_mode == "CREATE_PROPOSAL"
    assert setup_result.subject_scopes == ["setup"]
    assert setup_result.explicit_asset == "BTC"
    assert watchlist_result.interaction_mode == "ACTION_PROPOSAL"
    assert watchlist_result.subject_scopes == ["watchlist"]
    assert watchlist_result.explicit_asset == "ETH"


def test_guided_setup_state_collects_verified_inputs_without_premature_proposal():
    first_turn = SERVICE.analyze(
        message="Maak een setup voor BTC swing trading met daily trend en 4H entry."
    )

    assert first_turn.request_plan.operation_id == "create_setup"
    assert first_turn.request_plan.operation_state["collected_inputs"] == {
        "symbol": "BTC",
        "setup_type": "trade",
        "timeframe": "4H",
        "market_condition": "trend_defined",
    }
    assert first_turn.request_plan.operation_state["missing_required_inputs"] == ["name"]
    assert first_turn.request_plan.clarification_required is True

    second_turn = SERVICE.analyze(
        message="De naam is BTC swing daily-4H.",
        conversation_context={"operation_state": first_turn.request_plan.operation_state},
    )

    assert second_turn.interaction_mode == "CREATE_PROPOSAL"
    assert second_turn.request_plan.operation_id == "create_setup"
    assert second_turn.request_plan.operation_state["missing_required_inputs"] == []
    assert second_turn.request_plan.operation_state["collected_inputs"]["name"] == "BTC swing daily-4H"


def test_guided_setup_state_accepts_natural_name_follow_up():
    first_turn = SERVICE.analyze(message="Help me een nieuwe BTC-setup als concept te maken.")

    type_turn = SERVICE.analyze(
        message="Gebruik een swing setup.",
        conversation_context={"operation_state": first_turn.request_plan.operation_state},
    )
    timeframe_turn = SERVICE.analyze(
        message="Gebruik de 4H-timeframe.",
        conversation_context={"operation_state": type_turn.request_plan.operation_state},
    )
    second_turn = SERVICE.analyze(
        message="Noem hem BTC Daily 4H concept.",
        conversation_context={"operation_state": timeframe_turn.request_plan.operation_state},
    )

    state = second_turn.request_plan.operation_state
    assert second_turn.request_plan.operation_id == "create_setup"
    assert state["missing_required_inputs"] == []
    assert state["collected_inputs"]["name"] == "BTC Daily 4H concept"


def test_explicit_watchlist_operation_does_not_resume_pending_setup_state():
    setup_turn = SERVICE.analyze(message="Help me een nieuwe BTC-setup als concept te maken.")

    watchlist_turn = SERVICE.analyze(
        message="Voeg XRP toe aan mijn watchlist.",
        conversation_context={"operation_state": setup_turn.request_plan.operation_state},
    )

    assert watchlist_turn.request_plan.operation_id == "watchlist_add"
    assert watchlist_turn.interaction_mode == "ACTION_PROPOSAL"
    assert watchlist_turn.request_plan.operation_state["collected_inputs"]["asset"] == "XRP"


def test_watchlist_target_never_inherits_the_workspace_asset():
    analysis = SERVICE.analyze(
        message="Voeg toe aan mijn watchlist.",
        workspace_hints={"symbol": "BTC"},
    )

    assert analysis.request_plan.operation_id == "watchlist_add"
    assert analysis.request_plan.context_asset == "BTC"
    assert analysis.request_plan.target_asset is None
    assert analysis.request_plan.operation_state["missing_required_inputs"] == ["asset"]


def test_guided_watchlist_target_asset_is_typed_and_never_reuses_workspace_asset():
    analysis = SERVICE.analyze(
        message="De bedoelde targetasset is ADA.",
        workspace_hints={"symbol": "BTC"},
        conversation_context={
            "active_guided_operation": {
                "operation_id": "watchlist_add",
                "contract_version": "2026-08-23.operation-contracts.v1",
                "collected_inputs": {},
                "resolved_entities": {},
                "missing_required_inputs": ["asset"],
            }
        },
    )

    state = analysis.request_plan.operation_state
    assert analysis.request_plan.operation_id == "watchlist_add"
    assert analysis.request_plan.context_asset == "BTC"
    assert analysis.request_plan.target_asset == "ADA"
    assert state["collected_inputs"]["asset"] == "ADA"
    assert state["target_entities"] == {"asset": "ADA"}
    assert state["missing_required_inputs"] == []


def test_capability_question_with_plan_terms_keeps_its_own_contract_over_conversation_state():
    analysis = SERVICE.analyze(
        message="Leg kort uit welke analyses en acties je ondersteunt voor mijn plan.",
        conversation_context={
            "last_verified_context": {"verified_response_id": "verified-plan"},
            "active_guided_operation": {
                "operation_id": "create_setup",
                "contract_version": "2026-08-23.operation-contracts.v1",
                "missing_required_inputs": ["name"],
            },
        },
    )

    assert analysis.request_plan.operation_id == "capability"
    assert analysis.interaction_mode == "CAPABILITY"
    assert analysis.reasoning_required is False


def test_technical_configuration_request_uses_indicator_contract_and_scopes():
    analysis = SERVICE.analyze(
        message="Vat mijn technische configuratie voor Bitcoin samen.",
        conversation_context={"resolved_asset": "AAPL"},
    )

    assert analysis.request_plan.operation_id == "read_indicator_configuration"
    assert analysis.interaction_mode == "READ"
    assert analysis.explicit_asset == "BTC"
    assert analysis.request_plan.required_information_scopes == ["active_asset", "indicator_configuration"]


def test_active_guided_operation_has_priority_over_legacy_state():
    analysis = SERVICE.analyze(
        message="Noem hem BTC Daily 4H concept.",
        conversation_context={
            "active_guided_operation": {
                "operation_id": "create_setup",
                "contract_version": "2026-08-23.operation-contracts.v1",
                "collected_inputs": {"symbol": "BTC", "setup_type": "trade"},
                "resolved_entities": {},
                "missing_required_inputs": ["name"],
            },
            "operation_state": {"operation_id": "watchlist_add", "missing_required_inputs": ["asset"]},
        },
    )

    assert analysis.request_plan.operation_id == "create_setup"
    assert analysis.request_plan.operation_state["collected_inputs"]["name"] == "BTC Daily 4H concept"


def test_canonical_conversation_does_not_resume_a_legacy_guided_state():
    analysis = SERVICE.analyze(
        message="Welke indicatoren staan voor BTC ingesteld?",
        conversation_context={
            "conversation_state_version": "finn_v2.conversation-contracts.v1",
            "operation_state": {
                "operation_id": "create_setup",
                "contract_version": "2026-08-23.operation-contracts.v1",
                "missing_required_inputs": ["name"],
            },
        },
    )

    assert analysis.request_plan.operation_id == "read_indicator_configuration"


def test_guided_setup_cancel_closes_typed_state_without_selecting_a_write_operation():
    first_turn = SERVICE.analyze(message="Help me een nieuwe BTC-setup als concept te maken.")

    cancelled = SERVICE.analyze(
        message="Annuleer dit voorstel.",
        conversation_context={"active_guided_operation": first_turn.request_plan.operation_state},
    )

    assert cancelled.request_plan.operation_id == "clarify_request"
    assert cancelled.interaction_mode == "CLARIFICATION"
    assert cancelled.request_plan.operation_state["operation_id"] == "create_setup"
    assert cancelled.request_plan.operation_state["status"] == "cancelled"
    assert cancelled.request_plan.operation_state["missing_required_inputs"] == []


def test_guided_operation_state_retains_verified_context_without_reasking_fields():
    analysis = SERVICE.analyze(
        message="Maak een setup voor BTC swing trading.",
        conversation_context={
            "resolved_asset": "BTC",
            "resolved_setup_id": 309,
            "resolved_strategy_id": 325,
            "resolved_bot_id": 186,
            "last_verified_conclusion": "De bestaande BTC-setup gebruikt 4H voor entries.",
            "last_evidence_refs": ["artifact-asset", "artifact-setup"],
        },
    )

    state = analysis.request_plan.operation_state
    assert state["resolved_entities"] == {"asset": "BTC", "setup_id": 309, "strategy_id": 325, "bot_id": 186}
    assert state["previous_verified_conclusion"] == "De bestaande BTC-setup gebruikt 4H voor entries."
    assert state["previous_evidence_refs"] == ["artifact-asset", "artifact-setup"]
    assert state["missing_required_inputs"] == ["timeframe", "name"]


def test_guided_setup_collects_type_timeframe_and_name_in_one_persisted_contract():
    first = SERVICE.analyze(message="Maak een BTC-setup.")
    assert first.request_plan.operation_state["missing_required_inputs"] == [
        "setup_type", "timeframe", "name"
    ]
    assert first.request_plan.operation_state["next_missing_input"] == "setup_type"

    second = SERVICE.analyze(
        message="Gebruik een swing setup.",
        conversation_context={"active_guided_operation": first.request_plan.operation_state},
    )
    assert second.request_plan.operation_id == "create_setup"
    assert second.request_plan.operation_state["missing_required_inputs"] == ["timeframe", "name"]

    third = SERVICE.analyze(
        message="Gebruik de 4H-timeframe.",
        conversation_context={"active_guided_operation": second.request_plan.operation_state},
    )
    assert third.request_plan.operation_state["missing_required_inputs"] == ["name"]

    final = SERVICE.analyze(
        message="Noem hem BTC Contract QA.",
        conversation_context={"active_guided_operation": third.request_plan.operation_state},
    )
    assert final.request_plan.operation_state["missing_required_inputs"] == []
    assert final.request_plan.operation_state["collected_inputs"] == {
        "symbol": "BTC",
        "setup_type": "trade",
        "timeframe": "4H",
        "name": "BTC Contract QA",
    }


def test_complete_natural_setup_sentence_resolves_all_typed_inputs():
    result = SERVICE.analyze(
        message="Werk voor DOT een breakout-opzet uit op 2H en noem hem Polkadot Uitbraak."
    )

    assert result.request_plan.operation_id == "create_setup"
    assert result.request_plan.target_asset == "DOT"
    assert result.request_plan.operation_state["missing_required_inputs"] == []
    assert result.request_plan.operation_state["collected_inputs"] == {
        "symbol": "DOT",
        "setup_type": "trade",
        "timeframe": "2H",
        "name": "Polkadot Uitbraak",
    }


def test_setup_catalog_canonicalizes_natural_slots_without_losing_user_display_name():
    result = SERVICE.analyze(
        message="Zet voor Solana een position setup klaar op dagbasis met de naam SOL Kompas."
    )

    assert result.request_plan.operation_id == "create_setup"
    assert result.request_plan.target_asset == "SOL"
    assert result.request_plan.operation_state["missing_required_inputs"] == []
    assert result.request_plan.operation_state["collected_inputs"] == {
        "symbol": "SOL", "setup_type": "position", "timeframe": "1D", "name": "SOL Kompas",
    }


def test_setup_catalog_supports_dutch_english_and_german_timeframe_variants():
    cases = (
        ("Maak een swing setup voor SOL op 4 uur met de naam SOL Swing.", "trade", "4H"),
        ("Create an intraday setup for SOL on an hourly basis named SOL Hourly.", "trade", "1H"),
        ("Erstelle ein Position Setup für SOL auf Tagesbasis namens SOL Tagesplan.", "position", "1D"),
    )
    contract = FinnV2OperationRegistry().require_supported("create_setup")
    state_service = FinnV2OperationStateService()
    for message, setup_type, timeframe in cases:
        values = state_service.explicit_inputs(contract=contract, message=message, explicit_asset="SOL")
        assert values["setup_type"] == setup_type
        assert values["timeframe"] == timeframe


def test_setup_state_canonicalizes_supplied_values_before_missing_checks_without_overwrite():
    contract = FinnV2OperationRegistry().require_supported("create_setup")
    state = FinnV2OperationStateService().resolve(
        contract=contract,
        message="Maak een setup voor SOL.", explicit_asset="SOL", conversation_context={},
        supplied_inputs={"setup_type": "Position", "timeframe": "dagbasis", "name": "SOL Kompas"},
        derived_inputs={"setup_type": "trade", "timeframe": None, "name": "sol kompas", "symbol": "BTC"},
    )

    assert state.collected_inputs == {
        "symbol": "SOL", "setup_type": "position", "timeframe": "1D", "name": "SOL Kompas",
    }
    assert state.missing_required_inputs == []


def test_setup_state_leaves_actually_missing_type_and_timeframe_missing():
    contract = FinnV2OperationRegistry().require_supported("create_setup")
    state = FinnV2OperationStateService().resolve(
        contract=contract, message="Maak een setup voor SOL met de naam SOL Kompas.",
        explicit_asset="SOL", conversation_context={}, supplied_inputs={"name": "SOL Kompas"},
    )

    assert state.missing_required_inputs == ["setup_type", "timeframe"]


def test_natural_dutch_position_setup_is_a_supplied_type_not_a_missing_slot():
    result = SERVICE.analyze(message="Werk een nieuwe positie-opzet voor SOL uit.")

    assert result.request_plan.operation_id == "create_setup"
    assert result.request_plan.operation_state["collected_inputs"] == {
        "symbol": "SOL", "setup_type": "position",
    }
    assert result.request_plan.operation_state["missing_required_inputs"] == ["timeframe", "name"]


def test_compound_setup_type_is_canonicalized_before_missing_input_reconciliation():
    result = SERVICE.analyze(message="Bereid een nieuwe swingopzet voor XRP voor.")

    assert result.request_plan.operation_id == "create_setup"
    assert result.request_plan.operation_state["collected_inputs"] == {
        "symbol": "XRP", "setup_type": "trade",
    }
    assert result.request_plan.operation_state["missing_required_inputs"] == ["timeframe", "name"]


def test_timeframe_catalog_canonicalizes_compositional_dutch_english_and_german_forms():
    cases = {
        "uurgrafiek": "1H", "four-hour chart": "4H", "vieruursgrafiek": "4H",
        "4-Stunden-Chart": "4H", "twaalfuursgrafiek": "12H", "one-day chart": "1D",
        "weekgrafiek": "1W",
    }
    for value, expected in cases.items():
        assert FinnV2SetupInputCatalog.timeframe_from_text(value) == expected
        assert FinnV2SetupInputCatalog.canonical_timeframe(value) == expected
    assert FinnV2SetupInputCatalog.timeframe_from_text("vier uur en daggrafiek") is None


def test_complete_avax_compound_timeframe_setup_preserves_supplied_values():
    result = SERVICE.analyze(
        message="Bereid voor Avalanche een swingopzet voor op de vieruursgrafiek en noem hem AVAX Rustige Instap."
    )
    assert result.request_plan.operation_state["collected_inputs"] == {
        "symbol": "AVAX", "setup_type": "trade", "timeframe": "4H", "name": "AVAX Rustige Instap",
    }
    assert result.request_plan.operation_state["missing_required_inputs"] == []


def test_contextual_bot_implication_keeps_verified_lineage_payload():
    result = SERVICE.analyze(
        message="Wat betekent dat concreet voor mijn bot?",
        conversation_context={
            "conversation_state_version": "finn_v2.conversation-contracts.v1",
            "last_verified_context": {
                "verified_response_id": "verified-plan",
                "run_id": "run-plan",
                "operation_id": "evaluate_plan",
                "conclusion": "De entryvoorwaarde is onvoldoende toetsbaar.",
                "response": "Je plan mist een toetsbare entryvoorwaarde.",
                "evidence_refs": ["E1", "E2"],
                "resolved_entities": {"asset": "BTC", "bot_id": 170},
            },
        },
    )

    assert result.request_plan.operation_id == "evaluate_bot"
    assert result.interaction_mode == "EVALUATE"
    assert result.request_plan.conversation_reference == "verified-plan"
    assert result.request_plan.operation_state["previous_verified_run_id"] == "run-plan"
    assert result.request_plan.operation_state["previous_verified_conclusion"] == (
        "De entryvoorwaarde is onvoldoende toetsbaar."
    )


def test_canonical_guided_state_reads_only_verified_conversation_lineage():
    analysis = SERVICE.analyze(
        message="Maak een setup voor BTC swing trading.",
        conversation_context={
            "conversation_state_version": "finn_v2.conversation-contracts.v1",
            "resolved_asset": "AAPL",
            "last_verified_conclusion": "legacy conclusion",
            "last_verified_context": {
                "verified_response_id": "verified-btc",
                "conclusion": "BTC needs an entry rule.",
                "evidence_refs": ["artifact-btc"],
                "resolved_entities": {"asset": "BTC", "setup_id": 309},
            },
        },
    )

    state = analysis.request_plan.operation_state
    assert state["resolved_entities"] == {"asset": "BTC", "setup_id": 309}
    assert state["previous_verified_response_id"] == "verified-btc"
    assert state["previous_verified_conclusion"] == "BTC needs an entry rule."
    assert state["previous_evidence_refs"] == ["artifact-btc"]


def test_follow_up_references_the_previous_verified_response_not_a_text_label():
    analysis = SERVICE.analyze(
        message="Onderbouw die conclusie.",
        conversation_context={
            "last_verified_context": {
                "verified_response_id": "verified-btc-plan-1",
                "operation_id": "evaluate_plan",
                "mode": "EVALUATE",
                "conclusion": "The BTC plan needs a documented decision rule.",
                "evidence_refs": ["artifact-plan-1"],
                "resolved_entities": {"asset": "BTC", "bot_id": 186},
            },
        },
    )

    assert analysis.request_plan.operation_id == "explain_previous_evidence"
    assert analysis.request_plan.conversation_reference == "verified-btc-plan-1"


def test_degraded_evidence_lineage_keeps_provenance_without_reviving_a_conclusion(monkeypatch):
    service = FinnV2RequestAnalysisService()
    monkeypatch.setattr(
        service.classifier,
        "classify",
        lambda **_kwargs: SemanticOperationClassification(
            operation_id="explain_previous_evidence",
            action="read",
            domain="lineage",
            discourse="evidence_follow_up",
            confidence="high",
            selector_source="structured",
        ),
    )

    analysis = service.analyze(
        message="Waar baseer je dat op?",
        conversation_context={
            "last_degraded_context": {
                "operation_id": "evaluate_plan",
                "run_id": "run-degraded-1",
                "evidence_refs": ["E1"],
                "resolved_entities": {"asset": "BTC", "setup_id": 295},
            },
        },
    )

    state = analysis.request_plan.operation_state
    assert analysis.request_plan.operation_id == "explain_previous_evidence"
    assert analysis.request_plan.conversation_reference == "run-degraded-1"
    assert state["previous_evidence_refs"] == ["E1"]
    assert "previous_verified_conclusion" not in state
    assert "previous_verified_response" not in state


def test_concrete_bot_follow_up_can_use_degraded_scope_without_promoting_conclusion(monkeypatch):
    service = FinnV2RequestAnalysisService()
    monkeypatch.setattr(
        service.classifier, "classify", lambda **_kwargs: SemanticOperationClassification(
            operation_id="evaluate_bot", action="evaluate", domain="bot", discourse="contextual_follow_up",
            confidence="high", selector_source="structured",
        ),
    )

    analysis = service.analyze(
        message="Wat betekent dat concreet voor mijn bot?",
        conversation_context={"last_degraded_context": {
            "operation_id": "evaluate_plan", "run_id": "run-degraded", "evidence_refs": ["E1"],
            "evidence_scopes": ["linked_bot", "bot_status"],
            "released_response_sections": [{"kind": "verification_limitation", "text": "Niet geverifieerd."}],
            "resolved_entities": {"asset": "BTC", "bot_id": 170},
        }},
    )

    assert analysis.request_plan.operation_id == "evaluate_bot"
    assert analysis.request_plan.conversation_reference == "run-degraded"
    assert analysis.request_plan.operation_state["resolved_entities"] == {"asset": "BTC", "bot_id": 170}
    assert "previous_verified_conclusion" not in analysis.request_plan.operation_state


def test_request_analysis_does_not_treat_read_questions_with_confirmed_wording_as_execution():
    strategy_result = SERVICE.analyze(
        message="Welke belangrijkste entryvoorwaarde uit mijn BTC-strategie moet bevestigd zijn voordat mijn plan een entry toestaat?"
    )
    bot_result = SERVICE.analyze(
        message="Waarom heeft mijn gekoppelde BTC-bot nu geen positie geopend? Scheid wat je zeker weet van wat nog niet bevestigd kan worden."
    )

    assert strategy_result.interaction_mode == "EVALUATE"
    assert strategy_result.subject_scopes == ["setup", "strategy"]
    assert bot_result.interaction_mode == "READ"
    assert bot_result.subject_scopes == ["bot"]
