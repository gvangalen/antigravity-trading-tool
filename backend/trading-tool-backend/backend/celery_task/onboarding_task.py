import logging
from celery import shared_task, chain
from backend.utils.db import get_db_connection

logger = logging.getLogger(__name__)


@shared_task(
    name="backend.celery_task.onboarding_task.run_onboarding_pipeline",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 30},
    retry_backoff=True,
)
def run_onboarding_pipeline(self, user_id: int):
    """Refresh owner-scoped source history, scores and report.

    Onboarding no longer starts the legacy chain of independent AI agents.
    Completed scores publish coach feed events; navigation never generates a
    first-dashboard briefing.
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
        workflow = chain(
            bootstrap_indicator_histories.si(user_id=user_id, enqueue_score_refresh=False),
            store_daily_scores_task.si(user_id),
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
