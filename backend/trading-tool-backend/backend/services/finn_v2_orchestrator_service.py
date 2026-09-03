from __future__ import annotations

import logging
from types import SimpleNamespace
from time import monotonic
from typing import Awaitable, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.finn_v2_orchestrator_repository import FinnV2OrchestratorRepository
from backend.infrastructure.repositories.finn_v2_conversation_repository import FinnV2ConversationRepository
from backend.infrastructure.repositories.finn_v2_run_repository import FinnV2RunRepository
from backend.infrastructure.repositories.finn_v2_trace_repository import FinnV2TraceRepository
from backend.domain.finn_v2_contract import normalize_interaction_mode
from backend.schemas.finn_v2_orchestrator_schema import LifecyclePhaseOutcome, ORCHESTRATOR_VERSION
from backend.services.finn_v2_domain_requirement_service import FinnV2DomainRequirementService
from backend.services.finn_v2_flag_service import FinnV2FlagService
from backend.services.finn_v2_orchestrator_outcome_service import FinnV2OrchestratorOutcomeService
from backend.services.finn_v2_policy_engine_service import FinnV2PolicyEngineService
from backend.services.finn_v2_reasoning_service import FinnV2ReasoningService
from backend.services.finn_v2_response_verifier_service import FinnV2ResponseVerifierService, FinnV2VerifierRejected
from backend.services.finn_v2_request_analysis_service import FinnV2RequestAnalysisService
from backend.services.finn_v2_risk_classification_service import FinnV2RiskClassificationService
from backend.services.finn_v2_tool_execution_service import FinnV2ToolExecutionService
from backend.services.finn_v2_tool_plan_service import FinnV2ToolPlanService
from backend.services.ai_usage_observability_service import ai_usage_context
from backend.services.platform_metrics import increment_execution_safety_counter, record_latency_sample


logger = logging.getLogger(__name__)


