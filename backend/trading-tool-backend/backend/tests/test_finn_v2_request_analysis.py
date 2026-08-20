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
    assert result.reasoning_required is True


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
