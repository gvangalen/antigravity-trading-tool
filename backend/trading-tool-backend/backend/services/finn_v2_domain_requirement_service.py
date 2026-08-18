from __future__ import annotations

from backend.schemas.finn_v2_orchestrator_schema import DomainRequirementPlan, RequestAnalysisResult


class FinnV2DomainRequirementService:
    _MAPPING = {
        "profile": {"required": ["identity_context"], "optional": []},
        "analysis": {"required": ["market_context"], "optional": ["identity_context"]},
        "indicators": {"required": ["market_context"], "optional": []},
        "watchlist": {"required": ["identity_context"], "optional": []},
        "setup": {"required": ["plan_context"], "optional": []},
        "strategy": {"required": ["plan_context"], "optional": ["identity_context"]},
        "bot": {"required": ["automation_context", "plan_context"], "optional": []},
        "daily_report": {"required": ["report_context"], "optional": []},
        "reflection": {"required": ["review_context"], "optional": ["report_context", "identity_context"]},
        "portfolio": {"required": ["portfolio_context"], "optional": []},
    }

    def determine(self, analysis: RequestAnalysisResult) -> DomainRequirementPlan:
        required_domains: list[str] = []
        optional_domains: list[str] = []
        reasons: list[str] = []

        if analysis.interaction_mode == "CAPABILITY":
            return DomainRequirementPlan(
                required_domains=[],
                optional_domains=[],
                requirement_reason=["capability_registry_read_only"],
            )
        if analysis.interaction_mode == "UNAVAILABLE":
            return DomainRequirementPlan(
                required_domains=[],
                optional_domains=[],
                requirement_reason=["deterministic_unavailable_without_provider_call"],
            )

        for scope in analysis.subject_scopes:
            mapping = self._MAPPING.get(scope)
            if mapping is None:
                continue
            required_domains.extend(mapping["required"])
            optional_domains.extend(mapping["optional"])
            reasons.append(f"{scope}->{','.join(mapping['required'])}")

        if analysis.interaction_mode in {"CREATE_PROPOSAL", "ACTION_PROPOSAL", "CONFIRMATION", "EXECUTION"}:
            reasons.append("read_only_context_for_change_intent")
        if analysis.interaction_mode == "CREATE_PROPOSAL" and "setup" in analysis.subject_scopes:
            required_domains = ["identity_context"]
            optional_domains = ["plan_context"]
            reasons.append("setup_creation_requires_identity_not_existing_plan")
        if analysis.interaction_mode in {"ACTION_PROPOSAL", "CONFIRMATION", "EXECUTION"} and "watchlist" in analysis.subject_scopes:
            required_domains = ["identity_context"]
            optional_domains = []
            reasons.append("watchlist_action_requires_identity_context")
        if analysis.interaction_mode == "EVALUATE" and "strategy" in analysis.subject_scopes and "profile" in analysis.subject_scopes:
            required_domains.extend(["identity_context", "plan_context"])
            reasons.append("strategy_fit_requires_identity_and_plan")
        return DomainRequirementPlan(
            required_domains=required_domains,
            optional_domains=optional_domains,
            requirement_reason=reasons,
        )
