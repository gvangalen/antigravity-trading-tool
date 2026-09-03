from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
import asyncio
from types import SimpleNamespace
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.finn_v2_contract import (
    FinnV2ModeContractError,
    TRACE_EVENT_BY_STATUS,
    build_placeholder_response,
    is_terminal_status,
    normalize_interaction_mode,
    validate_run_transition,
)
from backend.domain.finn_v2_runtime_contract import build_terminal_runtime_contract
from backend.infrastructure.repositories.finn_v2_conversation_repository import FinnV2ConversationRepository
from backend.infrastructure.repositories.finn_v2_run_repository import FinnV2RunRepository
from backend.infrastructure.repositories.finn_v2_trace_repository import FinnV2TraceRepository
from backend.infrastructure.database import async_session_factory
from backend.services.finn_v2_delivery_service import FinnV2DeliveryService
from backend.services.finn_v2_orchestrator_service import FinnV2OrchestratorService
from backend.services.finn_v2_tool_execution_service import FinnV2ToolExecutionService
from backend.schemas.finn_v2_schema import AgentRunStatusEnvelope, PolicyDecision, VerifiedResponse
from backend.schemas.finn_v2_orchestrator_schema import LifecyclePhaseOutcome


logger = logging.getLogger(__name__)


class FinnV2RunService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.conversations = FinnV2ConversationRepository(session)
        self.runs = FinnV2RunRepository(session)
        self.traces = FinnV2TraceRepository(session)
        self.tools = FinnV2ToolExecutionService(session)
        self.delivery = FinnV2DeliveryService(session)
        self.orchestrator = FinnV2OrchestratorService(session, phase_transition=self.persist_transition)

    async def create_run(self, payload: Dict[str, Any], *, commit: bool = True):
        try:
            run = await self.runs.create(**payload)
            await self.conversations.set_last_run(
                conversation_id=run.conversation_id,
                user_id=run.user_id,
                run_id=run.id,
            )
            await self.traces.append_event(
                run_id=run.id,
                user_id=run.user_id,
                trace_id=run.trace_id,
                event_type="run_created",
                payload_json=self._trace_payload(run, status="created", response_source=None),
            )
            if commit:
                await self.runs._commit_with_rollback(
                    operation="create_run",
                    entity_type="FinnV2Run",
                    run_id=run.id,
                )
        except Exception:
            raise
        return run

    async def transition_run(
        self,
        run_id: str,
        user_id: int,
        *,
        next_status: str,
        interaction_mode: Optional[str] = None,
        policy_json: Optional[dict] = None,
        response_json: Optional[dict] = None,
        response_source: Optional[str] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        retryable: bool = False,
    ):
        run = await self.runs.get_by_id_for_user(run_id=run_id, user_id=user_id)
        if run is None:
            raise LookupError("FINN V2 run not found")

        validate_run_transition(run.status, next_status)
        now = datetime.now(timezone.utc)
        completed_at = now if is_terminal_status(next_status) and next_status != "canceled" else None
        canceled_at = now if next_status == "canceled" else None
        async with self.session.begin_nested():
            await self.runs.update_status(
                run=run,
                status=next_status,
                interaction_mode=interaction_mode,
                policy_json=policy_json,
                response_json=response_json,
                error_code=error_code,
                error_message=error_message,
                retryable=retryable,
                completed_at=completed_at,
                canceled_at=canceled_at,
            )
            await self.traces.append_event(
                run_id=run.id,
                user_id=run.user_id,
                trace_id=run.trace_id,
                event_type=TRACE_EVENT_BY_STATUS[next_status],
                payload_json=self._trace_payload(run, status=next_status, response_source=response_source),
            )
        return run

    async def persist_transition(
        self,
        run_id: str,
        user_id: int,
        *,
        next_status: str,
        interaction_mode: Optional[str] = None,
        policy_json: Optional[dict] = None,
        response_json: Optional[dict] = None,
        response_source: Optional[str] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        retryable: bool = False,
    ):
        run = await self.transition_run(
            run_id,
            user_id,
            next_status=next_status,
            interaction_mode=interaction_mode,
            policy_json=policy_json,
            response_json=response_json,
            response_source=response_source,
            error_code=error_code,
            error_message=error_message,
            retryable=retryable,
        )
        await self._commit_session_if_possible()
        return run

    async def complete_run(
        self,
        *,
        run_id: str,
        user_id: int,
        phase_outcome: LifecyclePhaseOutcome,
    ):
        artifacts = await self.delivery.get_delivery_artifacts(user_id=user_id, run_id=run_id)
        verified = artifacts.get("verified_response") or {}
        orchestrator = artifacts.get("orchestrator_result") or {}
        verifier = artifacts.get("verifier_result") or {}
        reasoning = artifacts.get("reasoning_result") or {}
        policy = artifacts.get("policy_result") or PolicyDecision().dict()
        direct_answer = str(verified.get("direct_answer") or "").strip()
        main_observation = str(verified.get("main_observation") or "").strip()
        content = "\n\n".join([part for part in [direct_answer, main_observation] if part]).strip()
        next_status = phase_outcome.terminal_status
        if next_status not in {"clarification_required", "unavailable", "downgraded", "rejected", "completed", "failed"}:
            raise ValueError("invalid_lifecycle_phase_outcome")
        if not content:
            response_json = self._terminal_placeholder_response(
                interaction_mode=phase_outcome.interaction_mode,
                terminal_status=next_status,
                orchestrator=orchestrator,
                verifier=verifier,
                reasoning=reasoning,
                delivery_envelope=artifacts.get("delivery_envelope") or {},
            )
        else:
            response_json = {
                "mode": verified.get("mode") or interaction_mode or "UNAVAILABLE",
                "content": content,
                "response_source": "v2_runtime",
                "verifier_status": verified.get("verifier_status") or "passed",
                "evidence": [],
                "uncertainty": verified.get("uncertainty_codes") or [],
                "proposal_id": verified.get("proposal_id"),
                "confirmation_required": bool(verified.get("confirmation_required")),
                "next_step": verified.get("next_step"),
                "reasoning_provenance": verified.get("reasoning_provenance") or {},
            }
        runtime_contract = build_terminal_runtime_contract(
            run=SimpleNamespace(id=run_id, user_id=user_id, conversation_id=None, trace_id=None),
            artifacts=artifacts,
            terminal_status=next_status,
            final_mode=phase_outcome.interaction_mode or response_json["mode"],
            terminal_response_type=(
                "clarification" if next_status == "clarification_required"
                else "safe_terminal" if next_status in {"unavailable", "downgraded", "rejected"}
                else "verified_response"
            ),
        )
        response_json["_runtime_contract"] = runtime_contract.dict()
        response_json["_runtime_trace"] = self._terminal_runtime_trace(
            artifacts,
            runtime_contract=runtime_contract.public_projection(),
            projection_hash=runtime_contract.public_projection_hash,
        )
        await self.persist_transition(
            run_id,
            user_id,
            next_status=next_status,
            interaction_mode=phase_outcome.interaction_mode or response_json["mode"],
            policy_json=policy,
            response_json=response_json,
            response_source="v2_runtime",
        )

    def _terminal_placeholder_response(
        self,
        *,
        interaction_mode: Optional[str],
        terminal_status: str,
        orchestrator: Dict[str, Any],
        verifier: Dict[str, Any],
        reasoning: Dict[str, Any],
        delivery_envelope: Dict[str, Any],
    ) -> Dict[str, Any]:
        placeholder = build_placeholder_response()
        reasoning_result = reasoning.get("result") or {}
        reason_codes = list(verifier.get("reason_codes") or [])
        content = placeholder.get("content") or "FINN V2 kon geen verified response afronden."
        mode = interaction_mode or "UNAVAILABLE"
        verifier_status = "not_run"
        if terminal_status == "clarification_required":
            clarification = orchestrator.get("selected_clarification") or {}
            content = str(clarification.get("question") or "FINN heeft eerst een verduidelijking nodig.").strip()
            mode = "CLARIFICATION"
        elif terminal_status == "rejected":
            content = "FINN heeft de response veilig afgewezen omdat de verificatie faalde."
            mode = "UNAVAILABLE"
            verifier_status = "failed"
        elif terminal_status == "unavailable":
            content = "FINN kon geen betrouwbare response afronden met de beschikbare of geldige context."
            mode = "UNAVAILABLE"
        elif terminal_status == "downgraded":
            verifier_status = "downgraded"
        return {
            "mode": mode,
            "content": content,
            "response_source": "v2_runtime",
            "verifier_status": verifier_status,
            "evidence": [],
            "uncertainty": reason_codes or [str(delivery_envelope.get("status") or terminal_status)],
            "proposal_id": None,
            "confirmation_required": False,
            "next_step": None,
            "reasoning_provenance": reasoning_result.get("reasoning_provenance") or {},
        }

    async def fail_run(
        self,
        *,
        run_id: str,
        user_id: int,
        error_code: str,
        error_message: str,
        retryable: bool = False,
        failure_stage: str = "run_failure",
        primary_exception: Optional[Exception] = None,
    ) -> None:
        if primary_exception is not None or self._session_requires_rollback():
            await self._rollback_failed_session(
                run_id=run_id,
                user_id=user_id,
                failure_stage=failure_stage,
                primary_exception=primary_exception,
            )
        try:
            await self.persist_transition(
                run_id,
                user_id,
                next_status="failed",
                error_code=error_code,
                error_message=error_message,
                retryable=retryable,
                response_source="foundation_placeholder",
            )
        except Exception as cleanup_exc:
            logger.exception(
                "FINN V2 fail_run cleanup failure",
                extra={
                    "run_id": run_id,
                    "user_id": user_id,
                    "failure_stage": failure_stage,
                    "service": "FinnV2RunService",
                    "method": "fail_run",
                    "primary_exception_class": primary_exception.__class__.__name__ if primary_exception else None,
                    "primary_exception_message": str(primary_exception) if primary_exception else None,
                    "cleanup_exception_class": cleanup_exc.__class__.__name__,
                    "cleanup_exception_message": str(cleanup_exc),
                },
            )
            raise

    async def cancel_run(self, *, run_id: str, user_id: int):
        run = await self.runs.get_by_id_for_user(run_id=run_id, user_id=user_id)
        if run is None:
            raise LookupError("FINN V2 run not found")
        await self.persist_transition(
            run_id,
            user_id,
            next_status="canceled",
            response_source="foundation_placeholder",
        )

    async def run_foundation_lifecycle(self, *, run_id: str, user_id: int) -> None:
        await self.persist_transition(run_id, user_id, next_status="queued", response_source="foundation_placeholder")
        await self.persist_transition(run_id, user_id, next_status="collecting", response_source="foundation_placeholder")
        await self.persist_transition(run_id, user_id, next_status="planned", response_source="foundation_placeholder")
        try:
            run = await self.runs.get_by_id_for_user(run_id=run_id, user_id=user_id)
            if run is None:
                raise LookupError("FINN V2 run not found")
            if self._is_visible_run(run) or self.tools.flags.should_run_block4_shadow(user_id):
                await self.orchestrator.execute_run(run_id=run_id, user_id=user_id, trace_id=run.trace_id)
                await self.complete_run(
                    run_id=run_id,
                    user_id=user_id,
                    phase_outcome=self.orchestrator.consume_phase_outcome(),
                )
            else:
                await self.tools.execute_shadow_tool_chain(run_id=run_id, user_id=user_id)
                await self.complete_run(
                    run_id=run_id,
                    user_id=user_id,
                    phase_outcome=LifecyclePhaseOutcome(
                        terminal_status="completed",
                        interaction_mode="UNAVAILABLE",
                        orchestrator_result_id="shadow-foundation",
                    ),
                )
        except asyncio.CancelledError:
            logger.warning(
                "FINN V2 lifecycle canceled before terminal persistence",
                extra={"run_id": run_id, "user_id": user_id},
            )
            raise
        except Exception as exc:
            logger.exception(
                "FINN V2 lifecycle primary failure",
                extra={
                    "run_id": run_id,
                    "user_id": user_id,
                    "failure_stage": "run_foundation_lifecycle",
                    "service": "FinnV2RunService",
                    "method": "run_foundation_lifecycle",
                    "primary_exception_class": exc.__class__.__name__,
                    "primary_exception_message": str(exc),
                },
            )
            await self.fail_run(
                run_id=run_id,
                user_id=user_id,
                error_code="orchestrator_failed",
                error_message=str(exc),
                retryable=False,
                failure_stage="run_foundation_lifecycle",
                primary_exception=exc,
            )

    @classmethod
    async def run_foundation_lifecycle_owned(cls, *, run_id: str, user_id: int) -> None:
        """Run each lifecycle boundary in a fresh database unit of work.

        The coordinator only exchanges immutable ids and a typed phase outcome
        between sessions. ORM instances must never survive a rollback boundary.
        """
        try:
            for status in ("queued", "collecting", "planned"):
                async with async_session_factory() as session:
                    await cls(session).persist_transition(
                        run_id,
                        user_id,
                        next_status=status,
                        response_source="foundation_placeholder",
                    )

            async with async_session_factory() as session:
                service = cls(session)
                run = await service.runs.get_by_id_for_user(run_id=run_id, user_id=user_id)
                if run is None:
                    raise LookupError("FINN V2 run not found")
                trace_id = run.trace_id
                visible = service._is_visible_run(run)

                async def transition_phase(**kwargs) -> None:
                    async with async_session_factory() as transition_session:
                        await cls(transition_session).persist_transition(**kwargs)

                if visible or service.tools.flags.should_run_block4_shadow(user_id):
                    orchestrator = FinnV2OrchestratorService(session, phase_transition=transition_phase)
                    await orchestrator.execute_run(run_id=run_id, user_id=user_id, trace_id=trace_id)
                    phase_outcome = orchestrator.consume_phase_outcome()
                else:
                    await service.tools.execute_shadow_tool_chain(run_id=run_id, user_id=user_id)
                    phase_outcome = LifecyclePhaseOutcome(
                        terminal_status="completed",
                        interaction_mode="UNAVAILABLE",
                        orchestrator_result_id="shadow-foundation",
                    )

            async with async_session_factory() as session:
                await cls(session).complete_run(
                    run_id=run_id,
                    user_id=user_id,
                    phase_outcome=phase_outcome,
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception(
                "FINN V2 owned lifecycle primary failure",
                extra={"run_id": run_id, "user_id": user_id, "primary_exception": str(exc)},
            )
            async with async_session_factory() as session:
                await cls(session).fail_run(
                    run_id=run_id,
                    user_id=user_id,
                    error_code="orchestrator_failed",
                    error_message=str(exc),
                    retryable=False,
                    failure_stage="run_foundation_lifecycle_owned",
                    primary_exception=exc,
                )

    def _is_visible_run(self, run) -> bool:
        return getattr(run, "visibility", None) == "visible" or getattr(run, "feature_mode", None) == "visible_readonly"

    async def apply_retention(self, *, message_days: int, trace_days: int) -> Dict[str, int]:
        now = datetime.now(timezone.utc)
        message_cutoff = now - timedelta(days=message_days)
        trace_cutoff = now - timedelta(days=trace_days)
        redacted = await self.runs.redact_messages_older_than(message_cutoff)
        deleted = await self.runs.delete_traces_older_than(trace_cutoff)
        tool_retention = await self.tools.apply_retention()
        logger.info(
            "FINN V2 retention cleanup completed.",
            extra={"message_redacted": redacted, "traces_deleted": deleted, **tool_retention},
        )
        return {"messages_redacted": redacted, "traces_deleted": deleted, **tool_retention}

    async def envelope_from_run(self, run) -> AgentRunStatusEnvelope:
        response_payload = dict(run.response_json or {})
        # Terminal delivery metadata is projected once when the run completes.
        # Polling and SSE can then serve the same envelope without reopening the
        # full verifier/evidence chain for every client poll.
        runtime_trace: Dict[str, Any] = dict(response_payload.pop("_runtime_trace", {}) or {})
        try:
            if response_payload:
                response_payload["mode"] = normalize_interaction_mode(response_payload.get("mode"))
            envelope_mode = normalize_interaction_mode(run.interaction_mode) if run.interaction_mode else None
        except FinnV2ModeContractError as exc:
            runtime_trace["mode_contract_error"] = {"code": exc.code, "mode": exc.mode}
            response_payload = {
                "mode": "UNAVAILABLE",
                "content": "Deze FINN-run bevat een incompatibel historisch responsecontract.",
                "response_source": "v2_runtime",
                "verifier_status": "failed",
                "evidence": [],
                "uncertainty": [exc.code],
                "proposal_id": None,
                "confirmation_required": False,
            }
            envelope_mode = "UNAVAILABLE"
        else:
            if is_terminal_status(run.status) and not runtime_trace:
                # Historical runs predate the compact terminal projection. Keep
                # them readable without turning high-frequency polling into a
                # fan-out of artifact queries.
                runtime_trace = {
                    "delivery": {"status": run.status, "response_source": "v2_runtime"},
                    "policy": {"allowed": (run.policy_json or {}).get("allowed")},
                    "terminal_projection": "legacy_compact",
                }
        response = VerifiedResponse(**response_payload) if response_payload else None
        policy = PolicyDecision(**run.policy_json) if run.policy_json else None
        return AgentRunStatusEnvelope(
            run_id=run.id,
            conversation_id=run.conversation_id,
            status=run.status,
            mode=envelope_mode,
            visibility=run.visibility,
            response=response,
            policy=policy,
            created_at=run.created_at,
            updated_at=run.updated_at,
            completed_at=run.completed_at,
            error_code=run.error_code or runtime_trace.get("mode_contract_error", {}).get("code"),
            error_message=run.error_message or ("FINN V2 mode contract is invalid." if runtime_trace.get("mode_contract_error") else None),
            retryable=bool(run.retryable),
            runtime_trace=runtime_trace,
        )

    def _terminal_runtime_trace(
        self,
        artifacts: Dict[str, Any],
        *,
        runtime_contract: Optional[Dict[str, Any]] = None,
        projection_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Project persisted records for polling/SSE without exposing evidence data."""
        orchestrator = artifacts.get("orchestrator_result") or {}
        reasoning = artifacts.get("reasoning_result") or {}
        reasoning_result = reasoning.get("result") or {}
        verifier = artifacts.get("verifier_result") or {}
        validation = artifacts.get("validation_result") or {}
        verified = artifacts.get("verified_response") or {}
        delivery = artifacts.get("delivery_envelope") or {}
        policy = artifacts.get("policy_result") or {}
        request_plan = dict(orchestrator.get("tool_plan") or {}).get("request_plan") or {}
        reasoning_provenance = dict(reasoning_result.get("reasoning_provenance") or {})
        reasoning_provenance.setdefault("operation_id", request_plan.get("operation_id"))
        projection = dict(runtime_contract or {})
        contract = projection or {
            "initial_operation_id": request_plan.get("initial_operation_id") or request_plan.get("operation_id"),
            "final_operation_id": request_plan.get("operation_id"),
            "operation_change_reason": request_plan.get("operation_change_reason"),
            "target_source": request_plan.get("target_asset_source"),
            "conversation_reference": request_plan.get("conversation_reference"),
        }
        return {
            "contract": {
                "initial_operation_id": contract.get("initial_operation_id"),
                "final_operation_id": contract.get("final_operation_id"),
                "operation_change_reason": contract.get("operation_change_reason"),
                "target_asset_source": contract.get("target_source") or request_plan.get("target_asset_source"),
                "conversation_reference": contract.get("conversation_reference"),
            },
            "terminal_projection": projection or None,
            "terminal_projection_hash": projection_hash,
            "requested_mode": orchestrator.get("interaction_mode"),
            "delivery": {
                "status": delivery.get("status"),
                "verified_response_id": verified.get("verified_response_id"),
                "response_source": "v2_runtime",
            },
            "orchestrator": {
                "orchestrator_result_id": orchestrator.get("orchestrator_result_id"),
                "required_domains": orchestrator.get("required_domains") or [],
                "optional_domains": orchestrator.get("optional_domains") or [],
                "outcome": orchestrator.get("outcome"),
                "snapshot_id": orchestrator.get("snapshot_id"),
                "validation_id": orchestrator.get("validation_id"),
            },
            "policy": {
                "allowed": policy.get("allowed"),
                "policy_class": policy.get("policy_class"),
            },
            "validation": {
                "integrity_status": validation.get("integrity_status"),
                "validation_id": validation.get("validation_id"),
            },
            "reasoning": {
                "reasoning_result_id": reasoning.get("reasoning_result_id"),
                "status": reasoning.get("status"),
                "mode": reasoning.get("mode"),
                "model": reasoning.get("model"),
                "latency_ms": reasoning.get("latency_ms"),
                "error_codes": reasoning.get("error_codes") or [],
                "provenance": reasoning_provenance,
            },
            "verifier": {
                "verifier_result_id": verifier.get("verifier_result_id"),
                "passed": verifier.get("passed"),
                "action": verifier.get("action"),
                "reason_codes": verifier.get("reason_codes") or [],
                "coverage": verifier.get("coverage") or {},
            },
            "tool_calls": artifacts.get("tool_calls") or [],
            "evidence_references": artifacts.get("evidence_references") or [],
        }

    def _trace_payload(self, run, *, status: str, response_source: Optional[str]) -> Dict[str, Any]:
        return {
            "run_id": run.id,
            "conversation_id": run.conversation_id,
            "user_id": run.user_id,
            "transport": run.transport,
            "visibility": run.visibility,
            "feature_mode": run.feature_mode,
            "status": status,
            "request_path": getattr(run, "request_path", None) or (run.client_context_json or {}).get("_request_path"),
            "trace_id": run.trace_id,
            "response_source": response_source,
        }

    def _session_requires_rollback(self) -> bool:
        sync_session = getattr(self.session, "sync_session", None)
        if sync_session is not None and getattr(sync_session, "is_active", True) is False:
            return True
        try:
            transaction = self.session.get_transaction()
        except NotImplementedError:
            transaction = getattr(sync_session, "get_transaction", lambda: None)()
        return bool(transaction is not None and getattr(transaction, "is_active", True) is False)

    async def _rollback_failed_session(
        self,
        *,
        run_id: str,
        user_id: int,
        failure_stage: str,
        primary_exception: Optional[Exception],
    ) -> None:
        try:
            await self.session.rollback()
        except Exception as cleanup_exc:
            logger.exception(
                "FINN V2 rollback before fail_run failed",
                extra={
                    "run_id": run_id,
                    "user_id": user_id,
                    "failure_stage": failure_stage,
                    "service": "FinnV2RunService",
                    "method": "_rollback_failed_session",
                    "primary_exception_class": primary_exception.__class__.__name__ if primary_exception else None,
                    "primary_exception_message": str(primary_exception) if primary_exception else None,
                    "cleanup_exception_class": cleanup_exc.__class__.__name__,
                    "cleanup_exception_message": str(cleanup_exc),
                },
            )
            raise

    async def _commit_session_if_possible(self) -> None:
        commit = getattr(self.session, "commit", None)
        if commit is not None:
            await commit()
