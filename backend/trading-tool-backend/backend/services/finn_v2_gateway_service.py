from __future__ import annotations

import hashlib
import asyncio
import logging
import os
import uuid
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time, timezone
from time import monotonic
from typing import Any, Dict, Optional

from fastapi import HTTPException
from sqlalchemy.inspection import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import async_session_factory
from backend.infrastructure.repositories.finn_v2_conversation_repository import FinnV2ConversationRepository
from backend.infrastructure.repositories.finn_v2_run_repository import FinnV2RunRepository
from backend.infrastructure.repositories.finn_v2_dispatch_repository import FinnV2DispatchRepository
from backend.celery_task.queue_policy import resolve_task_queue
from backend.schemas.finn_v2_schema import AgentRunRequest
from backend.services.finn_v2_flag_service import FinnV2FlagService
from backend.services.finn_v2_request_analysis_service import FinnV2RequestAnalysisService
from backend.services.finn_v2_run_service import FinnV2RunService
from backend.utils.rate_limit import InMemoryRateLimiter


logger = logging.getLogger(__name__)
run_rate_limiter = InMemoryRateLimiter(requests_limit=20, window_seconds=60)

SECRET_FIELD_MARKERS = ("token", "cookie", "secret", "api_key", "apikey", "credential", "authorization", "csrf")


