from celery import shared_task, current_app
import logging
import time
from backend.utils.db import get_db_connection

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

        logger.info(f"🚀 Dispatch '{task_name}' voor {len(user_ids)} users")

        task = current_app.tasks.get(task_name)
        if not task:
            logger.error(f"❌ Task niet gevonden: {task_name}")
            return

        for i, user_id in enumerate(user_ids):

            # 🔥 BELANGRIJK: stagger jobs (voorkomt pieken)
            countdown_seconds = i * 2  # 2 sec tussen users

            task.apply_async(
                kwargs={"user_id": user_id},
                countdown=countdown_seconds
            )

            logger.info(f"➡️ Task gepland voor user {user_id} over {countdown_seconds}s")

    except Exception as e:
        logger.error(f"❌ Dispatcher fout: {e}", exc_info=True)
    finally:
        conn.close()
