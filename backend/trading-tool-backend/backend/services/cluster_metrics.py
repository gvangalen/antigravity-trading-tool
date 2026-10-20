"""Small Redis rollup for counters and approximate latency percentiles."""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict

logger = logging.getLogger(__name__)
_client = None
_publish_disabled_until = 0.0
_LATENCY_BUCKETS_MS = (10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000)


def _enabled() -> bool:
    return os.getenv("APP_ENV", "development").lower() in {"production", "staging"}


def _redis():
    global _client
    if _client is None:
        import redis

        url = os.getenv("REDIS_URL") or os.getenv("CELERY_BROKER_URL")
        if not url:
            raise RuntimeError("Cluster metrics require Redis")
        _client = redis.from_url(url, socket_connect_timeout=0.1, socket_timeout=0.1)
    return _client


def reset_after_fork() -> None:
    global _client, _publish_disabled_until
    _client = None
    _publish_disabled_until = 0.0


def _key(minute: int) -> str:
    environment = os.getenv("APP_ENV", "development").lower()
    return f"platform-metrics:{environment}:{minute}"


def _record(field: str, amount: int = 1) -> None:
    global _publish_disabled_until
    if not _enabled():
        return
    if time.monotonic() < _publish_disabled_until:
        return
    try:
        key = _key(int(time.time()) // 60)
        pipe = _redis().pipeline(transaction=False)
        pipe.hincrby(key, field, max(0, int(amount)))
        pipe.expire(key, 7200)
        pipe.execute()
    except Exception:
        _publish_disabled_until = time.monotonic() + 30
        logger.warning("Cluster metrics publish failed", exc_info=True)


def record_counter(family: str, name: str, amount: int = 1) -> None:
    _record(f"counter:{family}:{name}", amount)


def record_latency(name: str, duration_ms: float) -> None:
    upper = next((bound for bound in _LATENCY_BUCKETS_MS if duration_ms <= bound), 60000)
    _record(f"latency:{name}:{upper}")


def snapshot(window_minutes: int = 60) -> dict:
    if not _enabled():
        return {"ready": False, "reason": "cluster_metrics_disabled"}
    try:
        current_minute = int(time.time()) // 60
        minutes = range(current_minute - window_minutes + 1, current_minute + 1)
        pipe = _redis().pipeline(transaction=False)
        for minute in minutes:
            pipe.hgetall(_key(minute))
        rows = pipe.execute()
    except Exception:
        logger.warning("Cluster metrics read failed", exc_info=True)
        return {"ready": False, "reason": "cluster_metrics_unavailable"}

    counters = defaultdict(int)
    histograms = defaultdict(lambda: defaultdict(int))
    for row in rows:
        for raw_field, raw_count in row.items():
            field = raw_field.decode() if isinstance(raw_field, bytes) else str(raw_field)
            count = int(raw_count)
            if field.startswith("counter:"):
                counters[field.removeprefix("counter:")] += count
            elif field.startswith("latency:"):
                name, _, bound = field.removeprefix("latency:").rpartition(":")
                histograms[name][int(bound)] += count

    def percentile(buckets: dict[int, int], fraction: float) -> int | None:
        total = sum(buckets.values())
        if not total:
            return None
        target = max(1, int(total * fraction + 0.999999))
        seen = 0
        for bound, count in sorted(buckets.items()):
            seen += count
            if seen >= target:
                return bound
        return None

    return {
        "ready": True,
        "window_minutes": window_minutes,
        "as_of_minute": current_minute,
        "counters": dict(counters),
        "latency_histograms": {
            name: {"samples": sum(buckets.values()), "p50_upper_ms": percentile(buckets, 0.5),
                   "p95_upper_ms": percentile(buckets, 0.95)}
            for name, buckets in histograms.items()
        },
    }
