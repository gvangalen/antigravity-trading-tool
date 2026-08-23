from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from time import monotonic
from typing import Optional

from pydantic import ValidationError

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.finn_v2_orchestrator_repository import FinnV2OrchestratorRepository
from backend.infrastructure.repositories.finn_v2_policy_repository import FinnV2PolicyRepository
from backend.infrastructure.repositories.finn_v2_reasoning_repository import FinnV2ReasoningRepository
from backend.infrastructure.repositories.finn_v2_run_repository import FinnV2RunRepository
from backend.infrastructure.repositories.finn_v2_state_repository import FinnV2StateRepository
from backend.infrastructure.repositories.finn_v2_trace_repository import FinnV2TraceRepository
from backend.infrastructure.repositories.finn_v2_validation_repository import FinnV2ValidationRepository
from backend.domain.finn_v2_contract import normalize_interaction_mode
from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.schemas.finn_v2_orchestrator_schema import ORCHESTRATOR_VERSION, OrchestratorResult
from backend.schemas.finn_v2_policy_schema import POLICY_VERSION, FinnV2PolicyDecision
from backend.schemas.finn_v2_reasoning_context_schema import REASONING_CONTEXT_VERSION
from backend.schemas.finn_v2_reasoning_schema import (
    FINN_V2_REASONING_PROMPT_VERSION,
    FINN_V2_REASONING_SCHEMA_VERSION,
    FINN_V2_REASONING_VERSION,
    PersistedReasoningRecord,
    ReasoningResult,
)
from backend.services.finn_v2_flag_service import FinnV2FlagService
from backend.services.finn_v2_capability_registry_service import FinnV2CapabilityRegistryService
from backend.services.finn_v2_json_safety import to_json_safe
from backend.services.finn_v2_reasoning_context_service import FinnV2ReasoningContextService
from backend.services.finn_v2_reasoning_fallback_service import FinnV2ReasoningFallbackService
from backend.services.finn_v2_reasoning_prompt_service import (
    FinnV2ReasoningPromptContractError,
    FinnV2ReasoningPromptService,
)
from backend.services.platform_metrics import increment_execution_safety_counter, record_latency_sample
from backend.utils import openai_client


logger = logging.getLogger(__name__)


class FinnV2ReasoningContractError(ValueError):
    """Raised when model output is structurally valid but incomplete for the request contract."""

    def __init__(
        self,
        *,
        code: str,
        missing_scopes: list[str],
        path: str = "evidence_refs_used",
        grounding_values: Optional[dict[str, list[str]]] = None,
    ):
        self.code = code
        self.missing_scopes = missing_scopes
        self.path = path
        self.grounding_values = grounding_values or {}
        super().__init__(f"{code}:{','.join(missing_scopes)}")


