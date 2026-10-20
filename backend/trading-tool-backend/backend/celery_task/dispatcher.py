from celery import shared_task, current_app, states
from celery.signals import task_postrun
import logging
import os
import time
import uuid
from backend.utils.db import get_db_connection
from backend.celery_task.queue_policy import (
    NAMED_QUEUES,
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
    return f"dispatcher:{os.getenv('APP_ENV', 'production')}:wave:{task_name}:{window_bucket}"


def _dispatch_user_key(task_name: str, *, user_id: int, window_bucket: int) -> str:
    return f"dispatcher:{os.getenv('APP_ENV', 'production')}:user:{task_name}:{user_id}:{window_bucket}"


def _try_acquire_dispatch_lease(client, key: str, *, ttl_seconds: int) -> bool:
    return bool(client.set(key, "1", nx=True, ex=max(1, int(ttl_seconds))))


def _queue_has_capacity(client, *, queue_name: str, backlog_limit: int) -> tuple[bool, int]:
    depth = int(client.llen(queue_name) or 0)
    return depth < max(1, int(backlog_limit)), depth


_RESERVE_CAPACITY_SCRIPT = """
local queued = redis.call('LLEN', KEYS[1])
local reserved = redis.call('ZCARD', KEYS[2])
if queued + reserved >= tonumber(ARGV[1]) then
    return {0, queued, reserved}
end
redis.call('ZADD', KEYS[2], ARGV[3], ARGV[2])
return {1, queued, reserved}
"""


def _reservation_key(queue_name: str) -> str:
    return f"dispatcher:{os.getenv('APP_ENV', 'production')}:scheduled:{queue_name}"


def _reserve_dispatch_capacity(client, *, queue_name: str, backlog_limit: int) -> tuple[bool, str]:
    token = uuid.uuid4().hex
    admitted, _, _ = client.eval(
        _RESERVE_CAPACITY_SCRIPT,
        2,
        queue_name,
        _reservation_key(queue_name),
        max(1, int(backlog_limit)),
        token,
        int(time.time()),
    )
    return bool(admitted), token


@task_postrun.connect
def release_dispatch_reservation(task_id=None, task=None, state=None, **_kwargs):
    """Keep a dispatched task counted until it actually finishes.

    A worker lost before postrun leaves the reservation in place. This fails
    closed instead of admitting above the backlog limit; operations must
    reconcile a lost task before removing its reservation.
    """
    headers = getattr(getattr(task, "request", None), "headers", None) or {}
    queue_name = headers.get("dispatch_queue") if isinstance(headers, dict) else None
    token = headers.get("dispatch_reservation") if isinstance(headers, dict) else None
    if not queue_name or not token or token != task_id or state not in states.READY_STATES:
        return
    client = None
    try:
        client = _broker_client()
        client.zrem(_reservation_key(queue_name), token)
    except Exception:
        logger.exception("Could not release dispatcher reservation task_id=%s queue=%s", task_id, queue_name)
    finally:
        if client is not None:
            client.close()


@shared_task(name="backend.celery_task.dispatcher.monitor_dispatch_reservations")
def monitor_dispatch_reservations():
    """Emit a recurring operational error for reservations older than one hour."""
    client = _broker_client()
    stale_before = time.time() - 3600
    try:
        for queue_name in NAMED_QUEUES:
            stale_count = int(client.zcount(_reservation_key(queue_name), "-inf", stale_before) or 0)
            if stale_count:
                increment_dispatcher_counter("stale_reservation_alert_count")
                logger.critical(
                    "Dispatcher stale reservations require operator reconciliation queue=%s count=%s",
                    queue_name, stale_count,
                )
    finally:
        client.close()


def _schedule_continuation(
    *, task_name: str, active_only: bool, batch_size: int, max_spread_seconds: int,
    dispatch_window_seconds: int, backlog_limit: int, start_after_user_id: int,
    continuation_attempt: int, window_bucket: int,
) -> bool:
    if continuation_attempt and continuation_attempt % 120 == 0:
        logger.error("Dispatcher wave still backlogged task=%s after_user=%s retries=%s",
                     task_name, start_after_user_id, continuation_attempt)
    dispatch_for_all_users.apply_async(
        kwargs={
            "task_name": task_name,
            "active_only": active_only,
            "batch_size": batch_size,
            "max_spread_seconds": max_spread_seconds,
            "dispatch_window_seconds": dispatch_window_seconds,
            "backlog_limit": backlog_limit,
            "start_after_user_id": start_after_user_id,
            "continuation_attempt": continuation_attempt + 1,
            "origin_window_bucket": window_bucket,
        },
        countdown=60,
        queue=resolve_task_queue(dispatch_for_all_users.name),
    )
    return True


@shared_task(name="backend.celery_task.dispatcher.dispatch_for_all_users")
def dispatch_for_all_users(
    task_name: str,
    *,
    active_only: bool = True,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_spread_seconds: int = DEFAULT_MAX_SPREAD_SECONDS,
    dispatch_window_seconds: int | None = None,
    backlog_limit: int | None = None,
    start_after_user_id: int = 0,
    continuation_attempt: int = 0,
    origin_window_bucket: int | None = None,
):
    conn = get_db_connection()
    if not conn:
        logger.error("❌ Geen DB-verbinding in dispatcher")
        return

    try:
        with conn.cursor() as cur:
            if active_only:
                cur.execute("""
                    SELECT id FROM users
                    WHERE is_active = true
                      AND COALESCE(ai_preferences #>> '{capacity_fixture,kind}', '') <> 'read_only_load_v1'
                    ORDER BY id;
                """)
            else:
                cur.execute("""
                    SELECT id FROM users
                    WHERE COALESCE(ai_preferences #>> '{capacity_fixture,kind}', '') <> 'read_only_load_v1'
                    ORDER BY id;
                """)

            user_ids = [r[0] for r in cur.fetchall() if r[0] > start_after_user_id]

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
        window_bucket = origin_window_bucket if origin_window_bucket is not None else _dispatch_window_bucket(
            now_ts=time.time(), window_seconds=dispatch_window_seconds,
        )

        try:
            broker_client = _broker_client()
            wave_key = _dispatch_wave_key(task_name, window_bucket=window_bucket)
            if not continuation_attempt and not _try_acquire_dispatch_lease(
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
            logger.error(
                "Dispatcher stopt: broker-state niet beschikbaar voor task=%s queue=%s: %s",
                task_name,
                queue_name,
                broker_exc,
            )
            return {"ok": False, "task_name": task_name, "reason": "broker_unavailable"}
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
            continued = _schedule_continuation(
                task_name=task_name, active_only=active_only, batch_size=batch_size,
                max_spread_seconds=max_spread_seconds,
                dispatch_window_seconds=dispatch_window_seconds,
                backlog_limit=backlog_limit, start_after_user_id=start_after_user_id,
                continuation_attempt=continuation_attempt, window_bucket=window_bucket,
            )
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
                "continued": continued,
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
        deferred = 0
        lease_client = None
        try:
            lease_client = _broker_client()
        except Exception as broker_exc:
            logger.error(
                "Dispatcher stopt: user-lease client niet beschikbaar voor task=%s: %s",
                task_name,
                broker_exc,
            )
            return {"ok": False, "task_name": task_name, "reason": "broker_unavailable"}

        try:
            for i, user_id in enumerate(user_ids):
                countdown_seconds = _bounded_countdown(
                    i,
                    batch_size=plan["batch_size"],
                    max_spread_seconds=plan["max_spread_seconds"],
                )

                user_lease_acquired = True
                user_lease_key = _dispatch_user_key(
                    task_name, user_id=user_id, window_bucket=window_bucket,
                )
                user_lease_acquired = _try_acquire_dispatch_lease(
                    lease_client, user_lease_key, ttl_seconds=dispatch_window_seconds,
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

                try:
                    has_capacity, reservation_token = _reserve_dispatch_capacity(
                        lease_client, queue_name=queue_name,
                        backlog_limit=backlog_limit,
                    )
                except Exception:
                    lease_client.delete(user_lease_key)
                    raise
                if not has_capacity:
                    lease_client.delete(user_lease_key)
                    deferred = user_count - i
                    increment_dispatcher_counter("backlog_skip_count")
                    _schedule_continuation(
                        task_name=task_name, active_only=active_only, batch_size=batch_size,
                        max_spread_seconds=max_spread_seconds,
                        dispatch_window_seconds=dispatch_window_seconds,
                        backlog_limit=backlog_limit,
                        start_after_user_id=user_ids[i - 1] if i else start_after_user_id,
                        continuation_attempt=continuation_attempt, window_bucket=window_bucket,
                    )
                    break
                try:
                    task.apply_async(
                        kwargs={"user_id": user_id},
                        countdown=countdown_seconds,
                        queue=queue_name,
                        task_id=reservation_token,
                        headers={"dispatch_reservation": reservation_token, "dispatch_queue": queue_name},
                    )
                except Exception:
                    lease_client.zrem(_reservation_key(queue_name), reservation_token)
                    lease_client.delete(user_lease_key)
                    raise
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
            "deferred": deferred,
            "backlog_limit": backlog_limit,
            "dispatch_window_seconds": dispatch_window_seconds,
        }

    except Exception as e:
        logger.error(f"❌ Dispatcher fout: {e}", exc_info=True)
    finally:
        conn.close()
