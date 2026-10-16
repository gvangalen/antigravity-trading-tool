"""Durably project newly settled bot ledger round trips into review records."""

import asyncio
import logging

from celery import shared_task
from sqlalchemy import text

from backend.infrastructure.database import async_session_factory
from backend.services.finn_trade_review_service import FinnTradeReviewService
from backend.services.finn_trade_analysis_service import FinnTradeAnalysisService
from backend.services.finn_trade_review_rollout import allowed_trade_review_users


logger = logging.getLogger(__name__)


@shared_task(name="backend.celery_task.finn_trade_review_task.project_dirty_trade_reviews")
def project_dirty_trade_reviews() -> int:
    return asyncio.run(_project_dirty_trade_reviews())


async def _project_dirty_trade_reviews() -> int:
    allowed = allowed_trade_review_users()
    if allowed == set():
        return 0
    user_filter = "WHERE user_id = ANY(CAST(:allowed AS INTEGER[]))" if allowed is not None else ""
    async with async_session_factory() as session:
        result = await session.execute(text(f"""
            SELECT user_id FROM finn_trade_review_dirty_users
            {user_filter}
            ORDER BY updated_at, user_id LIMIT 50
        """), {"allowed": sorted(allowed)} if allowed is not None else {})
        user_ids = [int(row[0]) for row in result.fetchall()]
    completed = 0
    for user_id in user_ids:
        try:
            async with async_session_factory() as session:
                await FinnTradeReviewService(session)._project(user_id)
            completed += 1
        except Exception:
            logger.exception("FINN trade review projection failed", extra={"user_id": user_id})
    return completed


@shared_task(name="backend.celery_task.finn_trade_review_task.analyze_pending_trade_reviews")
def analyze_pending_trade_reviews() -> int:
    return asyncio.run(_analyze_pending_trade_reviews())


async def _analyze_pending_trade_reviews() -> int:
    allowed = allowed_trade_review_users()
    if allowed == set():
        return 0
    user_filter = "AND user_id = ANY(CAST(:allowed AS INTEGER[]))" if allowed is not None else ""
    async with async_session_factory() as session:
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
            async with async_session_factory() as session:
                await FinnTradeAnalysisService(session).analyze(user_id, review_id, retry=True, scheduled=True)
            completed += 1
        except Exception:
            logger.exception("FINN trade analysis failed", extra={"review_id": review_id})
    return completed
