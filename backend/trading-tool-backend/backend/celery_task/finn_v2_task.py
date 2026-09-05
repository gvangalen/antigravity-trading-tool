from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Dict

from celery import shared_task
from sqlalchemy import select

from backend.services.finn_v2_gateway_service import (
    run_retention_cleanup_job,
    run_shadow_foundation_job,
)
from backend.infrastructure.database import async_session_factory
from backend.infrastructure.database import engine
from backend.infrastructure.repositories.finn_v2_dispatch_repository import FinnV2DispatchRepository
from backend.infrastructure.repositories.finn_v2_run_repository import FinnV2RunRepository
from backend.infrastructure.models import FinnV2Run
from backend.domain.finn_v2_contract import is_terminal_status
from backend.services.finn_v2_run_service import FinnV2RunService
from backend.celery_task.queue_policy import resolve_task_queue


logger = logging.getLogger(__name__)

DISPATCH_LEASE_SECONDS = 300
DISPATCH_HEARTBEAT_SECONDS = 60
# An interactive FINN request must not wait minutes behind an unavailable
# worker. Recovery is scheduled independently every five seconds.
DISPATCH_STALE_UNCLAIMED_SECONDS = 8
RECOVERY_RESERVATION_SECONDS = 60


async def _run_task_with_local_resources(coroutine):
    """Keep every asyncpg transport inside the Celery task's own event loop."""
    try:
        return await coroutine
    finally:
        # ``asyncio.run`` closes its loop immediately after this coroutine.
        # Closing the async engine beforehand prevents pooled SSL transports
        # from being finalized later against that closed loop.
        await engine.dispose()


def _run_async(coroutine):
    """Run one Celery task with a fresh loop and task-local async resources."""
    # ``worker_process_init`` clears inherited pools once per prefork child.
    # Repeating a synchronous pool disposal immediately before every task can
    # delay the worker's first dispatch claim long enough for recovery to
    # terminalize an otherwise delivered interactive run.  The async engine is
    # still disposed at the task boundary below, before this fresh loop closes.
    return asyncio.run(_run_task_with_local_resources(coroutine))


@shared_task(
    bind=True,
    name="backend.celery_task.finn_v2_task.process_finn_v2_run",
    acks_late=True,
    reject_on_worker_lost=True,
    track_started=True,
)
def process_finn_v2_run(self, *, run_id: str) -> str:
    return _run_async(_process_finn_v2_run(run_id=run_id, owner=str(self.request.id or "celery")))


async def _process_finn_v2_run(*, run_id: str, owner: str) -> str:
    async with async_session_factory() as session:
        dispatches = FinnV2DispatchRepository(session)
        run = (await session.execute(select(FinnV2Run).where(FinnV2Run.id == run_id))).scalars().first()
        if run is None or is_terminal_status(run.status):
            return run_id
        dispatch = await dispatches.claim(run_id=run_id, owner=owner, lease_seconds=DISPATCH_LEASE_SECONDS)
        if dispatch is None:
            return run_id
        await session.commit()
        dispatch_id = dispatch.dispatch_id
        user_id = run.user_id
    stop_heartbeat = asyncio.Event()

    async def _heartbeat_loop() -> None:
        while True:
            try:
                await asyncio.wait_for(stop_heartbeat.wait(), timeout=DISPATCH_HEARTBEAT_SECONDS)
                return
            except asyncio.TimeoutError:
                async with async_session_factory() as heartbeat_session:
                    renewed = await FinnV2DispatchRepository(heartbeat_session).heartbeat(
                        dispatch_id=dispatch_id,
                        owner=owner,
                        lease_seconds=DISPATCH_LEASE_SECONDS,
                    )
                    await heartbeat_session.commit()
                if not renewed:
                    logger.warning("FINN V2 dispatch lease lost", extra={"run_id": run_id, "dispatch_id": dispatch_id})
                    return

    heartbeat_task = asyncio.create_task(_heartbeat_loop(), name=f"finn-v2-dispatch-heartbeat:{dispatch_id}")
    try:
        async with async_session_factory() as session:
            await FinnV2DispatchRepository(session).heartbeat(dispatch_id=dispatch_id, owner=owner, lease_seconds=DISPATCH_LEASE_SECONDS)
            await session.commit()
        await FinnV2RunService.run_foundation_lifecycle_owned(run_id=run_id, user_id=user_id)
        async with async_session_factory() as session:
            completed_run = (
                await session.execute(select(FinnV2Run).where(FinnV2Run.id == run_id))
            ).scalars().first()
            if completed_run is None or not is_terminal_status(completed_run.status):
                raise RuntimeError("finn_v2_lifecycle_returned_nonterminal")
            dispatches = FinnV2DispatchRepository(session)
            if completed_run.status in {"failed", "canceled"}:
                if completed_run.retryable:
                    raise RuntimeError(completed_run.error_code or "finn_v2_retryable_lifecycle_failure")
                await dispatches.mark_terminal_failure(
                    dispatch_id=dispatch_id,
                    error_code=completed_run.error_code or completed_run.status,
                )
            else:
                await dispatches.mark_completed(dispatch_id)
            await session.commit()
    except Exception as exc:
        async with async_session_factory() as session:
            await FinnV2DispatchRepository(session).mark_failure(dispatch_id=dispatch_id, error_code=type(exc).__name__)
            await session.commit()
        raise
    finally:
        stop_heartbeat.set()
        await heartbeat_task
    return run_id


