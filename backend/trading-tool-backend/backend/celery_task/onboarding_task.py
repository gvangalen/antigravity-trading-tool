import logging
import asyncio
from datetime import datetime, timezone
from math import ceil
from celery import shared_task, chain
from backend.utils.db import get_db_connection

logger = logging.getLogger(__name__)


@shared_task(name="backend.celery_task.onboarding_task.enqueue_first_dashboard_briefing", bind=True)
def enqueue_first_dashboard_briefing(self, user_id: int, trigger: str = "onboarding_pipeline"):
    from backend.infrastructure.database import async_session_factory, engine, sync_engine
    from backend.services.finn_plan_service import FinnPlanService

    async def _run() -> dict:
        try:
            await engine.dispose()
        except Exception:
            logger.debug("Async engine dispose skipped before first-dashboard enqueue", exc_info=True)
        try:
            sync_engine.dispose()
        except Exception:
            logger.debug("Sync engine dispose skipped before first-dashboard enqueue", exc_info=True)

        async with async_session_factory() as session:
            service = FinnPlanService(session)
            return await service.enqueue_first_dashboard_briefing(
                user_id,
                trigger=trigger,
                owner_task_id=getattr(self.request, "id", None),
            )

    return asyncio.run(_run())


@shared_task(name="backend.celery_task.onboarding_task.generate_first_dashboard_briefing", bind=True)
def generate_first_dashboard_briefing(
    self,
    user_id: int,
    trigger: str = "onboarding_pipeline",
    enqueued_context_version: str | None = None,
    attempt: int | None = None,
    owner_task_id: str | None = None,
):
    from backend.infrastructure.database import async_session_factory
    from backend.infrastructure.database import engine, sync_engine
    from backend.services.finn_plan_service import FinnPlanService

    async def _run() -> dict:
        # Celery prefork workers can inherit pooled connections from the parent
        # process. Clear them before opening an async session for briefing work.
        try:
            await engine.dispose()
        except Exception:
            logger.debug("Async engine dispose skipped before first-dashboard briefing", exc_info=True)
        try:
            sync_engine.dispose()
        except Exception:
            logger.debug("Sync engine dispose skipped before first-dashboard briefing", exc_info=True)

        async with async_session_factory() as session:
            service = FinnPlanService(session)
            result = await service.generate_and_store_first_dashboard_briefing(
                user_id,
                trigger=trigger,
                task_id=getattr(self.request, "id", None),
                enqueued_context_version=enqueued_context_version,
                attempt=attempt,
                queue_name=(getattr(self.request, "delivery_info", None) or {}).get("routing_key"),
                owner_task_id=owner_task_id,
            )
            # The persisted fallback remains the source of truth. Queue a
            # delayed *enqueue* check without marking it active: the normal
            # enqueue path will reuse ready/in-flight work if a dashboard read
            # already started the retry. Recovery no longer depends on the
            # user keeping FINN Today open.
            retry_at = result.get("next_retry_at") if result.get("status") == "fallback" else None
            if result.get("retryable") and retry_at:
                try:
                    from backend.celery_task.queue_policy import resolve_task_queue

                    due = datetime.fromisoformat(str(retry_at))
                    if due.tzinfo is None:
                        due = due.replace(tzinfo=timezone.utc)
                    countdown = max(1, ceil((due - datetime.now(timezone.utc)).total_seconds()))
                    enqueue_first_dashboard_briefing.apply_async(
                        args=[user_id],
                        kwargs={"trigger": "first_dashboard_retry"},
                        countdown=countdown,
                        queue=resolve_task_queue("backend.celery_task.onboarding_task.enqueue_first_dashboard_briefing"),
                    )
                except Exception:
                    logger.exception("First dashboard retry scheduling failed for user_id=%s", user_id)
            try:
                from backend.api.ai_assistant_api import _invalidate_mission_control_cache

                _invalidate_mission_control_cache(user_id)
            except Exception:
                logger.debug("Mission control API-cache invalidation skipped for user_id=%s", user_id, exc_info=True)
            FinnPlanService.invalidate_runtime_caches_for_user(user_id)
            return result

    return asyncio.run(_run())


@shared_task(
    name="backend.celery_task.onboarding_task.run_onboarding_pipeline",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 30},
    retry_backoff=True,
)
def run_onboarding_pipeline(self, user_id: int):
    """Refresh owner-scoped source history and scores, then regenerate FINN.

    Onboarding no longer starts the legacy chain of independent AI agents.
    FINN Today and chat read the same persisted scores and setup matches.
    """

    logger.info("=================================================")
    logger.info(f"🚀 ONBOARDING START user_id={user_id}")
    logger.info(f"📌 task_id={self.request.id}")
    logger.info("=================================================")

    conn = get_db_connection()
    pipeline_claimed = False

    try:
        # --------------------------------------------------
        # 🔒 IDEMPOTENTIE
        # --------------------------------------------------
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE onboarding_steps
                SET pipeline_started = TRUE
                WHERE user_id = %s
                  AND flow = 'default'
                  AND pipeline_started = FALSE
                RETURNING id;
                """,
                (user_id,),
            )
            rows = cur.fetchall()

        conn.commit()
        pipeline_claimed = True

        if not rows:
            logger.warning(f"⚠️ Onboarding al gestart voor user_id={user_id}")
            return {
                "status": "already_started",
                "user_id": user_id,
                "task_id": self.request.id,
            }

        logger.info(f"✅ pipeline_started gezet voor user_id={user_id}")

        # --------------------------------------------------
        # 🔄 Lazy imports (NA idempotentie)
        # --------------------------------------------------
        from backend.celery_task.store_daily_scores_task import (
            store_daily_scores_task,
        )
        from backend.celery_task.indicator_history_task import bootstrap_indicator_histories
        from backend.celery_task.daily_report_task import generate_daily_report
        # A first briefing may already be generating from the just-saved
        # plan. Re-enqueue after scores so a changed context is regenerated.
        workflow = chain(
            bootstrap_indicator_histories.si(user_id=user_id, enqueue_score_refresh=False),
            store_daily_scores_task.si(user_id),
            enqueue_first_dashboard_briefing.si(user_id, trigger="onboarding_scores_ready"),
            generate_daily_report.si(user_id),
        )

        workflow.apply_async()

        logger.info("🔗 Per-user onboarding workflow succesvol gestart")

        return {
            "status": "started",
            "user_id": user_id,
            "task_id": self.request.id,
        }

    except Exception:
        conn.rollback()
        if pipeline_claimed:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE onboarding_steps
                        SET pipeline_started = FALSE
                        WHERE user_id = %s
                          AND flow = 'default';
                        """,
                        (user_id,),
                    )
                conn.commit()
                logger.warning("↩️ pipeline_started teruggezet na fout voor user_id=%s", user_id)
            except Exception:
                conn.rollback()
                logger.exception("❌ Kon pipeline_started niet terugzetten voor user_id=%s", user_id)
        logger.error("❌ Onboarding pipeline fout", exc_info=True)
        raise

    finally:
        conn.close()
