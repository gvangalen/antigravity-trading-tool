from backend.services.finn_v2_request_analysis_service import FinnV2RequestAnalysisService


SERVICE = FinnV2RequestAnalysisService()


def test_request_analysis_handles_integral_plan_evaluation():
    result = SERVICE.analyze(
        message=(
            "Bekijk mijn BTC-profiel, indicatoren, setup, strategie en gekoppelde bot. "
            "Wat is volgens jou op dit moment het belangrijkste ontbrekende onderdeel van mijn plan?"
        )
    )

    assert result.interaction_mode == "EVALUATION"
    assert result.subject_scopes == ["profile", "indicators", "setup", "strategy", "bot"]
    assert result.explicit_asset == "BTC"
    assert result.requires_gap_analysis is True


def test_request_analysis_handles_strategy_fit_question():
    result = SERVICE.analyze(message="Past mijn huidige BTC-strategie bij mijn risicoprofiel en tradingstijl?")

    assert result.interaction_mode == "EVALUATION"
    assert result.subject_scopes == ["profile", "strategy"]
    assert result.explicit_asset == "BTC"


def test_request_analysis_handles_indicator_gap_question():
    result = SERVICE.analyze(message="Welke indicatoren heb ik ingesteld en welk belangrijk perspectief ontbreekt nog?")

    assert result.interaction_mode == "EVALUATION"
    assert result.subject_scopes == ["indicators"]
    assert result.requires_gap_analysis is True


def test_request_analysis_handles_setup_strategy_and_bot_facts():
    setup_result = SERVICE.analyze(message="Welke setup gebruik ik voor BTC?")
    strategy_result = SERVICE.analyze(message="Welke strategie is aan mijn actieve setup gekoppeld?")
    bot_result = SERVICE.analyze(message="Welke bot is aan deze strategie gekoppeld?")
    status_result = SERVICE.analyze(message="Staat mijn gekoppelde bot live?")

    assert setup_result.interaction_mode == "FACT"
    assert setup_result.subject_scopes == ["setup"]
    assert strategy_result.subject_scopes == ["setup", "strategy"]
    assert bot_result.subject_scopes == ["strategy", "bot"]
    assert status_result.subject_scopes == ["bot"]


def test_request_analysis_marks_non_financial_question_unavailable():
    result = SERVICE.analyze(message="Wat is het weer morgen in Amsterdam?")

    assert result.interaction_mode == "UNAVAILABLE"
    assert result.subject_scopes == ["unknown"]
    assert "financial_domain_unavailable" in result.unresolved_signals