@shared_task(name="backend.celery_task.finn_v2_task.recover_finn_v2_dispatches")
def recover_finn_v2_dispatches() -> int:
    return _run_async(_recover_finn_v2_dispatches())


async def _recover_finn_v2_dispatches() -> int:
    async with async_session_factory() as session:
        repository = FinnV2DispatchRepository(session)
        expired = await repository.expire_stale_unclaimed(
            limit=100,
            max_age_seconds=DISPATCH_STALE_UNCLAIMED_SECONDS,
        )
        await session.commit()
    # A dead-lettered visible dispatch must also terminalize its run. Terminal
    # rows are excluded by the repository, making recovery safe to repeat.
    for row in expired:
        async with async_session_factory() as session:
            user_id = (await session.execute(select(FinnV2Run.user_id).where(FinnV2Run.id == row.run_id))).scalar_one()
            await FinnV2RunService(session).fail_run(
                run_id=row.run_id,
                user_id=user_id,
                error_code="dispatch_claim_timeout",
                error_message="FINN could not start this request in time. Please try again.",
                retryable=False,
                failure_stage="dispatch_recovery",
            )
    async with async_session_factory() as session:
        dispatches = await FinnV2DispatchRepository(session).list_recoverable(limit=100)
        rows = [(row.dispatch_id, row.run_id, row.task_id, row.queue) for row in dispatches]
    recovered = 0
    for dispatch_id, run_id, task_id, queue in rows:
        try:
            reservation_owner = f"recovery:{uuid.uuid4().hex}"
            async with async_session_factory() as session:
                reserved = await FinnV2DispatchRepository(session).reserve_recovery(
                    dispatch_id=dispatch_id,
                    owner=reservation_owner,
                    lease_seconds=RECOVERY_RESERVATION_SECONDS,
                )
                await session.commit()
            if not reserved:
                continue
            # The reservation blocks overlapping recovery workers.  Restore
            # pending just before broker handoff so a promptly delivered task
            # can claim normally; its retry deadline prevents a second
            # recovery from racing the handoff window.
            async with async_session_factory() as session:
                await FinnV2DispatchRepository(session).mark_published(dispatch_id)
                await session.commit()
            process_finn_v2_run.apply_async(kwargs={"run_id": run_id}, task_id=task_id, queue=queue or resolve_task_queue(process_finn_v2_run.name))
            recovered += 1
        except Exception:
            logger.exception("FINN V2 durable dispatch recovery enqueue failed", extra={"dispatch_id": dispatch_id, "run_id": run_id})
    return recovered


@shared_task(name="backend.celery_task.finn_v2_task.process_shadow_foundation_run")
def process_shadow_foundation_run(
    *,
    user_id: int,
    request_payload: Dict[str, Any],
    request_path: str,
    request_id: str,
    trace_id: str,
) -> str:
    return _run_async(
        run_shadow_foundation_job(
            user_id=user_id,
            request_payload=request_payload,
            request_path=request_path,
            request_id=request_id,
            trace_id=trace_id,
        )
    )


@shared_task(name="backend.celery_task.finn_v2_task.cleanup_finn_v2_retention")
def cleanup_finn_v2_retention() -> Dict[str, int]:
    result = _run_async(run_retention_cleanup_job())
    logger.info("FINN V2 retention task completed: %s", result)
    return result
