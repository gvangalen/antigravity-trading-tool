from backend.services.finn_v2_domain_requirement_service import FinnV2DomainRequirementService
from backend.services.finn_v2_request_analysis_service import FinnV2RequestAnalysisService


def test_domain_requirements_match_block4_regression_cases():
    analysis_service = FinnV2RequestAnalysisService()
    service = FinnV2DomainRequirementService()

    plan_a1 = service.determine(
        analysis_service.analyze(
            message="Bekijk mijn BTC-profiel, indicatoren, setup, strategie en gekoppelde bot. Wat ontbreekt er in mijn plan?"
        )
    )
    plan_a2 = service.determine(
        analysis_service.analyze(message="Past mijn huidige BTC-strategie bij mijn risicoprofiel en tradingstijl?")
    )
    plan_a3 = service.determine(
        analysis_service.analyze(message="Welke indicatoren heb ik ingesteld en welk belangrijk perspectief ontbreekt nog?")
    )

    assert plan_a1.required_domains == [
        "identity_context",
        "market_context",
        "plan_context",
        "automation_context",
    ]
    assert plan_a2.required_domains == ["identity_context", "plan_context"]
    assert plan_a3.required_domains == ["identity_context", "market_context"]


def test_domain_requirements_do_not_execute_unimplemented_report_review_operations():
    analysis_service = FinnV2RequestAnalysisService()
    service = FinnV2DomainRequirementService()

    plan = service.determine(analysis_service.analyze(message="Beoordeel mijn reflectie en laatste rapport."))

    assert plan.required_domains == []
    assert plan.optional_domains == []

def test_domain_requirements_narrow_create_setup_and_watchlist_actions():
    analysis_service = FinnV2RequestAnalysisService()
    service = FinnV2DomainRequirementService()

    setup_plan = service.determine(
        analysis_service.analyze(message="Maak een setup voor BTC swing trading met daily trend en 4H entry.")
    )
    watchlist_plan = service.determine(
        analysis_service.analyze(message="Voeg ETH toe aan mijn watchlist.")
    )

    assert setup_plan.required_domains == ["identity_context"]
    assert setup_plan.optional_domains == ["market_context", "plan_context"]
    assert "contract:create_setup:active_asset->identity_context" in setup_plan.requirement_reason
    assert watchlist_plan.required_domains == ["identity_context"]
    assert watchlist_plan.optional_domains == []
    assert "contract:watchlist_add:active_asset->identity_context" in watchlist_plan.requirement_reason


def test_domain_requirements_expand_live_bot_actions_to_full_context():
    analysis_service = FinnV2RequestAnalysisService()
    service = FinnV2DomainRequirementService()

    plan = service.determine(analysis_service.analyze(message="Zet mijn bot live."))

    assert plan.required_domains == [
        "identity_context",
        "market_context",
        "plan_context",
        "automation_context",
    ]
