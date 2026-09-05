import asyncio
import json
import os
import time
from datetime import date, datetime, timezone
from functools import lru_cache
from typing import Any, Dict, Optional

from sqlalchemy import text

from backend.celery_task.legacy_queue_drain import summarize_legacy_queue_messages
from backend.celery_task.queue_policy import DEFAULT_QUEUE, NAMED_QUEUES, rate_limit_summary_by_queue
from backend.infrastructure.database import async_session_factory
from backend.services.build_metadata_service import build_metadata_snapshot
from backend.services.platform_metrics import process_metrics_snapshot


PM2_CELERY_WORKER_QUEUE_MAP = {
    "celery-worker-default": [DEFAULT_QUEUE],
    "celery-worker-market-portfolio": ["market_data", "portfolio"],
    "celery-worker-scoring-execution": ["scoring", "execution_critical"],
    "celery-worker-ai-reporting": ["ai_generation"],
    "celery-worker-finn-interactive": ["finn_interactive"],
}

FIRST_DASHBOARD_TASK_NAMES = [
    "backend.celery_task.onboarding_task.enqueue_first_dashboard_briefing",
    "backend.celery_task.onboarding_task.generate_first_dashboard_briefing",
]

# Celery broadcasts inspection replies over the broker. Keep one bounded
# response window that accommodates a warming worker without masking a down
# control plane behind PM2 process state.
CELERY_CONTROL_RESPONSE_TIMEOUT_SECONDS = 8.0


@lru_cache(maxsize=1)
def _health_celery_app():
    """Load the Celery app once before issuing control-plane inspections."""
    from backend.celery_task.celery_app import celery_app

    return celery_app


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


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if isinstance(value, (date, datetime)):
        return _as_utc(value)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        try:
            return _as_utc(datetime.fromisoformat(normalized))
        except ValueError:
            return None
    return None


def _age_seconds(value: Any) -> Optional[int]:
    dt = _parse_timestamp(value)
    if not dt:
        return None
    return max(0, int((_utcnow() - dt).total_seconds()))


def _component(status: str, **extra: Any) -> Dict[str, Any]:
    return {"status": status, **extra}


