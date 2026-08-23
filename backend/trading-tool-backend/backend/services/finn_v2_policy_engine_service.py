from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.finn_v2_policy_repository import FinnV2PolicyRepository
from backend.domain.finn_v2_contract import normalize_interaction_mode
from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.schemas.finn_v2_domain_validation_schema import EvidenceValidationResult
from backend.schemas.finn_v2_orchestrator_schema import OrchestratorResult
from backend.schemas.finn_v2_policy_schema import FinnV2PolicyDecision, POLICY_VERSION
from backend.schemas.finn_v2_state_schema import FinancialStateSnapshot
from backend.services.finn_v2_flag_service import FinnV2FlagService
from backend.services.finn_v2_json_safety import to_json_safe
from backend.services.finn_v2_risk_classification_service import FinnV2RiskClassificationService


class FinnV2PolicyEngineService:
    _ACTION_MATRIX = {
        "update_indicator_configuration": ("proposal", ["identity_context", "market_context"]),
        "create_setup": ("proposal", ["identity_context"]),
        "update_setup": ("proposal", ["plan_context"]),
        "update_strategy": ("proposal", ["plan_context"]),
        "watchlist_add": ("proposal", ["identity_context"]),
        "watchlist_remove": ("proposal", ["identity_context"]),
        "save_trade_plan": ("proposal", ["identity_context", "plan_context"]),
        "activate_paper_bot": ("paper_action", ["plan_context", "automation_context"]),
        "activate_live_bot": ("high_risk_action", ["identity_context", "market_context", "plan_context", "automation_context"]),
        "portfolio_rebalance": ("high_risk_action", ["identity_context", "portfolio_context"]),
        "manual_order": ("high_risk_action", ["identity_context", "market_context", "portfolio_context"]),
    }

    def __init__(self, session: AsyncSession, flag_service: Optional[FinnV2FlagService] = None):
        self.session = session
        self.flags = flag_service or FinnV2FlagService()
        self.decisions = FinnV2PolicyRepository(session)
        self.risk = FinnV2RiskClassificationService()
        self.operations = FinnV2OperationRegistry()

    async def evaluate_run(
        self,
        *,
        user_id: int,
        run_id: str,
        orchestrator_result: OrchestratorResult,
        snapshot: FinancialStateSnapshot,
        validation: EvidenceValidationResult,
        requested_operation: str | None = None,
    ) -> FinnV2PolicyDecision:
        if orchestrator_result.user_id != user_id or snapshot.user_id != user_id or validation.user_id != user_id:
            raise LookupError("proposal_not_owned")

        request_plan = getattr(orchestrator_result.analysis, "request_plan", None)
        contract = None
        if request_plan is not None and request_plan.operation_id:
            candidate = self.operations.require_supported(request_plan.operation_id)
            if candidate.mode == normalize_interaction_mode(orchestrator_result.analysis.interaction_mode):
                contract = candidate
        mode = contract.mode if contract is not None else normalize_interaction_mode(orchestrator_result.analysis.interaction_mode)
        domain_statuses = {domain.domain: domain.status for domain in validation.domains}
        reasons: list[str] = []
        warnings: list[str] = []
        blocks: list[str] = []
        policy_class = "unsupported_action"
        allowed = False
        proposal_allowed = False
        confirmation_required = False
        step_up_required = False
        proposal_input_required = False
        operation_type = None
        required_domains = list(orchestrator_result.domain_requirements.required_domains)
        if contract is not None:
            # Domain requirements were already derived by the registry-backed
            # planner. Policy consumes that result and never adds scopes.
            policy_class = contract.policy_class
            # The persisted policy schema uses execution-adapter operation
            # types. Workflow-only confirmation/execution contracts therefore
            # intentionally have no business operation type of their own.
            operation_type = contract.execution_adapter
            proposal_allowed = contract.proposal_type is not None
            confirmation_required = contract.confirmation_required
            proposal_input_required = contract.proposal_type is not None

        if mode == "READ":
            policy_class = contract.policy_class if contract is not None else "read"
            allowed = orchestrator_result.outcome == "reasoning_ready"
            if not allowed:
                blocks.append("orchestrator_not_ready")
        elif mode == "CAPABILITY":
            policy_class = contract.policy_class if contract is not None else "read"
            allowed = orchestrator_result.outcome == "reasoning_ready"
            if not allowed:
                blocks.append("orchestrator_not_ready")
            reasons.append("capability_registry_read_only")
        elif mode == "EVALUATE":
            policy_class = contract.policy_class if contract is not None else "advice"
            allowed = orchestrator_result.outcome == "reasoning_ready"
            if not allowed:
                blocks.append("orchestrator_not_ready")
        elif mode == "UNAVAILABLE":
            policy_class = contract.policy_class if contract is not None else "read"
            allowed = orchestrator_result.outcome == "unavailable"
            if not allowed:
                blocks.append("orchestrator_not_ready")
            reasons.append("deterministic_unavailable_delivery")
        elif mode == "CLARIFICATION":
            policy_class = contract.policy_class if contract is not None else "read"
            allowed = orchestrator_result.outcome == "clarification_required"
            if not allowed:
                blocks.append("orchestrator_not_ready")
            reasons.append("deterministic_clarification_delivery")
        elif mode == "CREATE_PROPOSAL":
            policy_class = contract.policy_class if contract is not None else "proposal"
            operation_type = operation_type or self.risk.classify_requested_operation(message="", requested_operation=requested_operation)
            proposal_allowed = contract.proposal_type is not None if contract is not None else True
            confirmation_required = contract.confirmation_required if contract is not None else True
            proposal_input_required = contract.proposal_type is not None if contract is not None else True
            if contract is None and operation_type and operation_type in self._ACTION_MATRIX:
                policy_class, required_domains = self._ACTION_MATRIX[operation_type]
            allowed = self._domains_satisfy(required_domains, domain_statuses, blocks)
        elif mode in {"ACTION_PROPOSAL", "CONFIRMATION", "EXECUTION"}:
            operation_type = operation_type or self.risk.classify_requested_operation(message="", requested_operation=requested_operation)
            if contract is None and (operation_type is None or operation_type not in self._ACTION_MATRIX):
                policy_class = "unsupported_action"
                blocks.append("action_target_unresolved")
                blocks.append("operation_unsupported")
            else:
                if contract is None:
                    policy_class, required_domains = self._ACTION_MATRIX[operation_type]
                    proposal_allowed = True
                    confirmation_required = True
                    proposal_input_required = True
                step_up_required = operation_type == "activate_live_bot" and self.flags.require_step_up_for_live()
                allowed = self._domains_satisfy(required_domains, domain_statuses, blocks)
                self._apply_action_specific_rules(
                    operation_type=operation_type,
                    snapshot=snapshot,
                    validation=validation,
                    domain_statuses=domain_statuses,
                    warnings=warnings,
                    blocks=blocks,
                )
                allowed = allowed and not blocks
        else:
            policy_class = "unsupported_action"
            blocks.append("orchestrator_not_ready")

        if validation.integrity_status == "invalid" and mode in {"CREATE_PROPOSAL", "ACTION_PROPOSAL", "CONFIRMATION", "EXECUTION"}:
            if "snapshot_integrity_invalid" not in blocks:
                blocks.append("snapshot_integrity_invalid")
            allowed = False

        decision = FinnV2PolicyDecision(
            policy_decision_id=f"finn-v2-policy-{uuid.uuid4().hex}",
            run_id=run_id,
            user_id=user_id,
            policy_class=policy_class,
            operation_type=operation_type,
            allowed=bool(allowed and not blocks),
            proposal_allowed=proposal_allowed and policy_class != "unsupported_action",
            proposal_input_required=proposal_input_required and policy_class != "unsupported_action",
            confirmation_required=confirmation_required,
            step_up_required=step_up_required,
            execution_allowed=False,
            shadow_safe=True,
            required_domains=required_domains,
            evaluated_domain_statuses={domain: domain_statuses.get(domain, "not_collected") for domain in required_domains},
            reasons=reasons or [f"mode:{mode.casefold()}"],
            warning_codes=warnings,
            blocking_codes=blocks,
            snapshot_id=snapshot.snapshot_id,
            validation_id=validation.validation_id,
            evidence_set_hash=validation.evidence_set_hash,
            policy_version=POLICY_VERSION,
            created_at=datetime.now(timezone.utc),
        )
        return decision

    def _domains_satisfy(self, required_domains: list[str], domain_statuses: dict[str, str], blocks: list[str]) -> bool:
        allowed = True
        for domain in required_domains:
            status = domain_statuses.get(domain, "not_collected")
            if status == "ambiguous":
                blocks.append("required_domain_ambiguous")
                allowed = False
            elif status in {"unavailable", "invalid", "not_collected"}:
                blocks.append("required_domain_unavailable")
                allowed = False
        return allowed

    def _apply_action_specific_rules(
        self,
        *,
        operation_type: str,
        snapshot: FinancialStateSnapshot,
        validation: EvidenceValidationResult,
        domain_statuses: dict[str, str],
        warnings: list[str],
        blocks: list[str],
    ) -> None:
        tool_outcomes = {item.tool_name: item for item in snapshot.tool_outcomes}
        if operation_type == "activate_paper_bot":
            if validation.integrity_status == "invalid":
                blocks.append("missing_bot_link")
        if operation_type == "activate_live_bot":
            if validation.integrity_status != "valid":
                blocks.append("snapshot_integrity_invalid")
            market = tool_outcomes.get("read_market_snapshot")
            bot_status = tool_outcomes.get("read_bot_status")
            if market is None or market.status != "available":
                blocks.append("market_snapshot_stale")
            if bot_status is None or bot_status.status != "available":
                blocks.append("bot_status_stale")
            if self.flags.is_action_kill_switch_enabled():
                blocks.append("kill_switch_enabled")
            if not self.flags.is_live_actions_enabled():
                blocks.append("live_action_disabled")
        if operation_type in {"portfolio_rebalance", "manual_order"}:
            warnings.append("shadow_mode_execution_blocked")

    async def persist(self, orchestrator_result_id: str, decision: FinnV2PolicyDecision) -> FinnV2PolicyDecision:
        existing = await self.decisions.get_for_run_version(
            run_id=decision.run_id,
            user_id=decision.user_id,
            policy_version=decision.policy_version,
        )
        if existing is not None:
            raise ValueError("policy_decision_exists")
        await self.decisions.create(
            id=decision.policy_decision_id,
            run_id=decision.run_id,
            user_id=decision.user_id,
            orchestrator_result_id=orchestrator_result_id,
            snapshot_id=decision.snapshot_id,
            validation_id=decision.validation_id,
            policy_class=decision.policy_class,
            operation_type=decision.operation_type,
            allowed=decision.allowed,
            proposal_allowed=decision.proposal_allowed,
            confirmation_required=decision.confirmation_required,
            step_up_required=decision.step_up_required,
            execution_allowed=decision.execution_allowed,
            shadow_safe=decision.shadow_safe,
            evidence_set_hash=decision.evidence_set_hash,
            decision_json=to_json_safe(decision.dict()),
            policy_version=decision.policy_version,
            created_at=decision.created_at,
        )
        return decision