class FinnV2OrchestratorService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        flag_service: Optional[FinnV2FlagService] = None,
        complete_placeholder: Optional[Callable[..., Awaitable[None]]] = None,
        phase_transition: Optional[Callable[..., Awaitable[None]]] = None,
    ):
        self.session = session
        self.flags = flag_service or FinnV2FlagService()
        self.runs = FinnV2RunRepository(session)
        self.traces = FinnV2TraceRepository(session)
        self.results = FinnV2OrchestratorRepository(session)
        self.conversations = FinnV2ConversationRepository(session)
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
        self.phase_transition = phase_transition
        self.phase_outcome: Optional[LifecyclePhaseOutcome] = None

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

        conversation_id = getattr(run, "conversation_id", None)
        conversation_context = {}
        if conversation_id:
            conversation_context = await self.conversations.get_context(
                conversation_id=conversation_id,
                user_id=user_id,
            )
        # Selector quota is user-scoped. Without this context the OpenAI
        # boundary groups every lifecycle run into an unscoped global bucket,
        # allowing unrelated background/eval traffic to suppress user turns.
        with ai_usage_context(
            entry_point="finn_v2_selector",
            purpose="finn_v2_selector",
            user_id=user_id,
        ):
            analysis = self.analysis.analyze(
                message=run.message,
                workspace_hints=getattr(run, "workspace_hints_json", {}) or {},
                client_context=getattr(run, "client_context_json", {}) or {},
                conversation_context=conversation_context,
            )
        domain_requirements = self.requirements.determine(analysis)
        tool_plan = self.tool_plans.build(run_id=run_id, analysis=analysis, domain_plan=domain_requirements)

        result = None
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
                if normalize_interaction_mode(result.analysis.interaction_mode) in {"CREATE_PROPOSAL", "ACTION_PROPOSAL", "CONFIRMATION", "EXECUTION"}:
                    requested_operation = (
                        getattr(result.analysis.request_plan, "requested_operation", None)
                        or self.risk.classify_requested_operation(message=run.message)
                    )
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
                await self._transition_phase(
                    run_id=run_id,
                    user_id=user_id,
                    next_status="reasoning",
                    interaction_mode=result.analysis.interaction_mode,
                )
                reasoning_result = await self.reasoning.reason(
                    user_id=user_id,
                    run_id=run_id,
                    trace_id=trace_id,
                )
            verified_response = None
            if self._should_run_verifier(run=run, user_id=user_id) and reasoning_result is not None:
                await self._transition_phase(
                    run_id=run_id,
                    user_id=user_id,
                    next_status="verifying",
                    interaction_mode=getattr(reasoning_result, "mode", None) or result.analysis.interaction_mode,
                )
                verified_response = await self.verifier.verify_run(
                    user_id=user_id,
                    run_id=run_id,
                    trace_id=trace_id,
                )
            if verified_response is not None and conversation_id:
                await self._update_conversation_context(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    existing_context=conversation_context,
                    result=result,
                    verified_response=verified_response,
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
            await self._commit_persistence_boundary(stage="orchestrator_completed")
            record_latency_sample("finn_v2_orchestrator_duration_ms", int((monotonic() - started) * 1000))
            increment_execution_safety_counter(f"finn_v2_orchestrator_outcomes_total:{result.outcome}")
            self.phase_outcome = self._build_phase_outcome(
                result=result,
                verified_response=verified_response,
            )
            return result
        except FinnV2VerifierRejected as rejection:
            if conversation_id and result is not None:
                await self._update_conversation_context(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    existing_context=conversation_context,
                    result=result,
                    verified_response=self._rejected_response_lineage(rejection=rejection, run_id=run_id),
                )
            await self._append_trace(
                run_id=run_id,
                user_id=user_id,
                trace_id=trace_id,
                event_type="orchestrator_rejected",
                payload_json={
                    "run_id": run_id,
                    "user_id": user_id,
                    "verifier_result_id": rejection.verifier.verifier_result_id,
                    "reason_codes": rejection.verifier.reason_codes,
                    "duration_ms": int((monotonic() - started) * 1000),
                },
            )
            await self._commit_persistence_boundary(stage="orchestrator_rejected")
            increment_execution_safety_counter("finn_v2_orchestrator_rejections_total")
            self.phase_outcome = LifecyclePhaseOutcome(
                terminal_status="rejected",
                interaction_mode="UNAVAILABLE",
                orchestrator_result_id=result.orchestrator_result_id,
                verifier_action="reject",
            )
            return result
        except Exception as exc:
            logger.exception(
                "FINN V2 orchestrator primary failure",
                extra={
                    "trace_id": trace_id,
                    "run_id": run_id,
                    "user_id": user_id,
                    "failure_stage": "orchestrator_execute_run",
                    "service": "FinnV2OrchestratorService",
                    "method": "execute_run",
                    "primary_exception_class": exc.__class__.__name__,
                    "primary_exception_message": str(exc),
                },
            )
            result = self.outcomes.build_failed_result(
                run_id=run_id,
                user_id=user_id,
                analysis=analysis,
                domain_requirements=domain_requirements,
                tool_plan=tool_plan,
                unavailable_codes=[str(exc)],
            )
            cleanup_exc = None
            try:
                existing = await self.results.get_for_run_version(
                    run_id=run_id,
                    user_id=user_id,
                    orchestrator_version=result.orchestrator_version,
                )
                if existing is None:
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
            except Exception as inner_exc:
                cleanup_exc = inner_exc
                logger.exception(
                    "FINN V2 orchestrator cleanup failure",
                    extra={
                        "trace_id": trace_id,
                        "run_id": run_id,
                        "user_id": user_id,
                        "failure_stage": "orchestrator_cleanup",
                        "service": "FinnV2OrchestratorService",
                        "method": "execute_run",
                        "primary_exception_class": exc.__class__.__name__,
                        "primary_exception_message": str(exc),
                        "cleanup_exception_class": inner_exc.__class__.__name__,
                        "cleanup_exception_message": str(inner_exc),
                    },
                )
            increment_execution_safety_counter("finn_v2_orchestrator_failures_total")
            if cleanup_exc is not None:
                logger.error(
                    "FINN V2 orchestrator primary failure retained after cleanup error",
                    extra={
                        "trace_id": trace_id,
                        "run_id": run_id,
                        "user_id": user_id,
                        "primary_exception_class": exc.__class__.__name__,
                        "primary_exception_message": str(exc),
                        "cleanup_exception_class": cleanup_exc.__class__.__name__,
                        "cleanup_exception_message": str(cleanup_exc),
                    },
                )
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

    async def _update_conversation_context(
        self,
        *,
        conversation_id: str,
        user_id: int,
        existing_context: dict,
        result,
        verified_response,
    ) -> None:
        """Persist a durable lineage without letting failed turns poison context."""
        selectors = dict(getattr(result.tool_plan, "entity_selectors", {}) or {})
        request_plan = getattr(result.analysis, "request_plan", None)
        context = dict(existing_context or {})
        from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService

        had_canonical_state = context.get("conversation_state_version") == FinnV2OperationStateService.CONTEXT_STATE_VERSION
        context["conversation_state_version"] = FinnV2OperationStateService.CONTEXT_STATE_VERSION
        verified_context = dict(context.get("last_verified_context") or {})
        resolved_asset = selectors.get("asset") or getattr(result.analysis, "explicit_asset", None) or verified_context.get("resolved_entities", {}).get("asset")
        resolved_setup_id = selectors.get("setup_id") or getattr(result.analysis, "explicit_setup_id", None) or verified_context.get("resolved_entities", {}).get("setup_id")
        resolved_strategy_id = selectors.get("strategy_id") or getattr(result.analysis, "explicit_strategy_id", None) or verified_context.get("resolved_entities", {}).get("strategy_id")
        resolved_bot_id = selectors.get("bot_id") or getattr(result.analysis, "explicit_bot_id", None) or verified_context.get("resolved_entities", {}).get("bot_id")
        operation_state = dict(getattr(request_plan, "operation_state", {}) or {})
        response_mode = getattr(verified_response, "mode", None) or result.analysis.interaction_mode
        operation_id = getattr(request_plan, "operation_id", None)
        # A deterministic unavailable/clarification can be verifier-valid as a
        # delivery, but it is not a reusable factual conclusion for a later
        # turn.  Preserve the last usable grounded context instead.
        provenance = dict(getattr(verified_response, "reasoning_provenance", {}) or {})
        requires_lineage_proof = had_canonical_state
        is_contract_limited = provenance.get("reasoning_source") == "contract_evidence_limitation"
        is_verified = (
            getattr(verified_response, "verifier_status", None) in {"passed", "repaired"}
            and not is_contract_limited
            and response_mode in {"READ", "EVALUATE"}
            and operation_id not in {
                "off_topic", "unsupported_financial_operation",
                "explain_financial_concept", "explain_previous_evidence",
                "reformulate_previous_response",
            }
            and bool(getattr(verified_response, "evidence_refs_used", []) or [])
            and (not requires_lineage_proof or provenance.get("lineage_eligible") is True)
        )
        if is_verified:
            verified_context = {
                "verified_response_id": getattr(verified_response, "verified_response_id", None),
                "operation_id": operation_id,
                "contract_version": getattr(request_plan, "operation_contract_version", None),
                "mode": response_mode,
                "conclusion": getattr(verified_response, "main_observation", None),
                "response": getattr(verified_response, "direct_answer", None),
                "run_id": getattr(verified_response, "run_id", None),
                "evidence_refs": list(getattr(verified_response, "evidence_refs_used", []) or []),
                "required_scopes": list(getattr(request_plan, "required_information_scopes", []) or []),
                "resolved_entities": {
                    key: value for key, value in {
                        "asset": resolved_asset, "setup_id": resolved_setup_id,
                        "strategy_id": resolved_strategy_id, "bot_id": resolved_bot_id,
                    }.items() if value is not None
                },
            }
            context.update(
                {
                "last_user_goal": getattr(request_plan, "user_goal", None),
                "last_mode": response_mode,
                "resolved_asset": resolved_asset,
                "resolved_setup_id": resolved_setup_id,
                "resolved_strategy_id": resolved_strategy_id,
                "resolved_bot_id": resolved_bot_id,
                "last_evidence_refs": list(getattr(verified_response, "evidence_refs_used", []) or []),
                "last_verified_response_id": getattr(verified_response, "verified_response_id", None),
                "open_proposal_id": getattr(verified_response, "proposal_id", None),
                "last_verified_conclusion": getattr(verified_response, "main_observation", None),
                "last_verified_response_text": getattr(verified_response, "direct_answer", None),
                "last_verified_run_id": getattr(verified_response, "run_id", None),
                "last_primary_domains": list(getattr(request_plan, "primary_domains", []) or []),
                "last_required_information_scopes": list(getattr(request_plan, "required_information_scopes", []) or []),
                }
            )
        else:
            # A downgraded analysis cannot become a factual conclusion, but
            # evidence/reformulation follow-ups may safely reference its
            # retained provenance without receiving that conclusion.
            if (
                (
                    response_mode == "EVALUATE"
                    or (
                        getattr(request_plan, "operation_id", None) == "evaluate_plan"
                        and getattr(verified_response, "verifier_status", None) == "downgraded"
                    )
                )
                and operation_id not in {
                    "off_topic", "unsupported_financial_operation",
                    # Follow-ups consume existing lineage; a limited
                    # follow-up must never replace its durable source record.
                    "explain_previous_evidence", "reformulate_previous_response",
                }
            ):
                context["last_degraded_context"] = {
                    "context_version": "finn_v2.degraded-lineage.v1",
                    "operation_id": operation_id,
                    "user_goal": getattr(request_plan, "user_goal", None),
                    "mode": response_mode,
                    "conversation_id": conversation_id,
                    "run_id": getattr(verified_response, "run_id", None),
                    "evidence_refs": list(getattr(verified_response, "evidence_refs_used", []) or []),
                    "evidence_scopes": list(getattr(request_plan, "required_information_scopes", []) or []),
                    "terminal_status": self._degraded_terminal_status(
                        verified_response=verified_response,
                        is_contract_limited=is_contract_limited,
                    ),
                    "verifier_status": getattr(verified_response, "verifier_status", None),
                    "reason_codes": list(getattr(verified_response, "uncertainty_codes", []) or []),
                    "released_response_sections": [
                        {"kind": "verification_limitation", "text": "De eerdere beoordeling is niet als geverifieerde financiële conclusie vrijgegeven."},
                        {"kind": "evidence_availability", "text": "Beschikbare evidence kan wel worden toegelicht."},
                    ],
                    # Only fields already delivered to the user are eligible
                    # for a later safe reformulation.
                    "released_response": {
                        "direct_answer": getattr(verified_response, "direct_answer", None),
                        "main_observation": getattr(verified_response, "main_observation", None),
                        "uncertainty_summary": getattr(verified_response, "uncertainty_summary", None),
                        "next_step": getattr(getattr(verified_response, "next_step", None), "instruction", None),
                    },
                    "financial_conclusion_verified": False,
                    "resolved_entities": {
                        key: value for key, value in {
                            "asset": resolved_asset, "setup_id": resolved_setup_id,
                            "strategy_id": resolved_strategy_id, "bot_id": resolved_bot_id,
                        }.items() if value is not None
                    },
                }
            if operation_id in {"off_topic", "unsupported_financial_operation"}:
                context["last_safe_terminal_context"] = {
                    "context_version": "finn_v2.safe-terminal-boundary.v1",
                    "operation_id": operation_id,
                    "mode": response_mode,
                    "run_id": getattr(verified_response, "run_id", None),
                    "terminal_reason": (
                        "outside_finn_scope"
                        if operation_id == "off_topic"
                        else "unsupported_financial_operation"
                    ),
                }
            context["last_turn_diagnostics"] = {
                "operation_id": getattr(request_plan, "operation_id", None),
                "mode": response_mode,
                "verifier_status": getattr(verified_response, "verifier_status", None),
                "reason_codes": list(getattr(verified_response, "uncertainty_codes", []) or []),
            }
        context["last_verified_context"] = {key: value for key, value in verified_context.items() if value is not None}
        if operation_state.get("status") == "cancelled":
            context.pop("operation_state", None)
            context.pop("active_guided_operation", None)
            context["last_turn_diagnostics"] = {
                "operation_id": operation_state.get("operation_id"),
                "mode": response_mode,
                "verifier_status": getattr(verified_response, "verifier_status", None),
                "reason_codes": ["guided_operation_cancelled"],
            }
        elif operation_state:
            proposal_id = getattr(verified_response, "proposal_id", None)
            if proposal_id:
                operation_state.update(
                    {
                        "status": "proposed",
                        "open_proposal_id": proposal_id,
                        "missing_required_inputs": [],
                        "next_missing_input": None,
                    }
                )
            context["active_guided_operation"] = operation_state
            # New conversations have a single typed guided-operation field.
            # The legacy value is read only for historical planless contexts.
            context.pop("operation_state", None)
        await self.conversations.update_context(
            conversation_id=conversation_id,
            user_id=user_id,
            context={key: value for key, value in context.items() if value is not None},
        )

    @staticmethod
    def _degraded_terminal_status(*, verified_response, is_contract_limited: bool) -> str:
        if is_contract_limited:
            return "contract_limited"
        if getattr(verified_response, "verifier_status", None) == "rejected":
            return "rejected"
        if getattr(verified_response, "mode", None) == "UNAVAILABLE":
            return "unavailable"
        return "downgraded"

    @staticmethod
    def _rejected_response_lineage(*, rejection: FinnV2VerifierRejected, run_id: str):
        """Project a reject into the common safe terminal lineage boundary."""
        draft = rejection.draft
        return SimpleNamespace(
            verifier_status="rejected",
            mode=normalize_interaction_mode(draft.mode),
            run_id=run_id,
            evidence_refs_used=sorted(set(draft.evidence_refs_used or [])),
            uncertainty_codes=list(rejection.verifier.reason_codes or []),
            reasoning_provenance=dict(draft.reasoning_provenance or {}),
        )

    def consume_phase_outcome(self) -> LifecyclePhaseOutcome:
        if self.phase_outcome is None:
            raise RuntimeError("orchestrator_phase_outcome_missing")
        return self.phase_outcome

    def _build_phase_outcome(self, *, result, verified_response) -> LifecyclePhaseOutcome:
        if result.outcome == "clarification_required":
            return LifecyclePhaseOutcome(
                terminal_status="clarification_required",
                interaction_mode=result.analysis.interaction_mode,
                orchestrator_result_id=result.orchestrator_result_id,
            )
        if result.outcome == "unavailable":
            return LifecyclePhaseOutcome(
                terminal_status="unavailable",
                interaction_mode=result.analysis.interaction_mode,
                orchestrator_result_id=result.orchestrator_result_id,
            )
        if result.outcome == "failed":
            return LifecyclePhaseOutcome(
                terminal_status="failed",
                interaction_mode=result.analysis.interaction_mode,
                orchestrator_result_id=result.orchestrator_result_id,
            )
        if verified_response is None:
            raise RuntimeError("orchestrator_phase_outcome_incomplete")
        verifier_status = getattr(verified_response, "verifier_status", None)
        if verifier_status == "downgraded":
            terminal_status = "downgraded"
        elif verifier_status == "passed":
            terminal_status = "completed"
        else:
            raise RuntimeError("orchestrator_phase_outcome_invalid_verifier_status")
        return LifecyclePhaseOutcome(
            terminal_status=terminal_status,
            interaction_mode=getattr(verified_response, "mode", None) or result.analysis.interaction_mode,
            orchestrator_result_id=result.orchestrator_result_id,
            verifier_action="deliver",
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

    async def _transition_phase(
        self,
        *,
        run_id: str,
        user_id: int,
        next_status: str,
        interaction_mode: Optional[str],
    ) -> None:
        if self.phase_transition is None:
            return
        # The owned lifecycle writes its next phase in a fresh session. Commit
        # accumulated tool/evidence state first so that session cannot wait on
        # this session's uncommitted trace sequence.
        await self._commit_persistence_boundary(stage=f"before_{next_status}_transition")
        await self.phase_transition(
            run_id=run_id,
            user_id=user_id,
            next_status=next_status,
            interaction_mode=interaction_mode,
            response_source="v2_runtime",
        )

    async def _commit_persistence_boundary(self, *, stage: str) -> None:
        commit = getattr(self.session, "commit", None)
        if not callable(commit):
            return
        try:
            await commit()
        except Exception:
            rollback = getattr(self.session, "rollback", None)
            if callable(rollback):
                try:
                    await rollback()
                except Exception:
                    logger.exception(
                        "FINN V2 orchestrator boundary rollback failed",
                        extra={"failure_stage": stage},
                    )
            logger.exception(
                "FINN V2 orchestrator persistence boundary failed",
                extra={"failure_stage": stage},
            )
            raise
