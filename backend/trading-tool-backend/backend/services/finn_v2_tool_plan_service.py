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
    def build(self, *, run_id: str, analysis: RequestAnalysisResult, domain_plan: DomainRequirementPlan) -> ToolPlan:
        selector = ToolSelector(
            asset=analysis.explicit_asset,
            setup_id=analysis.explicit_setup_id,
            strategy_id=analysis.explicit_strategy_id,
            bot_id=analysis.explicit_bot_id,
        ).dict(exclude_none=True)
        ordered_tools = self._tool_names_for(analysis=analysis, domain_plan=domain_plan)
        if len(ordered_tools) > 15:
            raise ValueError("tool_plan_budget_exceeded")

        return ToolPlan(
            run_id=run_id,
            interaction_mode=analysis.interaction_mode,
            primary_subject=analysis.primary_subject,
            required_domains=list(domain_plan.required_domains),
            optional_domains=list(domain_plan.optional_domains),
            tool_names=ordered_tools,
            tool_inputs={tool_name: dict(selector) for tool_name in ordered_tools},
            required_evidence=self._required_evidence_for(analysis=analysis),
            optional_evidence=self._optional_evidence_for(analysis=analysis),
            entity_selectors=dict(selector),
            clarification_required=bool(analysis.missing_essential_inputs),
            expected_response_contract=analysis.output_contract,
            max_tool_calls=15,
            read_only=True,
            planning_reasons=[
                f"domains:{','.join(list(domain_plan.required_domains) + list(domain_plan.optional_domains))}" if (domain_plan.required_domains or domain_plan.optional_domains) else "domains:none",
                f"mode:{analysis.interaction_mode.casefold()}",
                "execution_order:canonical_readonly",
            ],
        )

    def _tool_names_for(self, *, analysis: RequestAnalysisResult, domain_plan: DomainRequirementPlan) -> list[str]:
        if analysis.interaction_mode == "CAPABILITY":
            return []
        if analysis.interaction_mode == "READ":
            if analysis.primary_subject == "setup":
                return ["read_active_asset", "read_active_setup"]
            if analysis.primary_subject == "strategy":
                return ["read_active_asset", "read_active_setup", "read_linked_strategy"]
            if analysis.primary_subject == "bot":
                return ["read_active_asset", "read_active_setup", "read_linked_strategy", "read_linked_bot", "read_bot_status"]
            if analysis.primary_subject == "watchlist":
                return ["read_active_asset", "read_watchlist"]
        if analysis.interaction_mode == "EVALUATE":
            if analysis.primary_subject == "indicators":
                return ["read_active_asset", "read_indicator_configuration"]
            if analysis.primary_subject == "setup":
                return ["read_active_asset", "read_active_setup"]
            if analysis.primary_subject == "strategy":
                return [
                    "read_profile",
                    "read_user_preferences",
                    "read_active_asset",
                    "read_active_setup",
                    "read_linked_strategy",
                ]
            if analysis.primary_subject == "bot":
                return [
                    "read_profile",
                    "read_user_preferences",
                    "read_active_asset",
                    "read_indicator_configuration",
                    "read_active_setup",
                    "read_linked_strategy",
                    "read_linked_bot",
                    "read_bot_status",
                ]
            return [
                "read_profile",
                "read_user_preferences",
                "read_active_asset",
                "read_indicator_configuration",
                "read_active_setup",
                "read_linked_strategy",
                "read_linked_bot",
                "read_bot_status",
            ]
        if analysis.interaction_mode == "CREATE_PROPOSAL":
            return ["read_profile", "read_user_preferences", "read_active_asset", "read_active_setup"]
        if analysis.interaction_mode == "ACTION_PROPOSAL":
            return ["read_active_asset"]

        active_domains = list(domain_plan.required_domains) + list(domain_plan.optional_domains)
        tool_names: list[str] = []
        for domain in active_domains:
            tool_names.extend(self._DOMAIN_TOOLS.get(domain, []))
        ordered_tools = []
        for tool_name in tool_names:
            if tool_name not in ordered_tools:
                ordered_tools.append(tool_name)
        return ordered_tools

    def _required_evidence_for(self, *, analysis: RequestAnalysisResult) -> list[str]:
        if analysis.interaction_mode == "READ":
            if analysis.primary_subject == "setup":
                return ["active_asset", "active_setup"]
            if analysis.primary_subject == "strategy":
                return ["active_asset", "active_setup", "linked_strategy"]
            if analysis.primary_subject == "bot":
                return ["active_asset", "active_setup", "linked_strategy", "linked_bot", "bot_status"]
        if analysis.interaction_mode == "EVALUATE":
            required: list[str] = []
            scopes = [scope for scope in analysis.subject_scopes if scope != "unknown"]
            if "profile" in scopes:
                required.append("profile")
            if any(scope in scopes for scope in {"indicators", "setup", "strategy", "bot", "watchlist"}):
                required.append("active_asset")
            if "indicators" in scopes:
                required.append("indicator_configuration")
            if "setup" in scopes:
                required.append("active_setup")
            if "strategy" in scopes:
                required.extend(["active_setup", "linked_strategy"])
            if "bot" in scopes:
                required.extend(["active_setup", "linked_strategy", "linked_bot"])
                if not any(scope in scopes for scope in {"profile", "indicators"}):
                    required.append("bot_status")
            if "watchlist" in scopes:
                required.append("watchlist")
            deduped: list[str] = []
            for item in required:
                if item not in deduped:
                    deduped.append(item)
            return deduped
        if analysis.interaction_mode == "CREATE_PROPOSAL":
            return ["active_asset"]
        if analysis.interaction_mode == "ACTION_PROPOSAL":
            if analysis.primary_subject == "watchlist":
                return ["active_asset", "watchlist"]
            return ["active_asset"]
        return []

    def _optional_evidence_for(self, *, analysis: RequestAnalysisResult) -> list[str]:
        if analysis.interaction_mode == "EVALUATE":
            optional = ["asset_scores", "market_snapshot", "macro_snapshot", "technical_snapshot"]
            if "bot" not in analysis.subject_scopes and "bot_status" not in optional:
                optional.append("bot_status")
            return optional
        if analysis.interaction_mode == "CREATE_PROPOSAL":
            return ["active_setup"]
        return []
