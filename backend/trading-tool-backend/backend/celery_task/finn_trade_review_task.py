"""Durably project newly settled bot ledger round trips into review records."""

import asyncio
import logging
from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy import text
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.infrastructure.database import ASYNC_DATABASE_URL, async_session_factory
from backend.services.finn_trade_review_service import FinnTradeReviewService, completed_reflection_week
from backend.services.finn_trade_analysis_service import FinnTradeAnalysisService
from backend.services.finn_trade_review_rollout import allowed_trade_review_users
from backend.services.finn_exchange_import_service import FinnExchangeImportService
from backend.services.finn_bybit_derivative_import_service import FinnBybitDerivativeImportService


logger = logging.getLogger(__name__)


@shared_task(name="backend.celery_task.finn_trade_review_task.finalize_weekly_trade_reflections")
def finalize_weekly_trade_reflections() -> int:
    return asyncio.run(_run_with_task_database(_finalize_weekly_trade_reflections))


async def _finalize_weekly_trade_reflections(session_factory=None) -> int:
    """Save the last closed Amsterdam week for every owner with a review."""
    session_factory = session_factory or async_session_factory
    allowed = allowed_trade_review_users()
    if allowed == set():
        return 0
    monday, _, start, end = completed_reflection_week(datetime.now(timezone.utc))
    user_filter = "AND user_id = ANY(CAST(:allowed AS INTEGER[]))" if allowed is not None else ""
    params = {"start": start, "end": end}
    if allowed is not None:
        params["allowed"] = sorted(allowed)
    completed = 0
    last_user_id = 0
    while True:
        async with session_factory() as session:
            result = await session.execute(text(f"""
                SELECT DISTINCT user_id FROM finn_trade_reviews
                WHERE exit_at >= :start AND exit_at < :end
                  AND user_id > :last_user_id {user_filter}
                ORDER BY user_id LIMIT 500
            """), {**params, "last_user_id": last_user_id})
            user_ids = [int(row.user_id) for row in result.fetchall()]
        if not user_ids:
            break
        for user_id in user_ids:
            try:
                async with session_factory() as session:
                    await FinnTradeReviewService(session).weekly_report(user_id, monday)
                completed += 1
            except Exception:
                logger.exception("FINN weekly reflection failed", extra={"user_id": user_id})
        last_user_id = user_ids[-1]
    return completed


@shared_task(name="backend.celery_task.finn_trade_review_task.sync_linked_exchange_fills")
def sync_linked_exchange_fills() -> int:
    return asyncio.run(_run_with_task_database(_sync_linked_exchange_fills))


async def _sync_linked_exchange_fills(session_factory=None) -> int:
    session_factory = session_factory or async_session_factory
    allowed = allowed_trade_review_users()
    if allowed == set():
        return 0
    owner_filter = "AND k.user_id = ANY(CAST(:allowed AS INTEGER[]))" if allowed is not None else ""
    async with session_factory() as session:
        result = await session.execute(text(f"""
            SELECT k.user_id, LOWER(k.exchange_name) AS exchange_name
            FROM exchange_keys k
            LEFT JOIN finn_exchange_import_attempts attempt
              ON attempt.user_id=k.user_id
             AND attempt.exchange_name=LOWER(k.exchange_name)
            WHERE k.is_active=TRUE AND LOWER(k.exchange_name) IN ('bitvavo','bybit')
              AND (attempt.last_attempt_at IS NULL
                   OR attempt.last_attempt_at <= NOW() - INTERVAL '5 minutes')
              {owner_filter}
            ORDER BY attempt.last_attempt_at NULLS FIRST, k.user_id, k.exchange_name
            LIMIT 2
        """), {"allowed": sorted(allowed)} if allowed is not None else {})
        targets = [(int(row.user_id), str(row.exchange_name)) for row in result.fetchall()]
    completed = 0
    for user_id, exchange_name in targets:
        try:
            async with session_factory() as session:
                await FinnExchangeImportService(session).sync(user_id, exchange_name)
            completed += 1
        except Exception:
            logger.warning("FINN exchange import failed", extra={"exchange_name": exchange_name})
    return completed


@shared_task(name="backend.celery_task.finn_trade_review_task.sync_bybit_derivatives")
def sync_bybit_derivatives() -> int:
    return asyncio.run(_run_with_task_database(_sync_bybit_derivatives))


