from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
import asyncio
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.finn_v2_contract import (
    TRACE_EVENT_BY_STATUS,
    build_placeholder_response,
    validate_run_transition,
)
from backend.infrastructure.repositories.finn_v2_conversation_repository import FinnV2ConversationRepository
from backend.infrastructure.repositories.finn_v2_run_repository import FinnV2RunRepository
from backend.infrastructure.repositories.finn_v2_trace_repository import FinnV2TraceRepository
from backend.services.finn_v2_delivery_service import FinnV2DeliveryService
from backend.services.finn_v2_orchestrator_service import FinnV2OrchestratorService
from backend.services.finn_v2_tool_execution_service import FinnV2ToolExecutionService
from backend.schemas.finn_v2_schema import AgentRunStatusEnvelope, PolicyDecision, VerifiedResponse


logger = logging.getLogger(__name__)


class FinnV2RunService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.conversations = FinnV2ConversationRepository(session)
        self.runs = FinnV2RunRepository(session)
        self.traces = FinnV2TraceRepository(session)
        self.tools = FinnV2ToolExecutionService(session)
        self.delivery = FinnV2DeliveryService(session)
        self.orchestrator = FinnV2OrchestratorService(session)

    async def create_run(self, payload: Dict[str, Any]):
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
        completed_at = now if next_status == "completed" else None
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

    async def complete_run(self, *, run_id: str, user_id: int, interaction_mode: Optional[str] = None):
        artifacts = await self.delivery.get_delivery_artifacts(user_id=user_id, run_id=run_id)
        verified = artifacts.get("verified_response") or {}
        policy = artifacts.get("policy_result") or PolicyDecision().dict()
        direct_answer = str(verified.get("direct_answer") or "").strip()
        main_observation = str(verified.get("main_observation") or "").strip()
        content = "\n\n".join([part for part in [direct_answer, main_observation] if part]).strip()
        if not content:
            placeholder = build_placeholder_response()
            response_json = {
                "mode": interaction_mode or "UNAVAILABLE",
                "content": placeholder.get("content") or "FINN V2 kon geen verified response afronden.",
                "response_source": "v2_runtime",
                "verifier_status": "failed",
                "evidence": [],
                "uncertainty": [str(artifacts.get("delivery_envelope", {}).get("status") or "delivery_unavailable")],
                "proposal_id": None,
                "confirmation_required": False,
                "reasoning_provenance": {},
            }
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
                "reasoning_provenance": verified.get("reasoning_provenance") or {},
            }
        await self.transition_run(
            run_id,
            user_id,
            next_status="completed",
            interaction_mode=response_json["mode"],
            policy_json=policy,
            response_json=response_json,
            response_source="v2_runtime",
        )

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
            await self.transition_run(
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
        await self.transition_run(
            run_id,
            user_id,
            next_status="canceled",
            response_source="foundation_placeholder",
        )

    async def run_foundation_lifecycle(self, *, run_id: str, user_id: int) -> None:
        await self.transition_run(run_id, user_id, next_status="collecting", response_source="foundation_placeholder")
        await self.transition_run(run_id, user_id, next_status="planned", response_source="foundation_placeholder")
        try:
            run = await self.runs.get_by_id_for_user(run_id=run_id, user_id=user_id)
            if run is None:
                raise LookupError("FINN V2 run not found")
            if self._is_visible_run(run) or self.tools.flags.should_run_block4_shadow(user_id):
                await self.orchestrator.execute_run(run_id=run_id, user_id=user_id, trace_id=run.trace_id)
                await self.complete_run(run_id=run_id, user_id=user_id)
            else:
                await self.tools.execute_shadow_tool_chain(run_id=run_id, user_id=user_id)
                await self.complete_run(run_id=run_id, user_id=user_id)
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

    def envelope_from_run(self, run) -> AgentRunStatusEnvelope:
        response = VerifiedResponse(**run.response_json) if run.response_json else None
        policy = PolicyDecision(**run.policy_json) if run.policy_json else None
        return AgentRunStatusEnvelope(
            run_id=run.id,
            conversation_id=run.conversation_id,
            status=run.status,
            mode=run.interaction_mode,
            visibility=run.visibility,
            response=response,
            policy=policy,
            created_at=run.created_at,
            updated_at=run.updated_at,
            completed_at=run.completed_at,
            error_code=run.error_code,
            error_message=run.error_message,
            retryable=bool(run.retryable),
        )

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
        transaction = self.session.get_transaction()
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
