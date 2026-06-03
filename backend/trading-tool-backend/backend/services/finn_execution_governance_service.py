from typing import Any, Dict, List, Optional


class FinnExecutionGovernanceService:
    def evaluate(
        self,
        *,
        action_policy: Dict[str, Any],
        context_sufficiency: str,
        plan_alignment: str,
        portfolio_conflict_level: str,
        explicit_execution_sensitive: bool,
        decision_status: Optional[str] = None,
        portfolio_blockers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        portfolio_blockers = [item for item in (portfolio_blockers or []) if item]

        warnings: List[str] = []
        blocking_reason: Optional[str] = None
        execution_allowed = True
        governance_status = "recommend"

        if context_sufficiency in {"insufficient", "missing"}:
            execution_allowed = False
            governance_status = "block"
            blocking_reason = "Ik mis nog te veel context om deze actie verantwoord te laten doorgaan."
        elif portfolio_conflict_level == "high":
            execution_allowed = False
            governance_status = "block"
            blocking_reason = portfolio_blockers[0] if portfolio_blockers else "Deze actie botst nu met je portfolio-risico."
        elif decision_status == "block":
            execution_allowed = False
            governance_status = "block"
            blocking_reason = "De onderliggende review blokkeert deze actie op risico of context."
        else:
            if plan_alignment == "warn":
                warnings.append("Deze actie schuurt tegen je plan of disciplinegrenzen aan.")
            elif plan_alignment == "conflict":
                warnings.append("Deze actie wijkt af van je plan en vraagt extra frictie.")

            if portfolio_conflict_level == "medium":
                warnings.append("Er is portfolio-frictie; ik zou dit alleen met extra aandacht doen.")

            action_class = action_policy.get("action_class")
            if action_class == "prepare_only":
                execution_allowed = False
                governance_status = "explain"
            elif action_class == "confirm_required":
                governance_status = "confirm" if explicit_execution_sensitive or action_policy.get("confirmation_required") else "recommend"
            elif action_class == "never_auto_execute":
                governance_status = "confirm" if context_sufficiency == "sufficient" else "block"
                execution_allowed = context_sufficiency == "sufficient"
                warnings.append("Deze actie mag nooit autonoom uitgevoerd worden en blijft achter expliciete bevestiging.")

        recommended_next_step = "Laat FINN deze actie eerst alleen uitleggen en voorbereiden."
        if governance_status == "confirm":
            recommended_next_step = "Laat FINN dit voorbereiden en vraag daarna om expliciete bevestiging."
        elif governance_status == "block":
            recommended_next_step = "Los eerst de blocker of ontbrekende context op voordat je dit opnieuw beoordeelt."
        elif governance_status == "recommend":
            recommended_next_step = "Je kunt dit als volgende stap voorbereiden, maar ik zou de guardrails zichtbaar houden."

        return {
            "action_type": action_policy.get("action_type"),
            "subject_type": action_policy.get("subject_type"),
            "subject_id": action_policy.get("subject_id"),
            "risk_level": action_policy.get("risk_level"),
            "context_sufficiency": context_sufficiency,
            "plan_alignment": plan_alignment,
            "portfolio_conflict_level": portfolio_conflict_level,
            "confirmation_required": bool(action_policy.get("confirmation_required")),
            "execution_allowed": execution_allowed,
            "governance_status": governance_status,
            "blocking_reason": blocking_reason,
            "warnings": warnings[:3],
            "recommended_next_step": recommended_next_step,
            "audit_required": bool(action_policy.get("audit_required")),
            "rollback_mode": action_policy.get("rollback_mode") or "none",
            "policy_class": action_policy.get("action_class"),
        }
