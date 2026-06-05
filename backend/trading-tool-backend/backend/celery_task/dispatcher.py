from celery import shared_task, current_app
import logging
import os
import time
from backend.utils.db import get_db_connection
from backend.celery_task.queue_policy import (
    resolve_task_queue,
    resolve_task_rate_limit,
    resolve_queue_backlog_limit,
    resolve_dispatch_window_seconds,
    resolve_workload_class,
)
from backend.services.platform_metrics import increment_dispatcher_counter

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 100
DEFAULT_MAX_SPREAD_SECONDS = 300
DEFAULT_DISPATCH_WINDOW_SECONDS = 15 * 60
DEFAULT_QUEUE_BACKLOG_LIMIT = 1000


def _broker_client():
    broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    import redis

    return redis.from_url(broker_url, socket_connect_timeout=1, socket_timeout=1)


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


def _dispatch_window_bucket(*, now_ts: float, window_seconds: int) -> int:
    active_window = max(1, int(window_seconds))
    return int(now_ts // active_window)


def _dispatch_wave_key(task_name: str, *, window_bucket: int) -> str:
    return f"dispatcher:wave:{task_name}:{window_bucket}"


def _dispatch_user_key(task_name: str, *, user_id: int, window_bucket: int) -> str:
    return f"dispatcher:user:{task_name}:{user_id}:{window_bucket}"


def _try_acquire_dispatch_lease(client, key: str, *, ttl_seconds: int) -> bool:
    return bool(client.set(key, "1", nx=True, ex=max(1, int(ttl_seconds))))


def _queue_has_capacity(client, *, queue_name: str, backlog_limit: int) -> tuple[bool, int]:
    depth = int(client.llen(queue_name) or 0)
    return depth < max(1, int(backlog_limit)), depth


@shared_task(name="backend.celery_task.dispatcher.dispatch_for_all_users")
def dispatch_for_all_users(
    task_name: str,
    *,
    active_only: bool = True,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_spread_seconds: int = DEFAULT_MAX_SPREAD_SECONDS,
    dispatch_window_seconds: int | None = None,
    backlog_limit: int | None = None,
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
        rate_limit = resolve_task_rate_limit(task_name) or "none"
        backlog_limit = (
            resolve_queue_backlog_limit(task_name)
            if backlog_limit is None
            else int(backlog_limit)
        ) or DEFAULT_QUEUE_BACKLOG_LIMIT
        dispatch_window_seconds = resolve_dispatch_window_seconds(
            task_name,
            fallback_seconds=dispatch_window_seconds or DEFAULT_DISPATCH_WINDOW_SECONDS,
        )
        user_count = len(user_ids)
        plan = _dispatch_plan(
            user_count,
            batch_size=batch_size,
            max_spread_seconds=max_spread_seconds,
        )

        broker_client = None
        queue_depth = None
        skipped_due_to_existing_wave = False
        skipped_due_to_backlog = False
        window_bucket = _dispatch_window_bucket(
            now_ts=time.time(),
            window_seconds=dispatch_window_seconds,
        )

        try:
            broker_client = _broker_client()
            wave_key = _dispatch_wave_key(task_name, window_bucket=window_bucket)
            if not _try_acquire_dispatch_lease(
                broker_client,
                wave_key,
                ttl_seconds=dispatch_window_seconds,
            ):
                skipped_due_to_existing_wave = True
            else:
                has_capacity, queue_depth = _queue_has_capacity(
                    broker_client,
                    queue_name=queue_name,
                    backlog_limit=backlog_limit,
                )
                skipped_due_to_backlog = not has_capacity
        except Exception as broker_exc:
            logger.warning(
                "⚠️ Dispatcher kon broker-state niet inspecteren voor task=%s queue=%s: %s",
                task_name,
                queue_name,
                broker_exc,
            )
        finally:
            if broker_client is not None:
                try:
                    broker_client.close()
                except Exception:
                    pass

        if skipped_due_to_existing_wave:
            increment_dispatcher_counter("wave_lease_skip_count")
            logger.warning(
                "⏭️ Dispatcher skip task=%s queue=%s workload=%s reason=wave_already_active window=%s",
                task_name,
                queue_name,
                workload_class,
                window_bucket,
            )
            return {
                "ok": True,
                "task_name": task_name,
                "queue": queue_name,
                "skipped": True,
                "reason": "wave_already_active",
                "window_bucket": window_bucket,
            }

        if skipped_due_to_backlog:
            increment_dispatcher_counter("backlog_skip_count")
            logger.warning(
                "⏭️ Dispatcher skip task=%s queue=%s workload=%s reason=queue_backlog depth=%s limit=%s",
                task_name,
                queue_name,
                workload_class,
                queue_depth,
                backlog_limit,
            )
            return {
                "ok": True,
                "task_name": task_name,
                "queue": queue_name,
                "skipped": True,
                "reason": "queue_backlog",
                "queue_depth": queue_depth,
                "backlog_limit": backlog_limit,
                "window_bucket": window_bucket,
            }

        logger.info(
            "🚀 Dispatch task=%s queue=%s workload=%s rate_limit=%s users=%s batch_size=%s batches=%s max_spread_seconds=%s max_countdown=%s backlog_limit=%s window_seconds=%s",
            task_name,
            queue_name,
            workload_class,
            rate_limit,
            user_count,
            plan["batch_size"],
            plan["batch_count"],
            plan["max_spread_seconds"],
            plan["max_countdown_seconds"],
            backlog_limit,
            dispatch_window_seconds,
        )

        task = current_app.tasks.get(task_name)
        if not task:
            logger.error(f"❌ Task niet gevonden: {task_name}")
            return

        enqueued = 0
        deduped = 0
        lease_client = None
        try:
            lease_client = _broker_client()
        except Exception as broker_exc:
            logger.warning(
                "⚠️ Dispatcher kon user-lease client niet openen voor task=%s: %s",
                task_name,
                broker_exc,
            )

        try:
            for i, user_id in enumerate(user_ids):
                countdown_seconds = _bounded_countdown(
                    i,
                    batch_size=plan["batch_size"],
                    max_spread_seconds=plan["max_spread_seconds"],
                )

                user_lease_acquired = True
                if lease_client is not None:
                    try:
                        user_lease_key = _dispatch_user_key(
                            task_name,
                            user_id=user_id,
                            window_bucket=window_bucket,
                        )
                        user_lease_acquired = _try_acquire_dispatch_lease(
                            lease_client,
                            user_lease_key,
                            ttl_seconds=dispatch_window_seconds,
                        )
                    except Exception as broker_exc:
                        logger.warning(
                            "⚠️ Dispatcher kon user-lease niet claimen voor task=%s user=%s: %s",
                            task_name,
                            user_id,
                            broker_exc,
                        )

                if not user_lease_acquired:
                    deduped += 1
                    increment_dispatcher_counter("window_dedupe_skip_count")
                    logger.info(
                        "⏭️ Dispatch dedupe task=%s queue=%s user=%s window=%s",
                        task_name,
                        queue_name,
                        user_id,
                        window_bucket,
                    )
                    continue

                task.apply_async(
                    kwargs={"user_id": user_id},
                    countdown=countdown_seconds,
                    queue=queue_name,
                )
                enqueued += 1

                logger.info(
                    "➡️ Task gepland task=%s queue=%s workload=%s rate_limit=%s user=%s batch=%s countdown=%ss",
                    task_name,
                    queue_name,
                    workload_class,
                    rate_limit,
                    user_id,
                    i // plan["batch_size"],
                    countdown_seconds,
                )
        finally:
            if lease_client is not None:
                try:
                    lease_client.close()
                except Exception:
                    pass

        return {
            "ok": True,
            "task_name": task_name,
            "queue": queue_name,
            "window_bucket": window_bucket,
            "users_seen": user_count,
            "enqueued": enqueued,
            "deduped": deduped,
            "backlog_limit": backlog_limit,
            "dispatch_window_seconds": dispatch_window_seconds,
        }

    except Exception as e:
        logger.error(f"❌ Dispatcher fout: {e}", exc_info=True)
    finally:
        conn.close()
