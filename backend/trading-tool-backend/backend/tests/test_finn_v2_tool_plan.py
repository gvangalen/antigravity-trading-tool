from backend.services.finn_v2_domain_requirement_service import FinnV2DomainRequirementService
from backend.services.finn_v2_request_analysis_service import FinnV2RequestAnalysisService
from backend.services.finn_v2_tool_plan_service import FinnV2ToolPlanService


def test_tool_plan_uses_canonical_order_and_explicit_selector():
    analysis = FinnV2RequestAnalysisService().analyze(
        message="Bekijk mijn BTC-profiel, indicatoren, setup, strategie en gekoppelde bot. Wat ontbreekt nu het meest?"
    )
    domain_plan = FinnV2DomainRequirementService().determine(analysis)

    plan = FinnV2ToolPlanService().build(run_id="run-1", analysis=analysis, domain_plan=domain_plan)

    assert plan.max_tool_calls == 15
    assert plan.tool_names == [
        "read_profile",
        "read_user_preferences",
        "read_active_asset",
        "read_indicator_configuration",
        "read_active_setup",
        "read_linked_strategy",
        "read_linked_bot",
        "read_bot_status",
    ]
    assert plan.tool_inputs["read_active_asset"] == {"asset": "BTC"}
    assert plan.required_evidence == [
        "profile",
        "preferences",
        "active_asset",
        "indicator_configuration",
        "active_setup",
        "linked_strategy",
        "linked_bot",
        "bot_status",
    ]
    assert plan.read_only is True

def test_tool_plan_keeps_strategy_and_bot_requests_grounded_without_indicator_gate():
    analysis_service = FinnV2RequestAnalysisService()
    domain_service = FinnV2DomainRequirementService()

    strategy_analysis = analysis_service.analyze(message="Welke strategie is aan mijn actieve setup gekoppeld?")
    strategy_plan = FinnV2ToolPlanService().build(
        run_id="run-strategy",
        analysis=strategy_analysis,
        domain_plan=domain_service.determine(strategy_analysis),
    )

    bot_analysis = analysis_service.analyze(message="Welke bot is aan deze strategie gekoppeld en staat die live?")
    bot_plan = FinnV2ToolPlanService().build(
        run_id="run-bot",
        analysis=bot_analysis,
        domain_plan=domain_service.determine(bot_analysis),
    )

    assert strategy_plan.tool_names == ["read_active_asset", "read_active_setup", "read_linked_strategy"]
    assert "read_indicator_configuration" not in strategy_plan.tool_names
    assert bot_plan.tool_names == [
        "read_active_asset",
        "read_active_setup",
        "read_linked_strategy",
        "read_linked_bot",
        "read_bot_status",
    ]
    assert "read_indicator_configuration" not in bot_plan.tool_names


def test_tool_plan_routes_setup_creation_and_watchlist_actions_through_proposal_inputs():
    analysis_service = FinnV2RequestAnalysisService()
    domain_service = FinnV2DomainRequirementService()

    setup_analysis = analysis_service.analyze(message="Maak een setup voor BTC swing trading met daily trend en 4H entry.")
    setup_plan = FinnV2ToolPlanService().build(
        run_id="run-setup-create",
        analysis=setup_analysis,
        domain_plan=domain_service.determine(setup_analysis),
    )

    watchlist_analysis = analysis_service.analyze(
        message="Voeg ETH toe aan mijn watchlist.",
        workspace_hints={"symbol": "BTC"},
    )
    watchlist_plan = FinnV2ToolPlanService().build(
        run_id="run-watchlist-add",
        analysis=watchlist_analysis,
        domain_plan=domain_service.determine(watchlist_analysis),
    )

    assert setup_plan.tool_names == ["read_active_asset"]
    assert setup_plan.required_evidence == ["active_asset"]
    assert watchlist_plan.tool_names == ["read_active_asset", "read_watchlist"]
    assert watchlist_plan.tool_inputs["read_active_asset"] == {"asset": "BTC"}
    assert watchlist_plan.tool_inputs["read_watchlist"] == {"asset": "BTC"}
    assert watchlist_plan.required_evidence == ["active_asset", "watchlist"]


def test_tool_plan_collects_bot_context_for_live_action_proposals():
    analysis = FinnV2RequestAnalysisService().analyze(message="Zet mijn bot live.")
    domain_plan = FinnV2DomainRequirementService().determine(analysis)

    plan = FinnV2ToolPlanService().build(run_id="run-live-bot", analysis=analysis, domain_plan=domain_plan)

    assert analysis.interaction_mode == "ACTION_PROPOSAL"
    assert analysis.primary_subject == "bot"
    assert analysis.action_risk_class == "live_action"
    assert plan.tool_names == [
        "read_active_asset",
        "read_market_snapshot",
        "read_active_setup",
        "read_linked_strategy",
        "read_linked_bot",
        "read_bot_status",
    ]
    assert plan.required_evidence == [
        "active_asset",
        "market_snapshot",
        "active_setup",
        "linked_strategy",
        "linked_bot",
        "bot_status",
    ]
