import asyncio
import os
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text

from backend.celery_task.queue_policy import NAMED_QUEUES, rate_limit_summary_by_queue
from backend.infrastructure.database import async_session_factory


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return None


def _age_seconds(value: Any) -> Optional[int]:
    dt = _as_utc(value)
    if not dt:
        return None
    return max(0, int((_utcnow() - dt).total_seconds()))


def _component(status: str, **extra: Any) -> Dict[str, Any]:
    return {"status": status, **extra}


class SystemHealthService:
    """Best-effort deep health checks for ops dashboards and deploy gates."""

    @classmethod
    async def deep_health(cls) -> Dict[str, Any]:
        started = time.perf_counter()
        components = {
            "database": await cls._check_database(),
            "broker": await cls._check_broker(),
            "celery": await cls._check_celery(),
            "market_snapshot": await cls._check_latest_market_snapshot(),
            "scores": await cls._check_latest_score(),
        }
        overall = cls._overall_status(components)
        return {
            "status": overall,
            "checked_at": _utcnow().isoformat(),
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "components": components,
        }

    @staticmethod
    def _overall_status(components: Dict[str, Dict[str, Any]]) -> str:
        statuses = {item.get("status") for item in components.values()}
        if "down" in statuses:
            return "degraded"
        if "error" in statuses:
            return "degraded"
        if "stale" in statuses:
            return "degraded"
        if "unknown" in statuses:
            return "degraded"
        return "ok"

    @staticmethod
    async def _check_database() -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            async with async_session_factory() as session:
                await session.execute(text("SELECT 1"))
            return _component("ok", latency_ms=round((time.perf_counter() - started) * 1000, 2))
        except Exception as exc:
            return _component("down", error=str(exc), latency_ms=round((time.perf_counter() - started) * 1000, 2))

    @staticmethod
    async def _check_broker() -> Dict[str, Any]:
        broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        try:
            import redis.asyncio as redis

            client = redis.from_url(broker_url, socket_connect_timeout=1, socket_timeout=1)
            started = time.perf_counter()
            try:
                await client.ping()
                queue_depths = {
                    queue_name: int(await client.llen(queue_name) or 0)
                    for queue_name in NAMED_QUEUES
                }
                return _component(
                    "ok",
                    broker="redis",
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                    default_queue_depth=queue_depths.get(os.getenv("CELERY_DEFAULT_QUEUE", "celery"), 0),
                    queue_depths=queue_depths,
                    total_queue_depth=sum(queue_depths.values()),
                )
            finally:
                await client.aclose()
        except Exception as exc:
            return _component("down", broker="redis", error=str(exc))

    @staticmethod
    async def _check_celery() -> Dict[str, Any]:
        try:
            result = await asyncio.to_thread(SystemHealthService._celery_ping)
            workers = result or {}
            if not workers:
                return _component("unknown", worker_count=0, workers=[], workers_by_queue={})
            active_queues = await asyncio.to_thread(SystemHealthService._celery_active_queues)
            workers_by_queue = SystemHealthService._workers_by_queue(active_queues or {})
            return _component(
                "ok",
                worker_count=len(workers),
                workers=sorted(workers.keys()),
                workers_by_queue=workers_by_queue,
                rate_limits_by_queue=rate_limit_summary_by_queue(),
            )
        except Exception as exc:
            return _component(
                "error",
                error=str(exc),
                worker_count=0,
                workers=[],
                workers_by_queue={},
                rate_limits_by_queue=rate_limit_summary_by_queue(),
            )

    @staticmethod
    def _celery_ping() -> Optional[Dict[str, Any]]:
        from backend.celery_task.celery_app import celery_app

        inspector = celery_app.control.inspect(timeout=1.0)
        return inspector.ping()

    @staticmethod
    def _celery_active_queues() -> Optional[Dict[str, Any]]:
        from backend.celery_task.celery_app import celery_app

        inspector = celery_app.control.inspect(timeout=1.0)
        return inspector.active_queues()

    @staticmethod
    def _workers_by_queue(active_queues: Dict[str, Any]) -> Dict[str, Any]:
        workers_by_queue = {queue_name: [] for queue_name in NAMED_QUEUES}
        for worker_name, queues in active_queues.items():
            for queue in queues or []:
                queue_name = queue.get("name") if isinstance(queue, dict) else None
                if not queue_name:
                    continue
                workers_by_queue.setdefault(queue_name, []).append(worker_name)
        return {queue: sorted(workers) for queue, workers in workers_by_queue.items()}

    @staticmethod
    async def _check_latest_market_snapshot() -> Dict[str, Any]:
        try:
            async with async_session_factory() as session:
                result = await session.execute(text("""
                    SELECT symbol, timestamp
                    FROM market_data
                    WHERE timestamp IS NOT NULL
                    ORDER BY timestamp DESC
                    LIMIT 1
                """))
                row = result.mappings().first()
            if not row:
                return _component("unknown", message="Geen market_data snapshots gevonden.")
            age = _age_seconds(row["timestamp"])
            status = "ok" if age is not None and age <= 900 else "stale"
            return _component(
                status,
                symbol=row["symbol"],
                latest_timestamp=_as_utc(row["timestamp"]).isoformat() if _as_utc(row["timestamp"]) else None,
                age_seconds=age,
                stale_after_seconds=900,
            )
        except Exception as exc:
            return _component("error", error=str(exc))

    @staticmethod
    async def _check_latest_score() -> Dict[str, Any]:
        try:
            async with async_session_factory() as session:
                result = await session.execute(text("""
                    SELECT symbol, report_date
                    FROM daily_scores
                    WHERE report_date IS NOT NULL
                    ORDER BY report_date DESC
                    LIMIT 1
                """))
                row = result.mappings().first()
            if not row:
                return _component("unknown", message="Geen daily_scores gevonden.")
            age = _age_seconds(row["report_date"])
            status = "ok" if age is not None and age <= 172800 else "stale"
            return _component(
                status,
                symbol=row["symbol"],
                latest_report_date=row["report_date"].isoformat() if row["report_date"] else None,
                age_seconds=age,
                stale_after_seconds=172800,
            )
        except Exception as exc:
            return _component("error", error=str(exc))
