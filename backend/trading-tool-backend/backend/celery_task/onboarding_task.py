import logging
import asyncio
from celery import shared_task, chain
from backend.utils.db import get_db_connection

logger = logging.getLogger(__name__)


@shared_task(name="backend.celery_task.onboarding_task.enqueue_first_dashboard_briefing")
def enqueue_first_dashboard_briefing(user_id: int, trigger: str = "bootstrap_agents"):
    """
    Backwards-compatible queue shim for production workers that still enqueue a
    dedicated first-dashboard briefing task from bootstrap flows.
    """
    logger.info("🧭 Queueing first dashboard briefing | user_id=%s | trigger=%s", user_id, trigger)
    generate_first_dashboard_briefing.delay(user_id)
    return {"status": "queued", "user_id": user_id, "trigger": trigger}


@shared_task(name="backend.celery_task.onboarding_task.generate_first_dashboard_briefing")
def generate_first_dashboard_briefing(user_id: int):
    from backend.infrastructure.database import async_session_factory, engine, sync_engine
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
                trigger="onboarding_pipeline",
            )
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
    """
    Volledige onboarding pipeline PER USER.

    Flow:
    1️⃣ Daily scores
    2️⃣ Macro AI insight
    3️⃣ Market AI insight
    4️⃣ Technical AI insight
    5️⃣ Setup agent (beste setup bepalen)
    6️⃣ Strategy agent (dagelijkse strategy snapshot)
    7️⃣ Daily report

    ⚠️ Geen master score, geen batch agents.
    """

    logger.info("=================================================")
    logger.info(f"🚀 ONBOARDING START user_id={user_id}")
    logger.info(f"📌 task_id={self.request.id}")
    logger.info("=================================================")

    conn = get_db_connection()

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
        from backend.ai_agents.macro_ai_agent import generate_macro_insight
        from backend.ai_agents.market_ai_agent import generate_market_insight
        from backend.ai_agents.technical_ai_agent import generate_technical_insight
        from backend.celery_task.setup_task import run_setup_agent_daily

        # 🔥 JUISTE STRATEGY TASK
        from backend.celery_task.strategy_task import (
            run_daily_strategy_snapshot,
        )

        from backend.celery_task.daily_report_task import generate_daily_report

        # --------------------------------------------------
        # 🔗 PER-USER CHAIN (IMMUTABLE)
        # --------------------------------------------------
        workflow = chain(
            # 1️⃣ Scores
            store_daily_scores_task.si(user_id),

            # 2️⃣–4️⃣ AI insights
            generate_macro_insight.si(user_id),
            generate_market_insight.si(user_id),
            generate_technical_insight.si(user_id),

            # 5️⃣ Setup agent → beste setup van de dag
            run_setup_agent_daily.si(user_id),

            # 6️⃣ Strategy agent → daily snapshot
            run_daily_strategy_snapshot.si(user_id),

            # 7️⃣ Dagrapport
            generate_daily_report.si(user_id),

            # 8️⃣ First dashboard briefing
            generate_first_dashboard_briefing.si(user_id),
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
        logger.error("❌ Onboarding pipeline fout", exc_info=True)
        raise

    finally:
        conn.close()
