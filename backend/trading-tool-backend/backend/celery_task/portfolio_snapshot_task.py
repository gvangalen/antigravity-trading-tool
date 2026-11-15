import logging
from celery import shared_task

from backend.services.portfolio_snapshot_service import snapshot_all_for_user

logger = logging.getLogger(__name__)


# =====================================================
# 📊 PORTFOLIO SNAPSHOT TASK
# =====================================================
@shared_task
def run_portfolio_snapshot(user_id: int):
    """
    Maakt een portfolio snapshot voor een specifieke gebruiker.

    Wordt aangeroepen via:
    dispatcher.dispatch_for_all_users
    """

    try:
        snapshot_all_for_user(user_id, bucket="1h")

        logger.info(
            f"📊 Portfolio snapshot succesvol | user_id={user_id}"
        )

        return {
            "status": "ok",
            "user_id": user_id,
        }

    except Exception as e:

        logger.exception(
            f"❌ Portfolio snapshot mislukt | user_id={user_id}"
        )

        return {
            "status": "error",
            "user_id": user_id,
            "error": str(e),
        }


@shared_task(name="backend.celery_task.portfolio_snapshot_task.reconcile_paper_position_risk",
             autoretry_for=(Exception,), retry_backoff=True,
             retry_kwargs={"max_retries": 3})
def reconcile_paper_position_risk(user_id: int):
    """Retryable Paper-only feed observer; no portfolio or trade mutation."""
    from backend.celery_task.finn_v2_task import _run_async
    from backend.infrastructure.database import async_session_factory
    from backend.services.finn_coach_feed_service import FinnCoachFeedService

    async def review():
        async with async_session_factory() as session:
            created = await FinnCoachFeedService(session).reconcile_paper_position_risks(
                user_id=user_id)
            await session.commit()
            return len(created)

    created_count = _run_async(review())
    return {"status": "ok", "user_id": user_id, "created_count": created_count}
