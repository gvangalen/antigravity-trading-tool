from typing import Any, Dict, Optional


class FinnActionPolicyService:
    ACTION_POLICIES: Dict[str, Dict[str, Any]] = {
        "setup_review": {
            "action_class": "prepare_only",
            "risk_level": "low",
            "confirmation_required": False,
            "audit_required": False,
            "rollback_mode": "none",
            "minimum_context": "setup_or_asset",
        },
        "strategy_review": {
            "action_class": "prepare_only",
            "risk_level": "low",
            "confirmation_required": False,
            "audit_required": False,
            "rollback_mode": "none",
            "minimum_context": "strategy_or_asset",
        },
        "portfolio_review": {
            "action_class": "prepare_only",
            "risk_level": "low",
            "confirmation_required": False,
            "audit_required": False,
            "rollback_mode": "none",
            "minimum_context": "portfolio",
        },
        "bot_review": {
            "action_class": "prepare_only",
            "risk_level": "medium",
            "confirmation_required": False,
            "audit_required": False,
            "rollback_mode": "none",
            "minimum_context": "bot_or_asset",
        },
        "decision_review": {
            "action_class": "prepare_only",
            "risk_level": "medium",
            "confirmation_required": False,
            "audit_required": False,
            "rollback_mode": "none",
            "minimum_context": "asset",
        },
        "create_setup": {
            "action_class": "confirm_required",
            "risk_level": "medium",
            "confirmation_required": True,
            "audit_required": True,
            "rollback_mode": "delete_draft",
            "minimum_context": "asset",
        },
        "create_strategy": {
            "action_class": "confirm_required",
            "risk_level": "medium",
            "confirmation_required": True,
            "audit_required": True,
            "rollback_mode": "delete_draft",
            "minimum_context": "asset_or_setup",
        },
        "create_bot": {
            "action_class": "confirm_required",
            "risk_level": "medium",
            "confirmation_required": True,
            "audit_required": True,
            "rollback_mode": "delete_config",
            "minimum_context": "strategy_or_setup",
        },
        "activate_setup": {
            "action_class": "confirm_required",
            "risk_level": "medium",
            "confirmation_required": True,
            "audit_required": True,
            "rollback_mode": "deactivate_setup",
            "minimum_context": "setup",
        },
        "activate_bot": {
            "action_class": "confirm_required",
            "risk_level": "high",
            "confirmation_required": True,
            "audit_required": True,
            "rollback_mode": "disable_bot",
            "minimum_context": "bot",
        },
        "save_trade_plan": {
            "action_class": "confirm_required",
            "risk_level": "medium",
            "confirmation_required": True,
            "audit_required": True,
            "rollback_mode": "replace_trade_plan",
            "minimum_context": "decision_or_bot",
        },
        "update_risk_profile": {
            "action_class": "confirm_required",
            "risk_level": "medium",
            "confirmation_required": True,
            "audit_required": True,
            "rollback_mode": "restore_previous_risk_profile",
            "minimum_context": "profile",
        },
        "watchlist_add": {
            "action_class": "confirm_required",
            "risk_level": "low",
            "confirmation_required": True,
            "audit_required": True,
            "rollback_mode": "watchlist_remove",
            "minimum_context": "asset",
        },
        "watchlist_remove": {
            "action_class": "confirm_required",
            "risk_level": "low",
            "confirmation_required": True,
            "audit_required": True,
            "rollback_mode": "watchlist_add",
            "minimum_context": "asset",
        },
        "live_manual_order": {
            "action_class": "never_auto_execute",
            "risk_level": "critical",
            "confirmation_required": True,
            "audit_required": True,
            "rollback_mode": "none",
            "minimum_context": "asset_and_live_preflight",
        },
        "portfolio_rebalance": {
            "action_class": "never_auto_execute",
            "risk_level": "critical",
            "confirmation_required": True,
            "audit_required": True,
            "rollback_mode": "manual_only",
            "minimum_context": "portfolio",
        },
    }

    def resolve_action_policy(
        self,
        action_type: str,
        *,
        subject_type: Optional[str] = None,
        subject_id: Optional[Any] = None,
    ) -> Dict[str, Any]:
        base = dict(self.ACTION_POLICIES.get(action_type) or self.ACTION_POLICIES["decision_review"])
        base["action_type"] = action_type
        base["subject_type"] = subject_type or "unknown"
        base["subject_id"] = subject_id
        return base
