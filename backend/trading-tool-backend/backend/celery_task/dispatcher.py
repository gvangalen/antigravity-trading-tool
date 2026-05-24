from celery import shared_task, current_app
import logging
from backend.utils.db import get_db_connection
from backend.celery_task.queue_policy import resolve_task_queue, resolve_workload_class

logger = logging.getLogger(__name__)


@shared_task(name="backend.celery_task.dispatcher.dispatch_for_all_users")
def dispatch_for_all_users(task_name: str, *, active_only: bool = True):
    conn = get_db_connection()
    if not conn:
        logger.error("❌ Geen DB-verbinding in dispatcher")
        return

    try:
        with conn.cursor() as cur:
            if active_only:
                cur.execute("SELECT id FROM users WHERE is_active = true;")
            else:
                cur.execute("SELECT id FROM users;")

            user_ids = [r[0] for r in cur.fetchall()]

        if not user_ids:
            logger.warning("⚠️ Geen users gevonden om te dispatchen")
            return

        queue_name = resolve_task_queue(task_name)
        workload_class = resolve_workload_class(task_name)
        user_count = len(user_ids)
        max_countdown_seconds = max(0, (user_count - 1) * 2)

        logger.info(
            "🚀 Dispatch task=%s queue=%s workload=%s users=%s spread_seconds=%s",
            task_name,
            queue_name,
            workload_class,
            user_count,
            max_countdown_seconds,
        )

        task = current_app.tasks.get(task_name)
        if not task:
            logger.error(f"❌ Task niet gevonden: {task_name}")
            return

        for i, user_id in enumerate(user_ids):

            # 🔥 BELANGRIJK: stagger jobs (voorkomt pieken)
            countdown_seconds = i * 2  # 2 sec tussen users

            task.apply_async(
                kwargs={"user_id": user_id},
                countdown=countdown_seconds,
                queue=queue_name,
            )

            logger.info(
                "➡️ Task gepland task=%s queue=%s workload=%s user=%s countdown=%ss",
                task_name,
                queue_name,
                workload_class,
                user_id,
                countdown_seconds,
            )

    except Exception as e:
        logger.error(f"❌ Dispatcher fout: {e}", exc_info=True)
    finally:
        conn.close()
