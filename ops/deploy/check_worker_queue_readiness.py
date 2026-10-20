"""Fail a deployment until Celery inspection confirms every topology queue."""

import json
import os
import sys
from pathlib import Path


WORKER_BY_QUEUE = {
    "compact": {
        "celery": "background",
        "market_data": "background",
        "portfolio": "background",
        "scoring": "background",
        "execution_critical": "background",
        "ai_generation": "background",
        "finn_interactive": "finn-interactive",
    },
    "scaled": {
        "celery": "background",
        "market_data": "market-portfolio",
        "portfolio": "market-portfolio",
        "scoring": "scoring",
        "execution_critical": "execution-critical",
        "ai_generation": "ai-reporting",
        "finn_interactive": "finn-interactive",
    },
}


def missing_queue_consumers(payload: dict, *, topology: str, environment: str) -> list[str]:
    if topology not in WORKER_BY_QUEUE:
        raise ValueError(f"Unknown worker topology: {topology}")
    celery = (payload.get("components") or {}).get("celery") or {}
    if celery.get("status") != "ok" or celery.get("control_plane_ready") is not True:
        return ["celery_control_plane"]
    if celery.get("worker_mapping_source") != "celery_active_queues_inspect":
        return ["celery_active_queues_inspect"]
    workers_by_queue = celery.get("workers_by_queue") or {}
    prefix = "staging-" if environment == "staging" else ""
    missing = []
    for logical_queue, worker_label in WORKER_BY_QUEUE[topology].items():
        queue_name = prefix + logical_queue
        expected_worker = f"{environment}-{worker_label}@"
        workers = workers_by_queue.get(queue_name) or []
        if not any(isinstance(worker, str) and worker.startswith(expected_worker) for worker in workers):
            missing.append(queue_name)
    return missing


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: check_worker_queue_readiness.py <deep-health.json>")
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    missing = missing_queue_consumers(
        payload,
        topology=os.environ.get("TRADAMIND_WORKER_TOPOLOGY", "compact"),
        environment=os.environ.get("APP_ENV", "production"),
    )
    if missing:
        print(f"Celery queue consumers not ready: {', '.join(missing)}", file=sys.stderr)
        return 1
    print("Celery queue consumers ready for selected topology")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