class FinnV2GatewayService:
    def __init__(self, session: AsyncSession, flag_service: Optional[FinnV2FlagService] = None):
        self.session = session
        self.flags = flag_service or FinnV2FlagService()
        self.conversations = FinnV2ConversationRepository(session)
        self.runs = FinnV2RunRepository(session)
        self.dispatches = FinnV2DispatchRepository(session)
        self.run_service = FinnV2RunService(session)
        self.analysis = FinnV2RequestAnalysisService()

    async def create_run(
        self,
        *,
        user_id: int,
        request: AgentRunRequest,
        request_path: str,
        request_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        feature_mode = self.flags.resolve_mode(user_id)
        if feature_mode == "disabled":
            raise HTTPException(status_code=503, detail="FINN V2 is disabled")
        if not self.flags.allows_transport(request.transport):
            raise HTTPException(status_code=400, detail="Unsupported FINN V2 transport")

        run_rate_limiter.check_rate_limit(
            f"user_{user_id}:finn_v2_runs",
            limit=max(self.flags.max_runs_per_minute(), 1),
        )

        conversation = await self._resolve_conversation(
            user_id=user_id,
            conversation_id=request.conversation_id,
            session_id=request.session_id or (request.client_context or {}).get("session_id"),
        )
        effective_request_id = request_id or f"finn-v2-req-{uuid.uuid4().hex}"
        effective_trace_id = trace_id or f"finn-v2-trace-{uuid.uuid4().hex}"
        effective_idempotency_key = self._resolve_idempotency_key(
            user_id=user_id,
            client_key=request.idempotency_key,
            request_id=effective_request_id,
        )

        existing = await self.runs.get_by_idempotency_key_for_user(
            idempotency_key=effective_idempotency_key,
            user_id=user_id,
        )
        if existing is not None:
            logger.info(
                "FINN V2 idempotency hit",
                extra={"user_id": user_id, "transport": request.transport, "idempotency_hit": True},
            )
            return existing

        redacted_workspace_hints = self._redact_hint_map(request.workspace_hints)
        redacted_client_context = self._redact_hint_map(request.client_context)
        redacted_client_context["_request_path"] = request_path
        run = await self.run_service.create_run(
            {
                "id": f"finn-v2-run-{uuid.uuid4().hex}",
                "conversation_id": conversation.id,
                "user_id": user_id,
                "request_id": effective_request_id,
                "trace_id": effective_trace_id,
                "idempotency_key": effective_idempotency_key,
                "transport": request.transport,
                "visibility": "shadow" if feature_mode == "shadow" else "visible",
                "feature_mode": feature_mode,
                "status": "created",
                "interaction_mode": None,
                "message": request.message,
                "workspace_hints_json": redacted_workspace_hints,
                "client_context_json": {
                    **redacted_client_context,
                    "_client_ip_hash": self._hash_optional_value(client_ip),
                    "_user_agent_hash": self._hash_optional_value(user_agent),
                },
                "policy_json": None,
                "response_json": None,
                "error_code": None,
                "error_message": None,
                "retryable": False,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            },
            commit=False,
        )
        if hasattr(self.session, "add"):
            await self.dispatches.create(
                dispatch_id=f"finn-v2-dispatch-{uuid.uuid4().hex}",
                run_id=run.id,
                task_id=f"finn-v2-task-{uuid.uuid4().hex}",
                queue=resolve_task_queue("backend.celery_task.finn_v2_task.process_finn_v2_run"),
                routing_rule="finn_v2.lifecycle",
                status="pending",
                attempt_count=0,
            )
        logger.info(
            "FINN V2 run created",
            extra={
                "run_id": run.id,
                "conversation_id": conversation.id,
                "user_id": user_id,
                "transport": request.transport,
                "message_length": len(request.message),
                "workspace_hint_keys": sorted(redacted_workspace_hints.keys()),
                "request_path": request_path,
                "idempotency_hit": False,
            },
        )
        return run

    async def get_run(self, *, run_id: str, user_id: int):
        run = await self.runs.get_by_id_for_user(run_id=run_id, user_id=user_id)
        if run is None:
            raise HTTPException(status_code=404, detail="FINN V2 run not found")
        return run

    async def enqueue_shadow_run(
        self,
        *,
        user_id: int,
        message: str,
        transport: str,
        request_path: str,
        request_id: str,
        trace_id: str,
        workspace_hints: Optional[Dict[str, Any]] = None,
        client_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        feature_mode = self.flags.resolve_mode(user_id)
        if feature_mode != "shadow":
            return False

        from backend.celery_task.finn_v2_task import process_shadow_foundation_run

        payload = {
            "message": message,
            "conversation_id": None,
            "workspace_hints": workspace_hints or {},
            "client_context": client_context or {},
            "idempotency_key": None,
            "transport": transport,
        }
        timeout = max(self.flags.shadow_enqueue_timeout_ms(), 1) / 1000.0
        try:
            await asyncio.wait_for(
                asyncio.to_thread(
                    process_shadow_foundation_run.delay,
                    user_id=user_id,
                    request_payload=payload,
                    request_path=request_path,
                    request_id=request_id,
                    trace_id=trace_id,
                ),
                timeout=timeout,
            )
            logger.info(
                "FINN V2 shadow enqueue success",
                extra={"user_id": user_id, "shadow_enqueue_success": True, "transport": transport},
            )
            return True
        except Exception as exc:
            logger.warning(
                "FINN V2 shadow enqueue failure",
                extra={
                    "user_id": user_id,
                    "shadow_enqueue_failure": True,
                    "transport": transport,
                    "request_path": request_path,
                    "error": str(exc),
                },
            )
            return False

    async def run_foundation_now(
        self,
        *,
        user_id: int,
        request_payload: Dict[str, Any],
        request_path: str,
        request_id: str,
        trace_id: str,
    ) -> str:
        request = AgentRunRequest(**request_payload)
        run = await self.create_run(
            user_id=user_id,
            request=request,
            request_path=request_path,
            request_id=request_id,
            trace_id=trace_id,
        )
        if run.status != "created":
            return run.id
        run_id = run.id
        await self.session.commit()
        if not hasattr(self.session, "add"):
            return run_id
        try:
            from backend.celery_task.finn_v2_task import process_finn_v2_run

            dispatch = await self.dispatches.get_for_run(run_id)
            publish_started = monotonic()
            # Celery's broker client is synchronous. It must never hold the
            # request event loop after the run and outbox record are durable.
            await asyncio.wait_for(
                asyncio.to_thread(
                    process_finn_v2_run.apply_async,
                    kwargs={"run_id": run_id},
                    task_id=dispatch.task_id,
                    queue=dispatch.queue,
                ),
                timeout=self.flags.direct_dispatch_timeout_ms() / 1000.0,
            )
            await self.dispatches.mark_published(dispatch.dispatch_id)
            await self.session.commit()
            logger.info(
                "FINN V2 dispatch published directly",
                extra={
                    "run_id": run_id,
                    "dispatch_id": dispatch.dispatch_id,
                    "queue": dispatch.queue,
                    "publish_latency_ms": int((monotonic() - publish_started) * 1000),
                },
            )
        except Exception as exc:
            # The committed pending outbox record is recovered by Celery beat;
            # never run lifecycle work in this request process.
            rollback = getattr(self.session, "rollback", None)
            if rollback is not None:
                await rollback()
            logger.warning(
                "FINN V2 dispatch enqueue deferred to recovery",
                extra={
                    "run_id": run_id,
                    "dispatch_error_class": type(exc).__name__,
                    "dispatch_error": str(exc),
                },
            )
        return run_id

    async def apply_retention_now(self) -> Dict[str, int]:
        return await self.run_service.apply_retention(
            message_days=self.flags.message_retention_days(),
            trace_days=self.flags.trace_retention_days(),
        )

    async def _resolve_conversation(
        self,
        *,
        user_id: int,
        conversation_id: Optional[str],
        session_id: Optional[str] = None,
    ):
        if conversation_id:
            conversation = await self.conversations.get_by_id_for_user(conversation_id, user_id)
            if conversation is None:
                raise HTTPException(status_code=404, detail="FINN V2 conversation not found")
            return conversation
        normalized_session_id = str(session_id or "").strip()
        # "new" is the legacy pre-session placeholder, not a stable session key.
        if normalized_session_id and normalized_session_id.casefold() != "new":
            conversation = await self.conversations.get_by_id_for_user(normalized_session_id, user_id)
            if conversation is not None:
                return conversation
            conversation = await self.conversations.get_by_session_id_for_user(normalized_session_id, user_id)
            if conversation is not None:
                return conversation
        create_kwargs = {
            "conversation_id": f"finn-v2-conv-{uuid.uuid4().hex}",
            "user_id": user_id,
            "title": "FINN Core V2 shadow conversation",
        }
        if normalized_session_id and normalized_session_id.casefold() != "new":
            create_kwargs["context"] = {"session_id": normalized_session_id}
        return await self.conversations.create(**create_kwargs)

    def _resolve_idempotency_key(self, *, user_id: int, client_key: Optional[str], request_id: str) -> str:
        if client_key:
            return client_key
        digest = hashlib.sha256(f"{user_id}:{request_id}".encode("utf-8")).hexdigest()
        return f"finn-v2-{digest[:32]}"

    def _predict_interaction_mode(self, request: AgentRunRequest) -> Optional[str]:
        try:
            analysis = self.analysis.analyze(
                message=request.message,
                workspace_hints=request.workspace_hints,
                client_context=request.client_context,
            )
        except Exception:
            logger.exception("FINN V2 could not predict interaction mode for visible timeout budget")
            return None
        return getattr(analysis, "interaction_mode", None)

    def _redact_hint_map(self, payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        source = dict(payload or {})
        redacted: Dict[str, Any] = {}
        for key, value in source.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in SECRET_FIELD_MARKERS):
                redacted[key] = "[redacted]"
                continue
            redacted[key] = self._json_safe(value)
        return redacted

    def _hash_optional_value(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        salt = os.getenv("JWT_SECRET_KEY")
        if not salt or len(salt) < 32:
            return None
        return hashlib.sha256(f"{salt}:{value}".encode("utf-8")).hexdigest()

    def _json_safe(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._json_safe(item) for item in value]
        if is_dataclass(value):
            return self._json_safe(asdict(value))
        if hasattr(value, "model_dump"):
            return self._json_safe(value.model_dump(by_alias=True))
        if hasattr(value, "dict"):
            return self._json_safe(value.dict())
        try:
            mapper = sa_inspect(value)
        except Exception:
            mapper = None
        if mapper is not None and getattr(mapper, "mapper", None) is not None:
            return {
                attr.key: self._json_safe(getattr(value, attr.key))
                for attr in mapper.mapper.column_attrs
            }
        if hasattr(value, "__dict__"):
            return {
                str(key): self._json_safe(item)
                for key, item in vars(value).items()
                if not str(key).startswith("_")
            }
        return str(value)


async def run_shadow_foundation_job(
    *,
    user_id: int,
    request_payload: Dict[str, Any],
    request_path: str,
    request_id: str,
    trace_id: str,
) -> str:
    async with async_session_factory() as session:
        service = FinnV2GatewayService(session)
        run_id = await service.run_foundation_now(
            user_id=user_id,
            request_payload=request_payload,
            request_path=request_path,
            request_id=request_id,
            trace_id=trace_id,
        )
        await session.commit()
        return run_id


async def run_foundation_lifecycle_owned_job(*, run_id: str, user_id: int) -> None:
    try:
        await FinnV2RunService.run_foundation_lifecycle_owned(run_id=run_id, user_id=user_id)
    except asyncio.CancelledError:
        logger.warning(
            "FINN V2 owned lifecycle task canceled; persisting terminal canceled state",
            extra={"run_id": run_id, "user_id": user_id},
        )
        try:
            async with async_session_factory() as session:
                service = FinnV2RunService(session)
                await service.cancel_run(run_id=run_id, user_id=user_id)
                await session.commit()
        except Exception:
            logger.exception(
                "FINN V2 owned lifecycle cancel cleanup failed",
                extra={"run_id": run_id, "user_id": user_id, "failure_stage": "lifecycle_cancel_cleanup"},
            )
        raise
    except Exception as exc:
        logger.exception(
            "FINN V2 owned lifecycle task failed",
            extra={"run_id": run_id, "user_id": user_id, "failure_stage": "lifecycle_owner"},
        )
        try:
            async with async_session_factory() as session:
                service = FinnV2RunService(session)
                await service.fail_run(
                    run_id=run_id,
                    user_id=user_id,
                    error_code="lifecycle_owner_failed",
                    error_message=str(exc),
                    retryable=False,
                )
                await session.commit()
        except Exception:
            logger.exception(
                "FINN V2 owned lifecycle failure cleanup failed",
                extra={"run_id": run_id, "user_id": user_id, "failure_stage": "lifecycle_owner_cleanup"},
            )


async def run_retention_cleanup_job() -> Dict[str, int]:
    async with async_session_factory() as session:
        service = FinnV2GatewayService(session)
        result = await service.apply_retention_now()
        await session.commit()
        return result
