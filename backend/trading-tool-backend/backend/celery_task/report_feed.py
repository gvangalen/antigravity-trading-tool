"""Publish one coach-feed item after a periodic report is committed."""

import logging
from datetime import date, datetime, timezone

logger = logging.getLogger(__name__)


def publish_periodic_report_ready(user_id: int, report_type: str, report_date: date) -> None:
    if report_type not in {"weekly", "monthly", "quarterly"}:
        raise ValueError("Unsupported report type")

    from backend.infrastructure.database import async_session_factory, run_celery_coroutine
    from backend.services.finn_coach_feed_service import FinnCoachFeedService

    async def publish():
        async with async_session_factory() as session:
            await FinnCoachFeedService(session).publish(
                user_id=user_id,
                event_key=f"{report_type}-report:{report_date.isoformat()}",
                event_type="periodic_report_ready",
                subject_type="report",
                subject_id=f"{report_type}:{report_date.isoformat()}",
                subject=report_type,
                symbol=None,
                evidence={"report_type": report_type, "report_date": report_date.isoformat()},
                source_observed_at=datetime.now(timezone.utc),
                priority=2,
                revision=report_date.isoformat(),
            )
            await session.commit()

    try:
        run_celery_coroutine(publish())
    except Exception:
        logger.exception("Unable to publish %s report feed item for user %s", report_type, user_id)
