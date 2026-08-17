from __future__ import annotations

import logging
from time import monotonic
from typing import Awaitable, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.finn_v2_orchestrator_repository import FinnV2OrchestratorRepository
from backend.infrastructure.repositories.finn_v2_run_repository import FinnV2RunRepository
from backend.infrastructure.repositories.finn_v2_trace_repository import FinnV2TraceRepository
from backend.schemas.finn_v2_orchestrator_schema import ORCHESTRATOR_VERSION
from backend.services.finn_v2_domain_requirement_service import FinnV2DomainRequirementService
from backend.services.finn_v2_flag_service import FinnV2FlagService
from backend.services.finn_v2_orchestrator_outcome_service import FinnV2OrchestratorOutcomeService
from backend.services.finn_v2_policy_engine_service import FinnV2PolicyEngineService
from backend.services.finn_v2_reasoning_service import FinnV2ReasoningService
from backend.services.finn_v2_response_verifier_service import FinnV2ResponseVerifierService
from backend.services.finn_v2_request_analysis_service import FinnV2RequestAnalysisService
from backend.services.finn_v2_risk_classification_service import FinnV2RiskClassificationService
from backend.services.finn_v2_tool_execution_service import FinnV2ToolExecutionService
from backend.services.finn_v2_tool_plan_service import FinnV2ToolPlanService
from backend.services.platform_metrics import increment_execution_safety_counter, record_latency_sample


logger = logging.getLogger(__name__)


