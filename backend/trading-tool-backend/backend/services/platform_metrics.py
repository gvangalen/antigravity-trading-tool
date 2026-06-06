from __future__ import annotations

import math
import os
import socket
from collections import defaultdict, deque
from datetime import datetime, timezone
from threading import Lock
from typing import Deque, Dict


_COUNTER_LOCK = Lock()
_LATENCY_LOCK = Lock()

_DISPATCHER_COUNTERS: dict[str, int] = defaultdict(int)
_EXECUTION_SAFETY_COUNTERS: dict[str, int] = defaultdict(int)
_RETRY_COUNTERS: dict[str, int] = defaultdict(int)
_LATENCY_SAMPLES: dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=256))
_PROCESS_STARTED_AT = datetime.now(timezone.utc)
_PROCESS_HOSTNAME = socket.gethostname()
_PROCESS_PID = os.getpid()
_PROCESS_APP_ENV = os.getenv("APP_ENV", "unknown")


def runtime_identity_snapshot() -> Dict[str, object]:
    instance_id = f"{_PROCESS_APP_ENV}:{_PROCESS_HOSTNAME}:{_PROCESS_PID}"
    return {
        "instance_id": instance_id,
        "hostname": _PROCESS_HOSTNAME,
        "pid": _PROCESS_PID,
        "app_env": _PROCESS_APP_ENV,
        "process_started_at": _PROCESS_STARTED_AT.isoformat(),
    }


def increment_dispatcher_counter(name: str, amount: int = 1) -> None:
    with _COUNTER_LOCK:
        _DISPATCHER_COUNTERS[name] += max(0, int(amount))


def increment_execution_safety_counter(name: str, amount: int = 1) -> None:
    with _COUNTER_LOCK:
        _EXECUTION_SAFETY_COUNTERS[name] += max(0, int(amount))


def increment_retry_counter(task_family: str, amount: int = 1) -> None:
    with _COUNTER_LOCK:
        _RETRY_COUNTERS[task_family] += max(0, int(amount))


def record_latency_sample(name: str, duration_ms: float) -> None:
    try:
        value = max(0.0, float(duration_ms))
    except (TypeError, ValueError):
        return
    with _LATENCY_LOCK:
        _LATENCY_SAMPLES[name].append(value)


def _percentile(samples: list[float], percentile: float) -> float | None:
    if not samples:
        return None
    ordered = sorted(samples)
    if len(ordered) == 1:
        return round(ordered[0], 2)
    rank = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return round(ordered[rank], 2)


def latency_summary(name: str) -> dict[str, float | int | None]:
    with _LATENCY_LOCK:
        samples = list(_LATENCY_SAMPLES.get(name, ()))
    return {
        "sample_size": len(samples),
        "p50": _percentile(samples, 0.5),
        "p95": _percentile(samples, 0.95),
    }


def process_metrics_snapshot() -> Dict[str, object]:
    with _COUNTER_LOCK:
        dispatcher = dict(_DISPATCHER_COUNTERS)
        execution = dict(_EXECUTION_SAFETY_COUNTERS)
        retries = dict(_RETRY_COUNTERS)
    dashboard_latency = latency_summary("dashboard_aggregation_latency_ms")
    assistant_latency = latency_summary("assistant_context_latency_ms")
    return {
        "metrics_scope": "process_lifetime",
        "runtime_identity": runtime_identity_snapshot(),
        "observability_scope": {
            "queue_truth_scope": "broker_snapshot_at_check_time",
            "worker_truth_scope": "celery_inspect_snapshot_visible_from_current_instance",
            "counter_truth_scope": "instance_process_lifetime",
            "latency_truth_scope": "instance_process_window_last_256_samples",
            "cluster_rollup_ready": False,
            "cluster_rollup_note": (
                "Aggregate multiple /api/system/health payloads externally for true cluster-wide "
                "interpretation."
            ),
        },
        "dispatcher_counters": {
            "wave_lease_skip_count": dispatcher.get("wave_lease_skip_count", 0),
            "backlog_skip_count": dispatcher.get("backlog_skip_count", 0),
            "window_dedupe_skip_count": dispatcher.get("window_dedupe_skip_count", 0),
        },
        "execution_safety_counters": {
            "replay_block_hits": execution.get("replay_block_hits", 0),
            "execution_duplicate_guard_hits": execution.get("execution_duplicate_guard_hits", 0),
        },
        "retry_counters": retries,
        "latency_metrics": {
            "dashboard_aggregation_latency_ms_p50": dashboard_latency["p50"],
            "dashboard_aggregation_latency_ms_p95": dashboard_latency["p95"],
            "assistant_context_latency_ms_p50": assistant_latency["p50"],
            "assistant_context_latency_ms_p95": assistant_latency["p95"],
            "dashboard_aggregation_sample_size": dashboard_latency["sample_size"],
            "assistant_context_sample_size": assistant_latency["sample_size"],
        },
    }


def reset_process_metrics() -> None:
    with _COUNTER_LOCK:
        _DISPATCHER_COUNTERS.clear()
        _EXECUTION_SAFETY_COUNTERS.clear()
        _RETRY_COUNTERS.clear()
    with _LATENCY_LOCK:
        _LATENCY_SAMPLES.clear()