class SystemHealthService:
    """Best-effort deep health checks for ops dashboards and deploy gates."""

    _last_queue_depths_snapshot: Optional[Dict[str, Any]] = None
    # The worker control commands use the bounded response window above.
    # This budget also covers the one-time Celery app import on a fresh API
    # process, so a healthy just-started control plane is not reported down.
    _celery_inspect_timeout_seconds: float = 15.0

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
        cls._attach_queue_runtime_metadata(components)
        overall = cls._overall_status(components)
        metrics = process_metrics_snapshot()
        return {
            "status": overall,
            "checked_at": _utcnow().isoformat(),
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "components": components,
            "cluster_observability": cls._cluster_observability_summary(components, metrics),
            **metrics,
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
                queue_metrics = await SystemHealthService._queue_metrics(
                    client,
                    queue_depths=queue_depths,
                    sample_size=200,
                )
                default_queue_sample = await SystemHealthService._queue_sample_summary(
                    client,
                    queue_name=DEFAULT_QUEUE,
                    sample_size=200,
                )
                return _component(
                    "ok",
                    broker="redis",
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                    default_queue_depth=queue_depths.get(DEFAULT_QUEUE, 0),
                    default_queue_sample=default_queue_sample,
                    queue_depths=queue_depths,
                    queue_metrics=queue_metrics,
                    total_queue_depth=sum(queue_depths.values()),
                )
            finally:
                await client.aclose()
        except Exception as exc:
            return _component("down", broker="redis", error=str(exc))

    @staticmethod
    async def _queue_sample_summary(client: Any, *, queue_name: str, sample_size: int) -> Dict[str, Any]:
        total_depth = int(await client.llen(queue_name) or 0)
        if total_depth <= 0:
            return {
                "queue": queue_name,
                "sample_size": 0,
                "rerouteable_count": 0,
                "kept_on_default_count": 0,
                "reroute_ratio": 0.0,
                "top_tasks": [],
            }
        raw_messages = await client.lrange(queue_name, -sample_size, -1)
        summary = summarize_legacy_queue_messages(raw_messages, source_queue=queue_name)
        return {"queue": queue_name, **summary}

    @staticmethod
    def _decode_queue_message(raw_message: Any) -> Optional[Dict[str, Any]]:
        if raw_message is None:
            return None
        if isinstance(raw_message, bytes):
            raw_message = raw_message.decode("utf-8")
        if not isinstance(raw_message, str):
            return None
        try:
            payload = json.loads(raw_message)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _message_published_at(raw_message: Any) -> Optional[datetime]:
        payload = SystemHealthService._decode_queue_message(raw_message)
        if not payload:
            return None

        headers = payload.get("headers") if isinstance(payload.get("headers"), dict) else {}
        properties = payload.get("properties") if isinstance(payload.get("properties"), dict) else {}

        candidates = [
            headers.get("published_at"),
            headers.get("sent_at"),
            headers.get("created_at"),
            properties.get("published_at"),
            properties.get("sent_at"),
            properties.get("timestamp"),
        ]
        for candidate in candidates:
            parsed = _parse_timestamp(candidate)
            if parsed:
                return parsed
        return None

    @staticmethod
    def _queue_age_summary(raw_messages: list[Any]) -> Dict[str, Any]:
        ages = [
            _age_seconds(timestamp)
            for timestamp in (
                SystemHealthService._message_published_at(raw_message)
                for raw_message in raw_messages
            )
        ]
        ages = [age for age in ages if age is not None]
        sample_size = len(raw_messages)

        if not ages:
            return {
                "sample_size": sample_size,
                "timestamped_sample_size": 0,
                "timestamp_coverage_ratio": 0.0,
                "oldest_message_age_seconds": None,
                "newest_message_age_seconds": None,
                "average_message_age_seconds": None,
                "age_source": "unavailable",
            }

        return {
            "sample_size": sample_size,
            "timestamped_sample_size": len(ages),
            "timestamp_coverage_ratio": round(len(ages) / sample_size, 4) if sample_size else 0.0,
            "oldest_message_age_seconds": max(ages),
            "newest_message_age_seconds": min(ages),
            "average_message_age_seconds": round(sum(ages) / len(ages), 2),
            "age_source": "celery_published_at_header",
        }

    @classmethod
    def _queue_depth_trend(cls, queue_depths: Dict[str, int]) -> Dict[str, Dict[str, Any]]:
        now = time.time()
        previous = cls._last_queue_depths_snapshot
        cls._last_queue_depths_snapshot = {
            "checked_at_monotonic": now,
            "queue_depths": dict(queue_depths),
        }

        trend: Dict[str, Dict[str, Any]] = {}
        for queue_name, depth in queue_depths.items():
            metric: Dict[str, Any] = {
                "depth_delta_since_last_check": None,
                "depth_delta_per_minute": None,
                "estimated_drain_per_minute": None,
                "trend_source": "needs_previous_health_check",
            }
            if previous:
                elapsed_seconds = max(0.001, now - float(previous["checked_at_monotonic"]))
                previous_depth = int(previous["queue_depths"].get(queue_name, 0))
                delta = int(depth) - previous_depth
                delta_per_minute = round(delta / (elapsed_seconds / 60), 2)
                metric = {
                    "depth_delta_since_last_check": delta,
                    "depth_delta_per_minute": delta_per_minute,
                    "estimated_drain_per_minute": abs(delta_per_minute) if delta_per_minute < 0 else 0.0,
                    "trend_source": "in_process_previous_health_check",
                }
            trend[queue_name] = metric
        return trend

    @classmethod
    async def _queue_metrics(
        cls,
        client: Any,
        *,
        queue_depths: Dict[str, int],
        sample_size: int,
    ) -> Dict[str, Dict[str, Any]]:
        depth_trends = cls._queue_depth_trend(queue_depths)
        metrics: Dict[str, Dict[str, Any]] = {}
        for queue_name, depth in queue_depths.items():
            raw_messages = []
            if depth > 0:
                raw_messages = await client.lrange(queue_name, -sample_size, -1)
            age_summary = cls._queue_age_summary(list(raw_messages))
            metrics[queue_name] = {
                "depth": depth,
                **age_summary,
                **depth_trends.get(queue_name, {}),
            }
        return metrics

    @staticmethod
    def _attach_queue_runtime_metadata(components: Dict[str, Dict[str, Any]]) -> None:
        broker = components.get("broker") or {}
        celery = components.get("celery") or {}
        queue_metrics = broker.get("queue_metrics")
        if not isinstance(queue_metrics, dict):
            return

        workers_by_queue = celery.get("workers_by_queue") if isinstance(celery.get("workers_by_queue"), dict) else {}
        rate_limits = celery.get("rate_limits_by_queue") if isinstance(celery.get("rate_limits_by_queue"), dict) else {}

        for queue_name, metric in queue_metrics.items():
            workers = list(workers_by_queue.get(queue_name, []))
            rate_limit = None
            if queue_name in rate_limits and isinstance(rate_limits[queue_name], dict):
                rate_limit = rate_limits[queue_name].get("rate_limit")
            metric["workers"] = workers
            metric["rate_limit"] = rate_limit
            metric["worker_mapping_source"] = celery.get("worker_mapping_source") or "celery_active_queues_inspect"
            metric["rate_limit_source"] = "queue_policy_static"
            metric["depth_source"] = "redis_llen"

    @staticmethod
    def _cluster_observability_summary(
        components: Dict[str, Dict[str, Any]],
        metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        runtime_identity = metrics.get("runtime_identity") if isinstance(metrics.get("runtime_identity"), dict) else {}
        observability_scope = (
            metrics.get("observability_scope")
            if isinstance(metrics.get("observability_scope"), dict)
            else {}
        )
        degraded_components = sorted(
            component_name
            for component_name, component in components.items()
            if isinstance(component, dict) and component.get("status") != "ok"
        )
        celery = components.get("celery") if isinstance(components.get("celery"), dict) else {}
        broker = components.get("broker") if isinstance(components.get("broker"), dict) else {}
        return {
            **runtime_identity,
            "default_queue_name": DEFAULT_QUEUE,
            "named_queue_count": len(NAMED_QUEUES),
            "visible_worker_count": celery.get("worker_count", 0),
            "visible_workers": celery.get("workers", []),
            "total_queue_depth": broker.get("total_queue_depth"),
            "degraded_components": degraded_components,
            **observability_scope,
        }

    @staticmethod
    async def _check_celery() -> Dict[str, Any]:
        try:
            ping_result = await SystemHealthService._safe_celery_inspect(SystemHealthService._celery_ping)
            active_queues = await SystemHealthService._safe_celery_inspect(
                SystemHealthService._celery_active_queues
            )
            stats_result = await SystemHealthService._safe_celery_inspect(SystemHealthService._celery_stats)
            registered_result = await SystemHealthService._safe_celery_inspect(
                SystemHealthService._celery_registered
            )

            workers = SystemHealthService._visible_workers(
                ping_result=ping_result or {},
                active_queues=active_queues or {},
                stats_result=stats_result or {},
                registered_result=registered_result or {},
            )
            workers_by_queue = SystemHealthService._workers_by_queue(active_queues or {})
            worker_mapping_source = "celery_active_queues_inspect"

            if not workers or not active_queues:
                pm2_snapshot = await asyncio.to_thread(SystemHealthService._pm2_celery_workers_snapshot)
                # PM2 only proves that a process was spawned. A worker must
                # answer Celery's queue inspection before deploy can call it
                # healthy; otherwise Redis may accept an unclaimable task.
                return _component(
                    "down",
                    worker_count=len(workers),
                    workers=workers,
                    workers_by_queue=workers_by_queue,
                    worker_mapping_source=worker_mapping_source,
                    control_plane_ready=False,
                    pm2_workers=(pm2_snapshot or {}).get("workers", []),
                )
            if not workers_by_queue.get("finn_interactive"):
                return _component(
                    "down",
                    worker_count=len(workers),
                    workers=workers,
                    workers_by_queue=workers_by_queue,
                    worker_mapping_source=worker_mapping_source,
                    control_plane_ready=True,
                    missing_queue="finn_interactive",
                )
            return _component(
                "ok",
                worker_count=len(workers),
                workers=workers,
                workers_by_queue=workers_by_queue,
                worker_mapping_source=worker_mapping_source,
                control_plane_ready=True,
                worker_discovery_sources=SystemHealthService._worker_discovery_sources(
                    ping_result=ping_result or {},
                    active_queues=active_queues or {},
                    stats_result=stats_result or {},
                    registered_result=registered_result or {},
                    worker_mapping_source=worker_mapping_source,
                ),
                registered_tasks=SystemHealthService._registered_task_summary(registered_result or {}),
                build=build_metadata_snapshot(service="backend"),
                rate_limits_by_queue=rate_limit_summary_by_queue(),
            )
        except Exception as exc:
            return _component(
                "error",
                error=str(exc),
                worker_count=0,
                workers=[],
                workers_by_queue={},
                build=build_metadata_snapshot(service="backend"),
                rate_limits_by_queue=rate_limit_summary_by_queue(),
            )

    @staticmethod
    async def _safe_celery_inspect(callback: Any) -> Optional[Dict[str, Any]]:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(callback),
                timeout=SystemHealthService._celery_inspect_timeout_seconds,
            )
        except (asyncio.TimeoutError, TimeoutError):
            return None

    @staticmethod
    def _celery_ping() -> Optional[Dict[str, Any]]:
        inspector = _health_celery_app().control.inspect(
            timeout=CELERY_CONTROL_RESPONSE_TIMEOUT_SECONDS
        )
        return inspector.ping()

    @staticmethod
    def _celery_active_queues() -> Optional[Dict[str, Any]]:
        inspector = _health_celery_app().control.inspect(
            timeout=CELERY_CONTROL_RESPONSE_TIMEOUT_SECONDS
        )
        return inspector.active_queues()

    @staticmethod
    def _celery_stats() -> Optional[Dict[str, Any]]:
        inspector = _health_celery_app().control.inspect(
            timeout=CELERY_CONTROL_RESPONSE_TIMEOUT_SECONDS
        )
        return inspector.stats()

    @staticmethod
    def _celery_registered() -> Optional[Dict[str, Any]]:
        inspector = _health_celery_app().control.inspect(
            timeout=CELERY_CONTROL_RESPONSE_TIMEOUT_SECONDS
        )
        return inspector.registered()

    @staticmethod
    def _visible_workers(
        *,
        ping_result: Dict[str, Any],
        active_queues: Dict[str, Any],
        stats_result: Dict[str, Any],
        registered_result: Dict[str, Any],
    ) -> list[str]:
        workers = set()
        workers.update(SystemHealthService._dict_keys(ping_result))
        workers.update(SystemHealthService._dict_keys(active_queues))
        workers.update(SystemHealthService._dict_keys(stats_result))
        workers.update(SystemHealthService._dict_keys(registered_result))
        return sorted(worker for worker in workers if isinstance(worker, str) and worker.strip())

    @staticmethod
    def _worker_discovery_sources(
        *,
        ping_result: Dict[str, Any],
        active_queues: Dict[str, Any],
        stats_result: Dict[str, Any],
        registered_result: Dict[str, Any],
        worker_mapping_source: Optional[str] = None,
    ) -> list[str]:
        sources = []
        if ping_result:
            sources.append("ping")
        if active_queues:
            sources.append("active_queues")
        if stats_result:
            sources.append("stats")
        if registered_result:
            sources.append("registered")
        if worker_mapping_source == "pm2_process_list_static_queue_map":
            sources.append("pm2")
        return sources

    @staticmethod
    def _registered_task_summary(registered_result: Dict[str, Any]) -> Dict[str, Any]:
        workers_with_first_dashboard = {}
        for worker_name, task_names in (registered_result or {}).items():
            normalized = [str(task_name) for task_name in (task_names or [])]
            matched = [task_name for task_name in normalized if task_name in FIRST_DASHBOARD_TASK_NAMES]
            if matched:
                workers_with_first_dashboard[str(worker_name)] = matched
        return {
            "required_tasks": list(FIRST_DASHBOARD_TASK_NAMES),
            "workers_with_first_dashboard_tasks": workers_with_first_dashboard,
            "visible_worker_count": len(workers_with_first_dashboard),
        }

    @staticmethod
    def _dict_keys(value: Any) -> list[str]:
        if not isinstance(value, dict):
            return []
        return [key for key in value.keys() if isinstance(key, str)]

    @staticmethod
    def _pm2_celery_workers_snapshot() -> Dict[str, Any]:
        pm2_dump_path = os.getenv("PM2_DUMP_PATH", "/home/ubuntu/.pm2/dump.pm2")
        try:
            with open(pm2_dump_path, "r", encoding="utf-8") as handle:
                processes = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(processes, list):
            return {}

        suffix = "-staging" if os.getenv("APP_ENV") == "staging" else ""
        workers = []
        workers_by_queue = {queue_name: [] for queue_name in NAMED_QUEUES}

        for base_name, queue_names in PM2_CELERY_WORKER_QUEUE_MAP.items():
            process_name = f"{base_name}{suffix}"
            process = next(
                (
                    item
                    for item in processes
                    if isinstance(item, dict) and item.get("name") == process_name
                ),
                None,
            )
            status = ((process or {}).get("pm2_env") or {}).get("status") or (process or {}).get("status")
            if status != "online":
                continue
            workers.append(process_name)
            for queue_name in queue_names:
                workers_by_queue.setdefault(queue_name, []).append(process_name)

        if not workers:
            return {}

        return {
            "workers": sorted(workers),
            "workers_by_queue": {
                queue_name: sorted(queue_workers)
                for queue_name, queue_workers in workers_by_queue.items()
            },
            "worker_mapping_source": "pm2_process_list_static_queue_map",
        }

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