async def _sync_bybit_derivatives(session_factory=None) -> int:
    """Continue bounded history windows fairly, including after worker restarts."""
    session_factory = session_factory or async_session_factory
    allowed = allowed_trade_review_users()
    if allowed == set():
        return 0
    owner_filter = "AND k.user_id = ANY(CAST(:allowed AS INTEGER[]))" if allowed is not None else ""
    async with session_factory() as session:
        result = await session.execute(text(f"""
            SELECT k.user_id
            FROM exchange_keys k
            LEFT JOIN finn_bybit_derivative_attempts attempt ON attempt.user_id=k.user_id
            WHERE k.is_active=TRUE AND LOWER(k.exchange_name)='bybit'
              AND (attempt.last_attempt_at IS NULL
                   OR attempt.last_attempt_at <= NOW() - INTERVAL '5 minutes')
              {owner_filter}
            ORDER BY attempt.last_attempt_at NULLS FIRST, k.user_id
            LIMIT 2
        """), {"allowed": sorted(allowed)} if allowed is not None else {})
        user_ids = [int(row.user_id) for row in result.fetchall()]
    completed = 0
    for user_id in user_ids:
        try:
            async with session_factory() as session:
                await FinnBybitDerivativeImportService(session).sync(user_id)
            completed += 1
        except Exception:
            logger.warning("FINN Bybit derivative import failed", extra={"user_id": user_id})
    return completed


async def _run_with_task_database(job) -> int:
    """Keep review database connections inside this Celery task's event loop.

    Other tasks on the same queue can use the process-wide async engine from a
    different, already closed asyncio.run loop. A task-local NullPool avoids
    checking out one of those connections or leaving one behind for the next
    task.
    """
    engine = create_async_engine(ASYNC_DATABASE_URL, poolclass=NullPool)
    try:
        sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        return await job(sessions)
    finally:
        await engine.dispose()


@shared_task(name="backend.celery_task.finn_trade_review_task.project_dirty_trade_reviews")
def project_dirty_trade_reviews() -> int:
    return asyncio.run(_run_with_task_database(_project_dirty_trade_reviews))


async def _project_dirty_trade_reviews(session_factory=None) -> int:
    session_factory = session_factory or async_session_factory
    allowed = allowed_trade_review_users()
    if allowed == set():
        return 0
    user_filter = "WHERE user_id = ANY(CAST(:allowed AS INTEGER[]))" if allowed is not None else ""
    async with session_factory() as session:
        result = await session.execute(text(f"""
            SELECT user_id FROM finn_trade_review_dirty_users
            {user_filter}
            ORDER BY updated_at, user_id LIMIT 50
        """), {"allowed": sorted(allowed)} if allowed is not None else {})
        user_ids = [int(row[0]) for row in result.fetchall()]
    completed = 0
    for user_id in user_ids:
        try:
            async with session_factory() as session:
                await FinnTradeReviewService(session)._project(user_id)
            completed += 1
        except Exception:
            logger.exception("FINN trade review projection failed", extra={"user_id": user_id})
    return completed


@shared_task(name="backend.celery_task.finn_trade_review_task.analyze_pending_trade_reviews")
def analyze_pending_trade_reviews() -> int:
    return asyncio.run(_run_with_task_database(_analyze_pending_trade_reviews))


async def _analyze_pending_trade_reviews(session_factory=None) -> int:
    session_factory = session_factory or async_session_factory
    allowed = allowed_trade_review_users()
    if allowed == set():
        return 0
    user_filter = "AND user_id = ANY(CAST(:allowed AS INTEGER[]))" if allowed is not None else ""
    async with session_factory() as session:
        result = await session.execute(text(f"""
            WITH queued AS (
              SELECT user_id, id, exit_at,
                     ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY exit_at, id) AS rank
              FROM finn_trade_reviews
              WHERE (analysis_status='pending' OR
                (analysis_status='running' AND analysis_updated_at < NOW() - INTERVAL '10 minutes') OR
                (analysis_status IN ('failed','unavailable')
                 AND analysis_updated_at < NOW() - INTERVAL '1 hour'
                 AND (SELECT COUNT(*) FROM finn_trade_ai_call_attempts attempts
                      WHERE attempts.review_id=finn_trade_reviews.id
                        AND attempts.purpose='analysis'
                        AND attempts.input_revision=finn_trade_reviews.input_revision) < 3))
              {user_filter}
            )
            SELECT q.user_id, q.id FROM queued q
            WHERE q.rank=1 AND (
              SELECT COUNT(*) FROM finn_trade_ai_call_attempts recent
              WHERE recent.user_id=q.user_id AND recent.created_at >= NOW() - INTERVAL '1 day'
            ) < 20
            ORDER BY q.exit_at, q.id LIMIT 6
        """), {"allowed": sorted(allowed)} if allowed is not None else {})
        targets = [(int(row.user_id), int(row.id)) for row in result.fetchall()]
    completed = 0
    for user_id, review_id in targets:
        try:
            async with session_factory() as session:
                await FinnTradeAnalysisService(session).analyze(user_id, review_id, retry=True, scheduled=True)
            completed += 1
        except Exception:
            logger.exception("FINN trade analysis failed", extra={"review_id": review_id})
    return completed