class FinnV2ReasoningService:
    def __init__(self, session: AsyncSession, *, flag_service: Optional[FinnV2FlagService] = None):
        self.session = session
        self.flags = flag_service or FinnV2FlagService()
        self.runs = FinnV2RunRepository(session)
        self.orchestrators = FinnV2OrchestratorRepository(session)
        self.policies = FinnV2PolicyRepository(session)
        self.snapshots = FinnV2StateRepository(session)
        self.validations = FinnV2ValidationRepository(session)
        self.reasoning = FinnV2ReasoningRepository(session)
        self.traces = FinnV2TraceRepository(session)
        self.contexts = FinnV2ReasoningContextService(
            session,
            max_evidence_items=self.flags.reasoning_max_evidence_items(),
            max_context_bytes=self.flags.reasoning_max_context_bytes(),
        )
        self.capabilities = FinnV2CapabilityRegistryService()
        self.prompts = FinnV2ReasoningPromptService()
        self.fallbacks = FinnV2ReasoningFallbackService()
        self.operations = FinnV2OperationRegistry()

    async def reason(self, *, user_id: int, run_id: str, trace_id: str):
        run = await self.runs.get_by_id_for_user(run_id=run_id, user_id=user_id)
        if run is None:
            raise LookupError("FINN V2 run not found")

        orchestrator_row = await self.orchestrators.get_for_run_version(run_id=run_id, user_id=user_id, orchestrator_version=ORCHESTRATOR_VERSION)
        if orchestrator_row is None:
            raise ValueError("orchestrator_not_ready")
        persisted_tool_plan = dict(orchestrator_row.tool_plan_json or {})
        persisted_request_plan = persisted_tool_plan.get("request_plan") or {}
        selectors = persisted_tool_plan.get("entity_selectors") or {}
        orchestrator_result = OrchestratorResult.parse_obj(
            {
                "orchestrator_result_id": orchestrator_row.id,
                "run_id": orchestrator_row.run_id,
                "user_id": orchestrator_row.user_id,
                "analysis": {
                    "interaction_mode": normalize_interaction_mode(orchestrator_row.interaction_mode),
                    "subject_scopes": orchestrator_row.subject_scopes_json,
                    "explicit_asset": selectors.get("asset"),
                    "explicit_setup_id": selectors.get("setup_id"),
                    "explicit_strategy_id": selectors.get("strategy_id"),
                    "explicit_bot_id": selectors.get("bot_id"),
                    "primary_subject": persisted_tool_plan.get("primary_subject"),
                    "output_contract": persisted_tool_plan.get("expected_response_contract"),
                    "requires_comparison": False,
                    "requires_gap_analysis": False,
                    "requests_change": normalize_interaction_mode(orchestrator_row.interaction_mode) in {"CREATE_PROPOSAL", "ACTION_PROPOSAL", "CONFIRMATION", "EXECUTION"},
                    "requests_execution": normalize_interaction_mode(orchestrator_row.interaction_mode) == "EXECUTION",
                    "confidence": "medium",
                    "matched_signals": [],
                    "unresolved_signals": [],
                    "reasoning_required": normalize_interaction_mode(orchestrator_row.interaction_mode) in {"CAPABILITY", "READ", "EVALUATE", "CREATE_PROPOSAL", "ACTION_PROPOSAL", "CONFIRMATION", "EXECUTION"},
                    "request_plan": persisted_request_plan or None,
                    "analysis_version": orchestrator_row.analysis_version,
                },
                "domain_requirements": {
                    "required_domains": orchestrator_row.required_domains_json,
                    "optional_domains": orchestrator_row.optional_domains_json,
                    "requirement_reason": [],
                },
                "tool_plan": persisted_tool_plan,
                "snapshot_id": orchestrator_row.snapshot_id,
                "validation_id": orchestrator_row.validation_id,
                "outcome": orchestrator_row.outcome,
                "selected_clarification": orchestrator_row.selected_clarification_json,
                "unavailable_codes": orchestrator_row.unavailable_codes_json,
                "uncertainty_codes": orchestrator_row.uncertainty_codes_json,
                "orchestrator_version": orchestrator_row.orchestrator_version,
                "created_at": orchestrator_row.created_at,
            }
        )
        mode = normalize_interaction_mode(orchestrator_result.analysis.interaction_mode)
        snapshot = await self.snapshots.get_by_id_for_user(snapshot_id=orchestrator_result.snapshot_id, user_id=user_id) if orchestrator_result.snapshot_id else None
        validation = await self.validations.get_by_id_for_user(validation_id=orchestrator_result.validation_id, user_id=user_id) if orchestrator_result.validation_id else None
        policy_row = await self.policies.get_for_run_version(run_id=run_id, user_id=user_id, policy_version=POLICY_VERSION)
        policy = FinnV2PolicyDecision.parse_obj(policy_row.decision_json) if policy_row is not None else None

        if orchestrator_result.outcome != "reasoning_ready":
            result = self.fallbacks.deterministic_draft(run_id=run_id, user_id=user_id, orchestrator_result=orchestrator_result, model=self._resolved_model())
            return await self._persist_record(
                run_id=run_id,
                user_id=user_id,
                orchestrator_result_id=orchestrator_result.orchestrator_result_id,
                policy_decision_id=policy.policy_decision_id if policy is not None else "",
                snapshot_id=snapshot.id if snapshot is not None else "",
                validation_id=validation.id if validation is not None else "",
                status="unavailable",
                mode=result.mode,
                context_version=REASONING_CONTEXT_VERSION,
                evidence_set_hash=validation.evidence_set_hash if validation is not None else "",
                input_hash="",
                model=result.model,
                result=result,
                error_codes=orchestrator_result.unavailable_codes or orchestrator_result.uncertainty_codes,
                retry_count=0,
            )

        if snapshot is None or validation is None or policy is None:
            raise ValueError("reasoning_dependencies_missing")
        if validation.integrity_status == "invalid":
            result = self.fallbacks.unavailable_draft(
                run_id=run_id,
                user_id=user_id,
                mode=mode,
                error_codes=["snapshot_integrity_invalid"],
                model=self._resolved_model(),
            )
            return await self._persist_record(
                run_id=run_id,
                user_id=user_id,
                orchestrator_result_id=orchestrator_result.orchestrator_result_id,
                policy_decision_id=policy.policy_decision_id,
                snapshot_id=snapshot.id,
                validation_id=validation.id,
                status="unavailable",
                mode=result.mode,
                context_version=REASONING_CONTEXT_VERSION,
                evidence_set_hash=validation.evidence_set_hash,
                input_hash="",
                model=result.model,
                result=result,
                error_codes=["snapshot_integrity_invalid"],
                retry_count=0,
            )

        context = await self.contexts.build(run=run, orchestrator_result=orchestrator_result, snapshot=snapshot, validation=validation, policy=policy)
        model_name = self._resolved_model()
        input_hash = self.contexts.input_hash(context, prompt_version=self.prompts.PROMPT_VERSION, model=model_name)
        request_plan = orchestrator_result.analysis.request_plan
        contract = self.operations.require_supported(request_plan.operation_id) if request_plan and request_plan.operation_id else None

        if (
            normalize_interaction_mode(context.interaction_mode) in {"ACTION_PROPOSAL", "EXECUTION"}
            and not context.policy.allowed
            and context.policy.operation_type == "activate_live_bot"
        ):
            result = self.fallbacks.blocked_action_draft(
                run_id=run_id,
                user_id=user_id,
                context=context,
                model=model_name,
                error_codes=list(context.policy.blocking_codes or ["live_action_disabled"]),
            )
            await self._append_trace(run_id, user_id, trace_id, "reasoning_blocked_live_action", context, model_name, "unavailable", 0, 0, input_hash, list(context.policy.blocking_codes or ["live_action_disabled"]))
            return await self._persist_record(
                run_id=run_id,
                user_id=user_id,
                orchestrator_result_id=orchestrator_result.orchestrator_result_id,
                policy_decision_id=policy.policy_decision_id,
                snapshot_id=snapshot.id,
                validation_id=validation.id,
                status="unavailable",
                mode=result.mode,
                context_version=context.context_version,
                evidence_set_hash=context.evidence_set_hash,
                input_hash=input_hash,
                model=model_name,
                result=result,
                error_codes=list(context.policy.blocking_codes or ["live_action_disabled"]),
                retry_count=0,
            )

        if normalize_interaction_mode(context.interaction_mode) == "CAPABILITY":
            result = self.capabilities.build_reasoning_result(
                run_id=run_id,
                user_id=user_id,
                user_message=run.message,
                locale=context.locale,
                model=model_name,
                missing_context=getattr(run, "client_context_json", {}).get("missing_context") or [],
                asset=getattr(run, "client_context_json", {}).get("asset") or getattr(run, "workspace_hints_json", {}).get("asset"),
                profile_completed=not bool(getattr(run, "client_context_json", {}).get("trader_profile_used") is False),
            )
            await self._append_trace(run_id, user_id, trace_id, "reasoning_capability_registry", context, model_name, "ready", 0, 0, input_hash, [])
            return await self._persist_record(
                run_id=run_id,
                user_id=user_id,
                orchestrator_result_id=orchestrator_result.orchestrator_result_id,
                policy_decision_id=policy.policy_decision_id,
                snapshot_id=snapshot.id,
                validation_id=validation.id,
                status="ready",
                mode=result.mode,
                context_version=context.context_version,
                evidence_set_hash=context.evidence_set_hash,
                input_hash=input_hash,
                model=model_name,
                result=result,
                error_codes=[],
                retry_count=0,
            )

        if contract is not None and contract.model_policy == "never":
            result = self.fallbacks.grounded_read_draft(
                run_id=run_id,
                user_id=user_id,
                context=context,
                model=model_name,
                error_codes=[],
            )
            result.reasoning_provenance = {
                "provider_called": False,
                "reasoning_source": "deterministic_contract",
                "operation_id": contract.operation_id,
                "model_policy": contract.model_policy,
                "validation_status": "passed",
            }
            await self._append_trace(run_id, user_id, trace_id, "reasoning_deterministic_contract", context, model_name, "ready", 0, 0, input_hash, [])
            return await self._persist_record(
                run_id=run_id,
                user_id=user_id,
                orchestrator_result_id=orchestrator_result.orchestrator_result_id,
                policy_decision_id=policy.policy_decision_id,
                snapshot_id=snapshot.id,
                validation_id=validation.id,
                status="ready",
                mode=result.mode,
                context_version=context.context_version,
                evidence_set_hash=context.evidence_set_hash,
                input_hash=input_hash,
                model=model_name,
                result=result,
                error_codes=[],
                retry_count=0,
            )

        reused = await self.reasoning.get_reusable_result(
            run_id=run_id,
            user_id=user_id,
            context_version=context.context_version,
            evidence_set_hash=context.evidence_set_hash,
            prompt_version=self.prompts.PROMPT_VERSION,
            model=model_name,
        )
        if reused is not None:
            await self._append_trace(run_id, user_id, trace_id, "reasoning_result_reused", context, model_name, "ready", 0, 0, input_hash, [])
            increment_execution_safety_counter("finn_v2_reasoning_reuse_total")
            return PersistedReasoningRecord(
                reasoning_result_id=reused.id,
                run_id=reused.run_id,
                user_id=reused.user_id,
                orchestrator_result_id=reused.orchestrator_result_id,
                policy_decision_id=reused.policy_decision_id,
                snapshot_id=reused.snapshot_id,
                validation_id=reused.validation_id,
                status=reused.status,
                mode=reused.mode,
                context_version=reused.context_version,
                evidence_set_hash=reused.evidence_set_hash,
                input_hash=reused.input_hash,
                prompt_version=reused.prompt_version,
                schema_version=reused.schema_version,
                reasoning_version=reused.reasoning_version,
                model=reused.model,
                result=ReasoningResult.parse_obj(reused.result_json) if reused.result_json else None,
                error_codes=reused.error_codes_json,
                input_tokens=reused.input_tokens,
                output_tokens=reused.output_tokens,
                reasoning_tokens=reused.reasoning_tokens,
                latency_ms=reused.latency_ms,
                retry_count=reused.retry_count,
                created_at=reused.created_at,
                completed_at=reused.completed_at,
            )

        availability = openai_client.get_openai_runtime_status()
        if (
            (not self._is_visible_run(run) and not self.flags.should_run_block6_shadow(user_id))
            or not availability.get("configured")
            or not openai_client.get_ai_availability()["available"]
        ):
            result = self._fallback_for_reasoning_error(
                run_id=run_id,
                user_id=user_id,
                context=context,
                model_name=model_name,
                error_codes=[str(openai_client.get_ai_availability().get("reason") or "ai_unavailable_configuration")],
            )
            await self._append_trace(run_id, user_id, trace_id, "reasoning_unavailable", context, model_name, "unavailable", None, 0, input_hash, [str(openai_client.get_ai_availability().get("reason") or "ai_unavailable_configuration")])
            return await self._persist_record(
                run_id=run_id,
                user_id=user_id,
                orchestrator_result_id=orchestrator_result.orchestrator_result_id,
                policy_decision_id=policy.policy_decision_id,
                snapshot_id=snapshot.id,
                validation_id=validation.id,
                status="unavailable",
                mode=result.mode,
                context_version=context.context_version,
                evidence_set_hash=context.evidence_set_hash,
                input_hash=input_hash,
                model=model_name,
                result=result,
                error_codes=[str(openai_client.get_ai_availability().get("reason") or "ai_unavailable_configuration")],
                retry_count=0,
            )

        return await self._run_model_reasoning(
            run_id=run_id,
            user_id=user_id,
            trace_id=trace_id,
            orchestrator_result=orchestrator_result,
            policy=policy,
            snapshot=snapshot,
            validation=validation,
            context=context,
            model_name=model_name,
            input_hash=input_hash,
        )

    async def _run_model_reasoning(self, *, run_id: str, user_id: int, trace_id: str, orchestrator_result, policy, snapshot, validation, context, model_name: str, input_hash: str):
        started = monotonic()
        await self._append_trace(run_id, user_id, trace_id, "reasoning_context_built", context, model_name, "pending", None, 0, input_hash, [])
        try:
            system_prompt = self.prompts.build_system_prompt(context)
        except FinnV2ReasoningPromptContractError as exc:
            await self._append_trace(
                run_id,
                user_id,
                trace_id,
                "reasoning_failed",
                context,
                model_name,
                "failed",
                int((monotonic() - started) * 1000),
                0,
                input_hash,
                [exc.code],
            )
            fallback = self.fallbacks.unavailable_draft(
                run_id=run_id,
                user_id=user_id,
                mode=context.interaction_mode,
                error_codes=[exc.code],
                model=model_name,
            )
            return await self._persist_record(
                run_id=run_id,
                user_id=user_id,
                orchestrator_result_id=orchestrator_result.orchestrator_result_id,
                policy_decision_id=policy.policy_decision_id,
                snapshot_id=snapshot.id,
                validation_id=validation.id,
                status="failed",
                mode=fallback.mode,
                context_version=context.context_version,
                evidence_set_hash=context.evidence_set_hash,
                input_hash=input_hash,
                model=model_name,
                result=fallback,
                error_codes=[exc.code],
                retry_count=0,
                latency_ms=int((monotonic() - started) * 1000),
            )
        retries_allowed = self.flags.reasoning_max_retries()
        last_error_codes: list[str] = []
        repair_validation_errors: list[dict[str, object]] = []
        repair_previous_response: dict[str, object] | None = None
        for attempt in range(retries_allowed + 1):
            await self._append_trace(run_id, user_id, trace_id, "reasoning_started", context, model_name, "generating", None, attempt, input_hash, [])
            # Do not hold the transaction that contains tool/evidence state while
            # waiting for the external provider. This also releases the pooled DB
            # connection for concurrent FINN runs.
            await self._commit_before_provider_call()
            call_started = monotonic()
            response = openai_client.ask_gpt_structured_response(
                prompt=self.prompts.build_user_prompt(
                    context,
                    repair_attempt=attempt > 0,
                    validation_errors=repair_validation_errors,
                    previous_response=repair_previous_response,
                ),
                system_role=system_prompt,
                schema=self.prompts.response_schema(),
                model_override=model_name,
                timeout_seconds=self.flags.reasoning_timeout_seconds(),
                max_output_tokens=self.flags.reasoning_max_output_tokens(),
                client_max_retries=0,
            )
            call_latency_ms = int((monotonic() - call_started) * 1000)
            logger.info(
                "FINN V2 reasoning model call finished",
                extra={
                    "run_id": run_id,
                    "user_id": user_id,
                    "trace_id": trace_id,
                    "stage": "reasoning_model",
                    "call_purpose": "primary_reasoning" if attempt == 0 else "retry",
                    "interaction_mode": context.interaction_mode,
                    "attempt": attempt,
                    "model": response.get("model") or model_name,
                    "latency_ms": call_latency_ms,
                    "output_status": "error" if response.get("error") else "ok",
                    "error_code": response.get("error"),
                    "error_detail": response.get("error_detail"),
                },
            )
            if response.get("error"):
                error = str(response["error"])
                last_error_codes = [error]
                normalized_mode = normalize_interaction_mode(context.interaction_mode)
                if attempt < retries_allowed and error in {"schema_invalid", "incomplete_structured_response"}:
                    await self._append_trace(
                        run_id,
                        user_id,
                        trace_id,
                        "reasoning_repair",
                        context,
                        model_name,
                        "generating",
                        None,
                        attempt + 1,
                        input_hash,
                        [error],
                        error_details=response.get("error_detail"),
                    )
                    increment_execution_safety_counter(f"finn_v2_reasoning_repairs_total:{error}")
                    continue
                if normalized_mode in {"EVALUATE", "CREATE_PROPOSAL", "ACTION_PROPOSAL"} and error in {"provider_error", "schema_invalid", "incomplete_structured_response", "timeout"}:
                    result = self._fallback_for_reasoning_error(
                        run_id=run_id,
                        user_id=user_id,
                        context=context,
                        model_name=model_name,
                        error_codes=[error],
                    )
                    await self._append_trace(
                        run_id,
                        user_id,
                        trace_id,
                        "reasoning_fallback_ready",
                        context,
                        model_name,
                        "ready",
                        int((monotonic() - started) * 1000),
                        attempt,
                        input_hash,
                        [error, "deterministic_validated"],
                        error_details=response.get("error_detail"),
                    )
                    return await self._persist_record(
                        run_id=run_id,
                        user_id=user_id,
                        orchestrator_result_id=orchestrator_result.orchestrator_result_id,
                        policy_decision_id=policy.policy_decision_id,
                        snapshot_id=snapshot.id,
                        validation_id=validation.id,
                        status="ready",
                        mode=result.mode,
                        context_version=context.context_version,
                        evidence_set_hash=context.evidence_set_hash,
                        input_hash=input_hash,
                        model=model_name,
                        result=result,
                        error_codes=[error, "deterministic_validated"],
                        retry_count=attempt,
                        input_tokens=response.get("input_tokens"),
                        output_tokens=response.get("output_tokens"),
                        reasoning_tokens=response.get("reasoning_tokens"),
                        latency_ms=int((monotonic() - started) * 1000),
                    )
                if attempt < retries_allowed and error in {"provider_error", "schema_invalid", "incomplete_structured_response", "timeout"}:
                    await self._append_trace(run_id, user_id, trace_id, "reasoning_retry", context, model_name, "generating", None, attempt + 1, input_hash, [error])
                    increment_execution_safety_counter(f"finn_v2_reasoning_retries_total:{error}")
                    continue
                fallback_ready_modes = {"READ", "EVALUATE"}
                fallback_status = "ready" if normalized_mode in fallback_ready_modes else None
                status = fallback_status or ("unavailable" if error in {"ai_unavailable_budget", "ai_unavailable_configuration", "ai_rate_limited"} else "failed")
                event = "reasoning_unavailable" if status == "unavailable" else "reasoning_failed"
                if status == "ready":
                    event = "reasoning_fallback_ready"
                await self._append_trace(run_id, user_id, trace_id, event, context, model_name, status, int((monotonic() - started) * 1000), attempt, input_hash, [error])
                result = self._fallback_for_reasoning_error(
                    run_id=run_id,
                    user_id=user_id,
                    context=context,
                    model_name=model_name,
                    error_codes=[error],
                )
                return await self._persist_record(
                    run_id=run_id,
                    user_id=user_id,
                    orchestrator_result_id=orchestrator_result.orchestrator_result_id,
                    policy_decision_id=policy.policy_decision_id,
                    snapshot_id=snapshot.id,
                    validation_id=validation.id,
                    status=status,
                    mode=result.mode,
                    context_version=context.context_version,
                    evidence_set_hash=context.evidence_set_hash,
                    input_hash=input_hash,
                    model=model_name,
                    result=result,
                    error_codes=[error],
                    retry_count=attempt,
                    input_tokens=response.get("input_tokens"),
                    output_tokens=response.get("output_tokens"),
                    reasoning_tokens=response.get("reasoning_tokens"),
                    latency_ms=int((monotonic() - started) * 1000),
                )

            try:
                result = ReasoningResult.parse_obj(
                    {
                        **response["parsed"],
                        "reasoning_result_id": f"finn-v2-reasoning-{uuid.uuid4().hex}",
                        "run_id": run_id,
                        "user_id": user_id,
                        "prompt_version": self.prompts.PROMPT_VERSION,
                        "reasoning_version": FINN_V2_REASONING_VERSION,
                        "model": response.get("model") or model_name,
                        "reasoning_provenance": self._reasoning_provenance(
                            response=response,
                            model=response.get("model") or model_name,
                            attempt=attempt,
                            validation_status="passed",
                        ),
                        "created_at": datetime.now(timezone.utc),
                    }
                )
                self._validate_refs(result, context)
            except (ValidationError, FinnV2ReasoningContractError) as exc:
                error = "schema_invalid"
                if isinstance(exc, FinnV2ReasoningContractError):
                    repair_validation_errors = [
                        {
                            "path": exc.path,
                            "code": exc.code,
                            "missing_scopes": ",".join(exc.missing_scopes),
                            "grounding_values": exc.grounding_values,
                        }
                    ]
                    # Semantic contract repairs need to see the rejected claim so
                    # they can replace it. Generic schema repairs stay sanitized.
                    repair_previous_response = response.get("parsed")
                else:
                    repair_validation_errors = self._validation_error_details(exc)
                    repair_previous_response = None
                error_details = self._reasoning_provenance(
                    response=response,
                    model=response.get("model") or model_name,
                    attempt=attempt,
                    validation_status="failed",
                    validation_errors=repair_validation_errors,
                )
                last_error_codes = [error]
                if attempt < retries_allowed:
                    await self._append_trace(
                        run_id,
                        user_id,
                        trace_id,
                        "reasoning_retry",
                        context,
                        model_name,
                        "generating",
                        None,
                        attempt + 1,
                        input_hash,
                        [error],
                        error_details=error_details,
                    )
                    increment_execution_safety_counter(f"finn_v2_reasoning_retries_total:{error}")
                    continue
                await self._append_trace(
                    run_id,
                    user_id,
                    trace_id,
                    "reasoning_failed",
                    context,
                    model_name,
                    "failed",
                    int((monotonic() - started) * 1000),
                    attempt,
                    input_hash,
                    [error],
                    error_details=error_details,
                )
                fallback = self._fallback_for_reasoning_error(
                    run_id=run_id,
                    user_id=user_id,
                    context=context,
                    model_name=model_name,
                    error_codes=[error],
                )
                fallback.reasoning_provenance = self._reasoning_provenance(
                    response=response,
                    model=model_name,
                    attempt=attempt,
                    validation_status="failed",
                    validation_errors=repair_validation_errors,
                    fallback_reason=error,
                )
                return await self._persist_record(
                    run_id=run_id,
                    user_id=user_id,
                    orchestrator_result_id=orchestrator_result.orchestrator_result_id,
                    policy_decision_id=policy.policy_decision_id,
                    snapshot_id=snapshot.id,
                    validation_id=validation.id,
                    status="failed",
                    mode=fallback.mode,
                    context_version=context.context_version,
                    evidence_set_hash=context.evidence_set_hash,
                    input_hash=input_hash,
                    model=model_name,
                    result=fallback,
                    error_codes=[error],
                    retry_count=attempt,
                    input_tokens=response.get("input_tokens"),
                    output_tokens=response.get("output_tokens"),
                    reasoning_tokens=response.get("reasoning_tokens"),
                    latency_ms=int((monotonic() - started) * 1000),
                )
            except Exception as exc:
                error = "invalid_evidence_refs" if "ref" in str(exc).lower() else "schema_invalid"
                error_details = {
                    "exception_class": type(exc).__name__,
                    "message": str(exc)[:500],
                }
                last_error_codes = [error]
                if attempt < retries_allowed and error == "schema_invalid":
                    await self._append_trace(
                        run_id,
                        user_id,
                        trace_id,
                        "reasoning_retry",
                        context,
                        model_name,
                        "generating",
                        None,
                        attempt + 1,
                        input_hash,
                        [error],
                        error_details=error_details,
                    )
                    increment_execution_safety_counter(f"finn_v2_reasoning_retries_total:{error}")
                    continue
                await self._append_trace(
                    run_id,
                    user_id,
                    trace_id,
                    "reasoning_failed",
                    context,
                    model_name,
                    "failed",
                    int((monotonic() - started) * 1000),
                    attempt,
                    input_hash,
                    [error],
                    error_details=error_details,
                )
                fallback = self._fallback_for_reasoning_error(
                    run_id=run_id,
                    user_id=user_id,
                    context=context,
                    model_name=model_name,
                    error_codes=[error],
                )
                return await self._persist_record(
                    run_id=run_id,
                    user_id=user_id,
                    orchestrator_result_id=orchestrator_result.orchestrator_result_id,
                    policy_decision_id=policy.policy_decision_id,
                    snapshot_id=snapshot.id,
                    validation_id=validation.id,
                    status="failed",
                    mode=fallback.mode,
                    context_version=context.context_version,
                    evidence_set_hash=context.evidence_set_hash,
                    input_hash=input_hash,
                    model=model_name,
                    result=fallback,
                    error_codes=[error],
                    retry_count=attempt,
                    input_tokens=response.get("input_tokens"),
                    output_tokens=response.get("output_tokens"),
                    reasoning_tokens=response.get("reasoning_tokens"),
                    latency_ms=int((monotonic() - started) * 1000),
                )

            await self._append_trace(
                run_id,
                user_id,
                trace_id,
                "reasoning_completed",
                context,
                result.model,
                "ready",
                int((monotonic() - started) * 1000),
                attempt,
                input_hash,
                [],
                error_details=response.get("provider_metadata"),
            )
            record_latency_sample("finn_v2_reasoning_latency_ms", int((monotonic() - started) * 1000))
            increment_execution_safety_counter(f"finn_v2_reasoning_runs_total:{result.mode}:ready:{result.model}")
            increment_execution_safety_counter(f"finn_v2_reasoning_tokens_total:input:{result.model}")
            return await self._persist_record(
                run_id=run_id,
                user_id=user_id,
                orchestrator_result_id=orchestrator_result.orchestrator_result_id,
                policy_decision_id=policy.policy_decision_id,
                snapshot_id=snapshot.id,
                validation_id=validation.id,
                status="ready",
                mode=result.mode,
                context_version=context.context_version,
                evidence_set_hash=context.evidence_set_hash,
                input_hash=input_hash,
                model=result.model,
                result=result,
                error_codes=[],
                retry_count=attempt,
                input_tokens=response.get("input_tokens"),
                output_tokens=response.get("output_tokens"),
                reasoning_tokens=response.get("reasoning_tokens"),
                latency_ms=int((monotonic() - started) * 1000),
            )
        raise ValueError(",".join(last_error_codes or ["reasoning_failed"]))

    async def _commit_before_provider_call(self) -> None:
        commit = getattr(self.session, "commit", None)
        if commit is not None:
            await commit()

    def _fallback_for_reasoning_error(
        self,
        *,
        run_id: str,
        user_id: int,
        context,
        model_name: str,
        error_codes: list[str],
    ) -> ReasoningResult:
        mode = normalize_interaction_mode(context.interaction_mode)
        if mode == "EVALUATE":
            return self.fallbacks.grounded_evaluation_draft(
                run_id=run_id,
                user_id=user_id,
                context=context,
                model=model_name,
                error_codes=error_codes,
            )
        if mode == "READ":
            return self.fallbacks.grounded_read_draft(
                run_id=run_id,
                user_id=user_id,
                context=context,
                model=model_name,
                error_codes=error_codes,
            )
        if mode in {"CREATE_PROPOSAL", "ACTION_PROPOSAL"}:
            if not context.policy.allowed and context.policy.operation_type == "activate_live_bot":
                return self.fallbacks.blocked_action_draft(
                    run_id=run_id,
                    user_id=user_id,
                    context=context,
                    model=model_name,
                    error_codes=error_codes,
                )
            return self.fallbacks.grounded_proposal_draft(
                run_id=run_id,
                user_id=user_id,
                context=context,
                model=model_name,
                error_codes=error_codes,
            )
        return self.fallbacks.unavailable_draft(
            run_id=run_id,
            user_id=user_id,
            mode=context.interaction_mode,
            error_codes=error_codes,
            model=model_name,
        )

    async def _persist_record(self, **kwargs):
        result = kwargs.pop("result", None)
        row = await self.reasoning.create(
            id=result.reasoning_result_id if result is not None else f"finn-v2-reasoning-{uuid.uuid4().hex}",
            run_id=kwargs["run_id"],
            user_id=kwargs["user_id"],
            orchestrator_result_id=kwargs["orchestrator_result_id"],
            policy_decision_id=kwargs["policy_decision_id"] or "finn-v2-policy-missing",
            snapshot_id=kwargs["snapshot_id"] or "finn-v2-snapshot-missing",
            validation_id=kwargs["validation_id"] or "finn-v2-validation-missing",
            status=kwargs["status"],
            mode=kwargs["mode"],
            context_version=kwargs["context_version"],
            evidence_set_hash=kwargs["evidence_set_hash"],
            input_hash=kwargs["input_hash"],
            prompt_version=self.prompts.PROMPT_VERSION,
            schema_version=FINN_V2_REASONING_SCHEMA_VERSION,
            reasoning_version=FINN_V2_REASONING_VERSION,
            model=kwargs["model"],
            result_json=to_json_safe(result.dict()) if result is not None else None,
            error_codes_json=kwargs.get("error_codes", []),
            input_tokens=kwargs.get("input_tokens"),
            output_tokens=kwargs.get("output_tokens"),
            reasoning_tokens=kwargs.get("reasoning_tokens"),
            latency_ms=kwargs.get("latency_ms"),
            retry_count=min(int(kwargs.get("retry_count", 0)), 1),
            completed_at=datetime.now(timezone.utc),
        )
        return PersistedReasoningRecord(
            reasoning_result_id=row.id,
            run_id=row.run_id,
            user_id=row.user_id,
            orchestrator_result_id=row.orchestrator_result_id,
            policy_decision_id=row.policy_decision_id,
            snapshot_id=row.snapshot_id,
            validation_id=row.validation_id,
            status=row.status,
            mode=row.mode,
            context_version=row.context_version,
            evidence_set_hash=row.evidence_set_hash,
            input_hash=row.input_hash,
            prompt_version=row.prompt_version,
            schema_version=row.schema_version,
            reasoning_version=row.reasoning_version,
            model=row.model,
            result=ReasoningResult.parse_obj(row.result_json) if row.result_json else None,
            error_codes=row.error_codes_json,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            reasoning_tokens=row.reasoning_tokens,
            latency_ms=row.latency_ms,
            retry_count=row.retry_count,
            created_at=row.created_at,
            completed_at=row.completed_at,
        )

    def _validate_refs(self, result: ReasoningResult, context) -> None:
        expected_mode = normalize_interaction_mode(context.interaction_mode)
        actual_mode = normalize_interaction_mode(result.mode)
        if actual_mode != expected_mode:
            raise FinnV2ReasoningContractError(
                code="reasoning_mode_mismatch",
                missing_scopes=[],
                path="mode",
                grounding_values={
                    "expected_mode": [expected_mode],
                    "actual_mode": [actual_mode],
                },
            )
        valid_refs = {item.evidence_id for item in context.evidence}
        referenced = set(result.evidence_refs_used)
        for claim in result.claims:
            if claim.claim_type in {"fact", "inference", "evaluation"} and not claim.evidence_refs:
                raise ValueError("invalid_evidence_refs")
            referenced.update(claim.evidence_refs)
        for point in result.supporting_points:
            referenced.update(point.evidence_refs)
        if result.proposal_candidate is not None:
            referenced.update(result.proposal_candidate.evidence_refs)
            if result.proposal_candidate.operation_type not in context.allowed_operation_types:
                raise ValueError("schema_invalid")
        if result.next_step and result.next_step.operation_type and context.allowed_operation_types and result.next_step.operation_type not in context.allowed_operation_types:
            raise ValueError("schema_invalid")
        if any(ref not in valid_refs for ref in referenced):
            raise ValueError("invalid_evidence_refs")
        self._validate_integrated_plan_contract(result=result, referenced=referenced, context=context)
        self._validate_configuration_causality(result=result, context=context)
        self._validate_indicator_configuration_inference(result=result, context=context)
        self._validate_stored_field_absence(result=result, context=context)
        self._validate_market_causality(result=result, context=context)

    @staticmethod
    def _validate_configuration_causality(*, result: ReasoningResult, context) -> None:
        """Reject causal conclusions that are unsupported by a configuration value alone."""
        bot_mode_values = {
            str((item.facts or {}).get("mode") or "").lower()
            for item in context.evidence
            if item.tool_name in {"read_linked_bot", "read_bot_status"}
        }
        bot_mode_values.discard("")
        if not bot_mode_values:
            return

        statements = [
            result.direct_answer or "",
            result.main_observation or "",
            *(claim.text for claim in result.claims),
            *(point.explanation for point in result.supporting_points),
            result.next_step.instruction if result.next_step is not None else "",
        ]
        mode_terms_by_value = {
            "manual": {"manual", "handmatig", "handmatige"},
            "automated": {"automated", "automatisch", "geautomatiseerd"},
        }
        mode_terms = set().union(*(mode_terms_by_value.get(value, {value}) for value in bot_mode_values))
        causal_terms = {
            "beperkt",
            "belemmer",
            "gemiste kans",
            "gemiste kansen",
            "leidt tot",
            "oorzaakt",
            "niet ideaal",
            "effectiviteit",
            "effectief",
            "ondermijnen",
            "ondermijnt",
            "verouderde botconfiguratie",
            "werkt niet",
            "mogelijk niet optimaal",
            "limit",
            "restrict",
            "missed opportunit",
            "causes",
            "prevents",
            "ineffective",
            "undermine",
        }
        bot_status_terms = {"stale", "verouderd", "outdated"}
        # Evidence-backed facts and unrelated uncertainty may coexist in a response.
        # Require the mode and causal language to occur in the same statement.
        if any(
            (
                any(term in statement.lower() for term in mode_terms)
                or any(term in statement.lower() for term in bot_status_terms)
            )
            and any(term in statement.lower() for term in causal_terms)
            for statement in statements
        ):
            raise FinnV2ReasoningContractError(
                code="unsupported_configuration_causality",
                missing_scopes=[],
                path="claims",
                grounding_values={"supported_bot_mode_facts": sorted(bot_mode_values)},
            )

    @staticmethod
    def _validate_indicator_configuration_inference(*, result: ReasoningResult, context) -> None:
        """Keep configured indicators factual unless the evidence proves a requirement or effect."""
        indicator_rows = [
            row
            for item in context.evidence
            if item.tool_name == "read_indicator_configuration"
            for row in (item.facts or {}).get("configured_indicators", [])
        ]
        if not indicator_rows:
            return

        statements = [
            result.direct_answer or "",
            result.main_observation or "",
            *(claim.text for claim in result.claims),
            *(point.explanation for point in result.supporting_points),
            result.next_step.instruction if result.next_step is not None else "",
        ]
        indicator_terms = {
            "indicatorconfiguratie",
            "indicator configuration",
            "indicatoren",
            "indicators",
        }
        unsupported_inference_terms = {
            "beperkte indicator",
            "onvoldoende indicator",
            "te weinig indicator",
            "niet genoeg indicator",
            "insufficient indicator",
            "limited indicator",
            "missing indicator",
            "ontbrekende indicator",
            "zonder macro",
            "without macro",
            "kan leiden tot",
            "leidt tot",
            "beperkt",
            "minder robuust",
            "less robust",
        }
        if any(
            any(term in statement.lower() for term in indicator_terms)
            and any(term in statement.lower() for term in unsupported_inference_terms)
            for statement in statements
        ):
            configured_indicators = sorted(
                {
                    str((row or {}).get("indicator"))
                    for row in indicator_rows
                    if (row or {}).get("indicator")
                }
            )
            raise FinnV2ReasoningContractError(
                code="unsupported_indicator_configuration_inference",
                missing_scopes=[],
                path="claims",
                grounding_values={"configured_indicators": configured_indicators},
            )

    @staticmethod
    def _validate_stored_field_absence(*, result: ReasoningResult, context) -> None:
        """Do not let narrative text erase a populated strategy field."""
        strategy_facts = [
            item.facts or {}
            for item in context.evidence
            if item.tool_name == "read_linked_strategy"
        ]
        populated_values = {
            field: facts[field]
            for facts in strategy_facts
            for field in ("entry", "stop_loss", "targets")
            if facts.get(field) not in (None, "", [], {})
        }
        if not populated_values:
            return
        populated_fields = set(populated_values)

        statements = [
            result.direct_answer or "",
            result.main_observation or "",
            *(claim.text for claim in result.claims),
            *(point.explanation for point in result.supporting_points),
            result.next_step.instruction if result.next_step is not None else "",
        ]
        field_terms = {
            "entry": {"entry", "instap", "instapniveau"},
            "stop_loss": {"stop-loss", "stop loss", "stoploss"},
            "targets": {"target", "targets", "doel", "doelen", "exit-niveau", "exit niveau", "exit levels"},
        }
        absence_terms = {"geen", "zonder", "ontbreekt", "ontbreken", "mist", "missing", "absent", "no "}
        unsupported = {
            field
            for statement in statements
            for field in populated_fields
            if any(term in statement.lower() for term in field_terms[field])
            and any(term in statement.lower() for term in absence_terms)
        }
        if unsupported:
            raise FinnV2ReasoningContractError(
                code="unsupported_stored_field_absence",
                missing_scopes=[],
                path="claims",
                grounding_values={
                    "populated_strategy_fields": sorted(unsupported),
                    # A repair must preserve the canonical values, not only their names.
                    "populated_strategy_values": {
                        field: populated_values[field]
                        for field in sorted(unsupported)
                    },
                },
            )

    @staticmethod
    def _validate_market_causality(*, result: ReasoningResult, context) -> None:
        """Require market measurements before judging a plan against current conditions."""
        text = " ".join(
            [
                result.direct_answer or "",
                result.main_observation or "",
                *(claim.text for claim in result.claims),
                *(point.explanation for point in result.supporting_points),
                result.next_step.instruction if result.next_step is not None else "",
            ]
        ).lower()
        market_condition_terms = {
            "huidige marktomstandigheden",
            "current market conditions",
            "marktvolatiliteit",
            "market volatility",
            "volatiliteit in de crypto",
            "given the volatility",
        }
        if not any(term in text for term in market_condition_terms):
            return

        measurement_keys = {
            "price",
            "current_price",
            "last_price",
            "close",
            "atr",
            "volatility",
            "volatiliteit",
            "change_24h",
            "market_regime",
        }
        has_market_measurement = any(
            any(key in (item.facts or {}) for key in measurement_keys)
            for item in context.evidence
        )
        if not has_market_measurement:
            raise FinnV2ReasoningContractError(
                code="unsupported_market_causality",
                missing_scopes=["market_measurement"],
                path="claims",
                grounding_values={"required_market_measurement_keys": sorted(measurement_keys)},
            )

    @classmethod
    def _validate_integrated_plan_contract(cls, *, result: ReasoningResult, referenced: set[str], context) -> None:
        request_plan = context.request_plan or {}
        required_scopes = set(request_plan.get("required_information_scopes") or [])
        legacy_scope_names = not bool(required_scopes)
        if not required_scopes:
            # Historical contexts created before the registry did not persist a
            # RequestPlan. Preserve their validation semantics without using
            # this branch for new runs.
            required_scopes = {"profile", "indicators", "setup", "strategy", "bot"}
        if context.interaction_mode != "EVALUATE":
            return
        scope_tools = {
            "profile": {"read_profile"}, "preferences": {"read_user_preferences"},
            "active_asset": {"read_active_asset"}, "indicator_configuration": {"read_indicator_configuration"},
            "market_snapshot": {"read_market_snapshot"}, "watchlist": {"read_watchlist"},
            "active_setup": {"read_active_setup"}, "linked_strategy": {"read_linked_strategy"},
            "linked_bot": {"read_linked_bot"}, "bot_status": {"read_bot_status"},
        }
        if legacy_scope_names:
            # Historical planless contexts only had a subject list. Preserve
            # their former integrated-plan guard instead of applying new
            # contract scopes to every isolated evaluation.
            if not required_scopes.issubset(set(context.subject_scopes)):
                return
            scope_tools = {
                "profile": {"read_profile", "read_user_preferences"},
                "indicators": {"read_indicator_configuration"},
                "setup": {"read_active_setup"},
                "strategy": {"read_linked_strategy"},
                "bot": {"read_linked_bot", "read_bot_status"},
            }
        missing_scopes = [
            scope
            for scope in required_scopes
            for tools in [scope_tools.get(scope, set())]
            if not any(item.evidence_id in referenced and item.tool_name in tools for item in context.evidence)
        ]
        if missing_scopes:
            raise FinnV2ReasoningContractError(
                code="missing_required_scope_refs",
                missing_scopes=missing_scopes,
            )

        if context.uncertainty_codes and not result.uncertainty_summary:
            raise FinnV2ReasoningContractError(
                code="missing_required_uncertainty",
                missing_scopes=[],
                path="uncertainty_summary",
            )

    def _validation_error_details(self, exc: ValidationError) -> list[dict[str, str]]:
        return [
            {
                "path": ".".join(str(item) for item in error.get("loc", ())),
                "code": str(error.get("type") or "validation_error"),
            }
            for error in exc.errors()
        ]

    def _reasoning_provenance(
        self,
        *,
        response: dict,
        model: str,
        attempt: int,
        validation_status: str,
        validation_errors: Optional[list[dict[str, str]]] = None,
        fallback_reason: Optional[str] = None,
    ) -> dict:
        metadata = response.get("provider_metadata") or {}
        return {
            "provider_called": True,
            "provider_status": metadata.get("response_status") or "unknown",
            "provider_response_id": metadata.get("response_id"),
            "model": model,
            "reasoning_source": "model_repair" if attempt else "model",
            "structured_output_source": metadata.get("parsed_source") or "unknown",
            "schema_version": FINN_V2_REASONING_SCHEMA_VERSION,
            "parse_status": "passed",
            "validation_status": validation_status,
            "validation_errors": validation_errors or [],
            "repair_attempted": attempt > 0,
            "repair_status": "passed" if attempt and validation_status == "passed" else ("failed" if attempt else "not_attempted"),
            "fallback_reason": fallback_reason,
        }

    async def _append_trace(self, run_id: str, user_id: int, trace_id: str, event_type: str, context, model: str, status: str, latency_ms: Optional[int], retry_count: int, input_hash: str, error_codes: list[str], error_details: Optional[dict] = None) -> None:
        await self.traces.append_event(
            run_id=run_id,
            user_id=user_id,
            trace_id=trace_id,
            event_type=event_type,
            payload_json={
                "run_id": run_id,
                "user_id": user_id,
                "mode": context.interaction_mode,
                "subject_scopes": context.subject_scopes,
                "required_domains": context.required_domains,
                "evidence_count": len(context.evidence),
                "context_bytes": self.contexts.context_bytes(context),
                "input_hash": input_hash,
                "prompt_version": self.prompts.PROMPT_VERSION,
                "model": model,
                "status": status,
                "latency_ms": latency_ms,
                "retry_count": retry_count,
                "input_tokens": None,
                "output_tokens": None,
                "reasoning_tokens": None,
                "error_codes": error_codes,
                "error_details": error_details or None,
            },
        )

    def _resolved_model(self) -> str:
        return self.flags.reasoning_model_override() or openai_client.get_openai_runtime_status().get("model") or "unknown"

    def _is_visible_run(self, run) -> bool:
        return getattr(run, "visibility", None) == "visible" or getattr(run, "feature_mode", None) in {"visible_runtime", "visible_readonly"}
