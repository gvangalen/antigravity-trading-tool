from __future__ import annotations

from backend.schemas.finn_v2_orchestrator_schema import DomainRequirementPlan, RequestAnalysisResult, ToolPlan
from backend.schemas.finn_v2_tool_schema import ToolSelector


class FinnV2ToolPlanService:
    _DOMAIN_TOOLS = {
        "identity_context": ["read_profile", "read_user_preferences", "read_active_asset"],
        "market_context": [
            "read_active_asset",
            "read_indicator_configuration",
            "read_asset_scores",
            "read_market_snapshot",
            "read_macro_snapshot",
            "read_technical_snapshot",
        ],
        "plan_context": [
            "read_active_asset",
            "read_indicator_configuration",
            "read_active_setup",
            "read_linked_strategy",
        ],
        "automation_context": [
            "read_active_asset",
            "read_active_setup",
            "read_linked_strategy",
            "read_linked_bot",
            "read_bot_status",
        ],
        "portfolio_context": ["read_portfolio"],
        "report_context": ["read_latest_report"],
        "review_context": ["read_review_history"],
    }
    _SCOPE_TOOLS = {
        "profile": ["read_profile", "read_user_preferences", "read_active_asset"],
        "analysis": [
            "read_active_asset",
            "read_indicator_configuration",
            "read_asset_scores",
            "read_market_snapshot",
            "read_macro_snapshot",
            "read_technical_snapshot",
        ],
        "indicators": [
            "read_active_asset",
            "read_indicator_configuration",
            "read_asset_scores",
            "read_market_snapshot",
            "read_macro_snapshot",
            "read_technical_snapshot",
        ],
        "watchlist": ["read_active_asset"],
        "setup": ["read_active_asset", "read_active_setup"],
        "strategy": ["read_active_asset", "read_active_setup", "read_linked_strategy"],
        "bot": ["read_active_asset", "read_active_setup", "read_linked_strategy", "read_linked_bot", "read_bot_status"],
        "daily_report": ["read_active_asset", "read_latest_report"],
        "reflection": ["read_latest_report", "read_review_history"],
        "portfolio": ["read_portfolio"],
    }

    def build(self, *, run_id: str, analysis: RequestAnalysisResult, domain_plan: DomainRequirementPlan) -> ToolPlan:
        active_domains = list(domain_plan.required_domains) + list(domain_plan.optional_domains)
        tool_names: list[str] = []
        for scope in analysis.subject_scopes:
            tool_names.extend(self._SCOPE_TOOLS.get(scope, []))
        if analysis.interaction_mode == "CREATE_PROPOSAL" and "setup" in analysis.subject_scopes:
            tool_names.extend(["read_profile", "read_user_preferences", "read_active_asset"])
        if not tool_names:
            for domain in active_domains:
                tool_names.extend(self._DOMAIN_TOOLS.get(domain, []))

        selector = ToolSelector(
            asset=analysis.explicit_asset,
            setup_id=analysis.explicit_setup_id,
            strategy_id=analysis.explicit_strategy_id,
            bot_id=analysis.explicit_bot_id,
        ).dict(exclude_none=True)

        ordered_tools = []
        for tool_name in tool_names:
            if tool_name not in ordered_tools:
                ordered_tools.append(tool_name)
        if len(ordered_tools) > 15:
            raise ValueError("tool_plan_budget_exceeded")

        return ToolPlan(
            run_id=run_id,
            interaction_mode=analysis.interaction_mode,
            required_domains=list(domain_plan.required_domains),
            optional_domains=list(domain_plan.optional_domains),
            tool_names=ordered_tools,
            tool_inputs={tool_name: dict(selector) for tool_name in ordered_tools},
            max_tool_calls=15,
            read_only=True,
            planning_reasons=[
                f"domains:{','.join(active_domains)}" if active_domains else "domains:none",
                f"scopes:{','.join(analysis.subject_scopes)}" if analysis.subject_scopes else "scopes:none",
                "execution_order:canonical_readonly",
            ],
        )
