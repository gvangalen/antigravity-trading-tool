from celery import shared_task, current_app
import logging
from backend.utils.db import get_db_connection
from backend.celery_task.queue_policy import resolve_task_queue, resolve_workload_class

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 100
DEFAULT_MAX_SPREAD_SECONDS = 300


def _normalize_dispatch_window(batch_size: int, max_spread_seconds: int) -> tuple[int, int]:
    resolved_batch_size = DEFAULT_BATCH_SIZE if batch_size is None else batch_size
    resolved_spread = (
        DEFAULT_MAX_SPREAD_SECONDS
        if max_spread_seconds is None
        else max_spread_seconds
    )
    return max(1, int(resolved_batch_size)), max(0, int(resolved_spread))


def _bounded_countdown(index: int, *, batch_size: int, max_spread_seconds: int) -> int:
    batch_size, max_spread_seconds = _normalize_dispatch_window(
        batch_size, max_spread_seconds
    )
    if batch_size == 1 or max_spread_seconds == 0:
        return 0
    offset = index % batch_size
    return round((offset / (batch_size - 1)) * max_spread_seconds)


def _dispatch_plan(user_count: int, *, batch_size: int, max_spread_seconds: int) -> dict:
    batch_size, max_spread_seconds = _normalize_dispatch_window(
        batch_size, max_spread_seconds
    )
    batch_count = (max(0, user_count) + batch_size - 1) // batch_size if user_count else 0
    return {
        "batch_size": batch_size,
        "batch_count": batch_count,
        "max_spread_seconds": max_spread_seconds,
        "max_countdown_seconds": max_spread_seconds if user_count > 1 else 0,
    }


@shared_task(name="backend.celery_task.dispatcher.dispatch_for_all_users")
def dispatch_for_all_users(
    task_name: str,
    *,
    active_only: bool = True,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_spread_seconds: int = DEFAULT_MAX_SPREAD_SECONDS,
):
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
        plan = _dispatch_plan(
            user_count,
            batch_size=batch_size,
            max_spread_seconds=max_spread_seconds,
        )

        logger.info(
            "🚀 Dispatch task=%s queue=%s workload=%s users=%s batch_size=%s batches=%s max_spread_seconds=%s max_countdown=%s",
            task_name,
            queue_name,
            workload_class,
            user_count,
            plan["batch_size"],
            plan["batch_count"],
            plan["max_spread_seconds"],
            plan["max_countdown_seconds"],
        )

        task = current_app.tasks.get(task_name)
        if not task:
            logger.error(f"❌ Task niet gevonden: {task_name}")
            return

        for i, user_id in enumerate(user_ids):
            countdown_seconds = _bounded_countdown(
                i,
                batch_size=plan["batch_size"],
                max_spread_seconds=plan["max_spread_seconds"],
            )

            task.apply_async(
                kwargs={"user_id": user_id},
                countdown=countdown_seconds,
                queue=queue_name,
            )

            logger.info(
                "➡️ Task gepland task=%s queue=%s workload=%s user=%s batch=%s countdown=%ss",
                task_name,
                queue_name,
                workload_class,
                user_id,
                i // plan["batch_size"],
                countdown_seconds,
            )

    except Exception as e:
        logger.error(f"❌ Dispatcher fout: {e}", exc_info=True)
    finally:
        conn.close()
