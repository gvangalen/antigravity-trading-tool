from __future__ import annotations

import asyncio
import logging
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


def _run_async(coroutine):
    """Run one Celery task on a fresh loop without reusing asyncpg connections."""
    # Celery's prefork children execute many tasks, while asyncio.run creates a
    # loop per task. Discard pooled asyncpg connections from the prior loop.
    engine.sync_engine.dispose(close=False)
    return asyncio.run(coroutine)


@shared_task(bind=True, name="backend.celery_task.finn_v2_task.process_finn_v2_run")
def process_finn_v2_run(self, *, run_id: str) -> str:
    return _run_async(_process_finn_v2_run(run_id=run_id, owner=str(self.request.id or "celery")))


async def _process_finn_v2_run(*, run_id: str, owner: str) -> str:
    async with async_session_factory() as session:
        dispatches = FinnV2DispatchRepository(session)
        run = (await session.execute(select(FinnV2Run).where(FinnV2Run.id == run_id))).scalars().first()
        if run is None or is_terminal_status(run.status):
            return run_id
        dispatch = await dispatches.claim(run_id=run_id, owner=owner, lease_seconds=300)
        if dispatch is None:
            return run_id
        await session.commit()
        dispatch_id = dispatch.dispatch_id
        user_id = run.user_id
    try:
        async with async_session_factory() as session:
            await FinnV2DispatchRepository(session).heartbeat(dispatch_id=dispatch_id, owner=owner, lease_seconds=300)
            await session.commit()
        await FinnV2RunService.run_foundation_lifecycle_owned(run_id=run_id, user_id=user_id)
        async with async_session_factory() as session:
            completed_run = (
                await session.execute(select(FinnV2Run).where(FinnV2Run.id == run_id))
            ).scalars().first()
            if completed_run is None or not is_terminal_status(completed_run.status):
                raise RuntimeError("finn_v2_lifecycle_returned_nonterminal")
            await FinnV2DispatchRepository(session).mark_completed(dispatch_id)
            await session.commit()
    except Exception as exc:
        async with async_session_factory() as session:
            await FinnV2DispatchRepository(session).mark_failure(dispatch_id=dispatch_id, error_code=type(exc).__name__)
            await session.commit()
        raise
    return run_id


@shared_task(name="backend.celery_task.finn_v2_task.recover_finn_v2_dispatches")
def recover_finn_v2_dispatches() -> int:
    return _run_async(_recover_finn_v2_dispatches())


async def _recover_finn_v2_dispatches() -> int:
    async with async_session_factory() as session:
        dispatches = await FinnV2DispatchRepository(session).list_recoverable(limit=100)
        rows = [(row.dispatch_id, row.run_id, row.task_id, row.queue) for row in dispatches]
    recovered = 0
    for dispatch_id, run_id, task_id, queue in rows:
        try:
            process_finn_v2_run.apply_async(kwargs={"run_id": run_id}, task_id=task_id, queue=queue or resolve_task_queue(process_finn_v2_run.name))
            async with async_session_factory() as session:
                await FinnV2DispatchRepository(session).mark_dispatched(dispatch_id)
                await session.commit()
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
