from backend.services.finn_v2_request_analysis_service import FinnV2RequestAnalysisService


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


def test_request_analysis_handles_setup_strategy_and_bot_facts():
    setup_result = SERVICE.analyze(message="Welke setup gebruik ik voor BTC?")
    strategy_result = SERVICE.analyze(message="Welke strategie is aan mijn actieve setup gekoppeld?")
    bot_result = SERVICE.analyze(message="Welke bot is aan deze strategie gekoppeld?")
    status_result = SERVICE.analyze(message="Staat mijn gekoppelde bot live?")

    assert setup_result.interaction_mode == "READ"
    assert setup_result.subject_scopes == ["setup"]
    assert strategy_result.subject_scopes == ["setup", "strategy"]
    assert bot_result.subject_scopes == ["strategy", "bot"]
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

    second_turn = SERVICE.analyze(
        message="Noem hem BTC Daily 4H concept.",
        conversation_context={"operation_state": first_turn.request_plan.operation_state},
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
    assert state["missing_required_inputs"] == ["name"]


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


def test_request_analysis_does_not_treat_read_questions_with_confirmed_wording_as_execution():
    strategy_result = SERVICE.analyze(
        message="Welke belangrijkste entryvoorwaarde uit mijn BTC-strategie moet bevestigd zijn voordat mijn plan een entry toestaat?"
    )
    bot_result = SERVICE.analyze(
        message="Waarom heeft mijn gekoppelde BTC-bot nu geen positie geopend? Scheid wat je zeker weet van wat nog niet bevestigd kan worden."
    )

    assert strategy_result.interaction_mode == "EVALUATE"
    assert strategy_result.subject_scopes == ["strategy"]
    assert bot_result.interaction_mode == "READ"
    assert bot_result.subject_scopes == ["bot"]