class FinnV2OrchestratorService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        flag_service: Optional[FinnV2FlagService] = None,
        complete_placeholder: Optional[Callable[..., Awaitable[None]]] = None,
    ):
        self.session = session
        self.flags = flag_service or FinnV2FlagService()
        self.runs = FinnV2RunRepository(session)
        self.traces = FinnV2TraceRepository(session)
        self.results = FinnV2OrchestratorRepository(session)
        self.analysis = FinnV2RequestAnalysisService()
        self.requirements = FinnV2DomainRequirementService()
        self.tool_plans = FinnV2ToolPlanService()
        self.tools = FinnV2ToolExecutionService(session, self.flags)
        self.outcomes = FinnV2OrchestratorOutcomeService()
        self.policy = FinnV2PolicyEngineService(session, self.flags)
        self.risk = FinnV2RiskClassificationService()
        self.reasoning = FinnV2ReasoningService(session, flag_service=self.flags)
        self.verifier = FinnV2ResponseVerifierService(session, flag_service=self.flags)
        self.complete_placeholder = complete_placeholder

    async def execute_run(
        self,
        *,
        user_id: int,
        run_id: str,
        trace_id: str,
    ):
        started = monotonic()
        run = await self.runs.get_by_id_for_user(run_id=run_id, user_id=user_id)
        if run is None:
            raise LookupError("FINN V2 run not found")
        if run.status != "planned":
            raise ValueError("orchestrator_run_invalid_state")
        if not self.flags.is_tool_registry_enabled() or not self.flags.is_state_assembly_enabled():
            raise ValueError("orchestrator_feature_disabled")

        await self._append_trace(
            run_id=run_id,
            user_id=user_id,
            trace_id=trace_id,
            event_type="orchestrator_started",
            payload_json={"run_id": run_id, "user_id": user_id, "orchestrator_version": ORCHESTRATOR_VERSION},
        )

        analysis = self.analysis.analyze(
            message=run.message,
            workspace_hints=getattr(run, "workspace_hints_json", {}) or {},
            client_context=getattr(run, "client_context_json", {}) or {},
        )
        domain_requirements = self.requirements.determine(analysis)
        tool_plan = self.tool_plans.build(run_id=run_id, analysis=analysis, domain_plan=domain_requirements)

        try:
            await self.tools.execute_tool_plan(run_id=run_id, user_id=user_id, tool_plan=tool_plan)
            snapshot, validation = await self.tools.run_state_pipeline(run_id=run_id, user_id=user_id)
            result = self.outcomes.evaluate(
                run_id=run_id,
                user_id=user_id,
                analysis=analysis,
                domain_requirements=domain_requirements,
                tool_plan=tool_plan,
                snapshot_id=getattr(snapshot, "snapshot_id", None),
                validation=validation,
            )
            await self._persist_result(result)
            policy_decision = None
            if self._should_run_policy(run=run, user_id=user_id) and snapshot is not None and validation is not None and result.outcome != "failed":
                requested_operation = None
                if result.analysis.interaction_mode == "ACTION":
                    requested_operation = self.risk.classify_requested_operation(message=run.message)
                await self._append_trace(
                    run_id=run_id,
                    user_id=user_id,
                    trace_id=trace_id,
                    event_type="policy_evaluation_started",
                    payload_json={"run_id": run_id, "user_id": user_id, "interaction_mode": result.analysis.interaction_mode},
                )
                policy_decision = await self.policy.evaluate_run(
                    user_id=user_id,
                    run_id=run_id,
                    orchestrator_result=result,
                    snapshot=snapshot,
                    validation=validation,
                    requested_operation=requested_operation,
                )
                await self.policy.persist(result.orchestrator_result_id, policy_decision)
                await self._append_trace(
                    run_id=run_id,
                    user_id=user_id,
                    trace_id=trace_id,
                    event_type="policy_evaluation_completed",
                    payload_json={
                        "run_id": run_id,
                        "user_id": user_id,
                        "policy_class": policy_decision.policy_class,
                        "allowed": policy_decision.allowed,
                        "proposal_input_required": policy_decision.proposal_input_required,
                        "blocking_codes": policy_decision.blocking_codes,
                    },
                )
                increment_execution_safety_counter(
                    f"finn_v2_policy_decisions_total:{policy_decision.policy_class}:{str(policy_decision.allowed).lower()}"
                )
                if policy_decision.blocking_codes:
                    await self._append_trace(
                        run_id=run_id,
                        user_id=user_id,
                        trace_id=trace_id,
                        event_type="policy_blocked",
                        payload_json={"run_id": run_id, "user_id": user_id, "blocking_codes": policy_decision.blocking_codes},
                    )
                    for code in policy_decision.blocking_codes:
                        increment_execution_safety_counter(f"finn_v2_policy_blocks_total:{code}")
            reasoning_result = None
            if self._should_run_reasoning(run=run, user_id=user_id) and result.outcome != "failed":
                reasoning_result = await self.reasoning.reason(
                    user_id=user_id,
                    run_id=run_id,
                    trace_id=trace_id,
                )
            verified_response = None
            if self._should_run_verifier(run=run, user_id=user_id) and reasoning_result is not None:
                verified_response = await self.verifier.verify_run(
                    user_id=user_id,
                    run_id=run_id,
                    trace_id=trace_id,
                )
            await self._append_trace(
                run_id=run_id,
                user_id=user_id,
                trace_id=trace_id,
                event_type="orchestrator_completed",
                payload_json={
                    "run_id": run_id,
                    "user_id": user_id,
                    "outcome": result.outcome,
                    "snapshot_id": result.snapshot_id,
                    "validation_id": result.validation_id,
                    "required_domains": result.domain_requirements.required_domains,
                    "policy_class": getattr(policy_decision, "policy_class", None),
                    "proposal_input_required": getattr(policy_decision, "proposal_input_required", False),
                    "reasoning_status": getattr(reasoning_result, "status", None),
                    "verified_response_mode": getattr(verified_response, "mode", None),
                    "verified_response_status": getattr(verified_response, "verifier_status", None),
                    "duration_ms": int((monotonic() - started) * 1000),
                },
            )
            record_latency_sample("finn_v2_orchestrator_duration_ms", int((monotonic() - started) * 1000))
            increment_execution_safety_counter(f"finn_v2_orchestrator_outcomes_total:{result.outcome}")
            if self.complete_placeholder is not None:
                await self.complete_placeholder(
                    run_id=run_id,
                    user_id=user_id,
                    interaction_mode=analysis.interaction_mode,
                )
            return result
        except Exception as exc:
            logger.exception("FINN V2 orchestrator failed", extra={"run_id": run_id, "user_id": user_id})
            result = self.outcomes.build_failed_result(
                run_id=run_id,
                user_id=user_id,
                analysis=analysis,
                domain_requirements=domain_requirements,
                tool_plan=tool_plan,
                unavailable_codes=[str(exc)],
            )
            await self._persist_result(result)
            await self._append_trace(
                run_id=run_id,
                user_id=user_id,
                trace_id=trace_id,
                event_type="orchestrator_failed",
                payload_json={
                    "run_id": run_id,
                    "user_id": user_id,
                    "issue_codes": result.unavailable_codes,
                    "duration_ms": int((monotonic() - started) * 1000),
                },
            )
            increment_execution_safety_counter("finn_v2_orchestrator_failures_total")
            raise

    async def _persist_result(self, result) -> None:
        existing = await self.results.get_for_run_version(
            run_id=result.run_id,
            user_id=result.user_id,
            orchestrator_version=result.orchestrator_version,
        )
        if existing is not None:
            raise ValueError("orchestrator_result_exists")
        await self.results.create(
            id=result.orchestrator_result_id,
            run_id=result.run_id,
            user_id=result.user_id,
            orchestrator_version=result.orchestrator_version,
            analysis_version=result.analysis.analysis_version,
            planning_version=result.tool_plan.planning_version,
            interaction_mode=result.analysis.interaction_mode,
            subject_scopes_json=result.analysis.subject_scopes,
            required_domains_json=result.domain_requirements.required_domains,
            optional_domains_json=result.domain_requirements.optional_domains,
            tool_plan_json=result.tool_plan.dict(),
            snapshot_id=result.snapshot_id,
            validation_id=result.validation_id,
            outcome=result.outcome,
            selected_clarification_json=result.selected_clarification.dict() if result.selected_clarification else None,
            unavailable_codes_json=result.unavailable_codes,
            uncertainty_codes_json=result.uncertainty_codes,
            created_at=result.created_at,
        )

    async def _append_trace(self, *, run_id: str, user_id: int, trace_id: str, event_type: str, payload_json: dict) -> None:
        await self.traces.append_event(
            run_id=run_id,
            user_id=user_id,
            trace_id=trace_id,
            event_type=event_type,
            payload_json=payload_json,
        )

    def _is_visible_run(self, run) -> bool:
        return getattr(run, "visibility", None) == "visible" or getattr(run, "feature_mode", None) == "visible_readonly"

    def _should_run_policy(self, *, run, user_id: int) -> bool:
        return self._is_visible_run(run) or self.flags.should_run_block5_shadow(user_id)

    def _should_run_reasoning(self, *, run, user_id: int) -> bool:
        return self._is_visible_run(run) or self.flags.should_run_block6_shadow(user_id)

    def _should_run_verifier(self, *, run, user_id: int) -> bool:
        return self._is_visible_run(run) or self.flags.should_run_block7_shadow(user_id)
