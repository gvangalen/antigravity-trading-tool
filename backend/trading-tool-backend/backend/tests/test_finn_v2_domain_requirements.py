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
    assert plan_a3.required_domains == ["market_context"]


def test_domain_requirements_keep_optional_domains_ordered():
    analysis_service = FinnV2RequestAnalysisService()
    service = FinnV2DomainRequirementService()

    plan = service.determine(analysis_service.analyze(message="Beoordeel mijn reflectie en laatste rapport."))

    assert plan.required_domains == ["report_context", "review_context"]
    assert plan.optional_domains == ["identity_context", "report_context"]
