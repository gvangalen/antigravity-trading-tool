from backend.services.finn_v2_domain_requirement_service import FinnV2DomainRequirementService
from backend.services.finn_v2_request_analysis_service import FinnV2RequestAnalysisService
from backend.services.finn_v2_tool_plan_service import FinnV2ToolPlanService


def test_tool_plan_uses_canonical_order_and_explicit_selector():
    analysis = FinnV2RequestAnalysisService().analyze(
        message="Bekijk mijn BTC-profiel, indicatoren, setup, strategie en gekoppelde bot."
    )
    domain_plan = FinnV2DomainRequirementService().determine(analysis)

    plan = FinnV2ToolPlanService().build(run_id="run-1", analysis=analysis, domain_plan=domain_plan)

    assert plan.max_tool_calls == 15
    assert plan.tool_names == [
        "read_profile",
        "read_user_preferences",
        "read_active_asset",
        "read_indicator_configuration",
        "read_asset_scores",
        "read_market_snapshot",
        "read_macro_snapshot",
        "read_technical_snapshot",
        "read_active_setup",
        "read_linked_strategy",
        "read_linked_bot",
        "read_bot_status",
    ]
    assert plan.tool_inputs["read_active_asset"] == {"asset": "BTC"}
    assert plan.read_only is True
