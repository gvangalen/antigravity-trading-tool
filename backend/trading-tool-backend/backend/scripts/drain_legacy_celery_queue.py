"""Inspect or reroute legacy messages from the default Celery queue.

Usage examples:
    python3 backend/scripts/drain_legacy_celery_queue.py --sample-size 200
    python3 backend/scripts/drain_legacy_celery_queue.py --apply --limit 1000
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict

import redis

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.celery_task.legacy_queue_drain import (
    classify_legacy_queue_message,
    summarize_legacy_queue_messages,
)
from backend.celery_task.queue_policy import DEFAULT_QUEUE


logger = logging.getLogger(__name__)


def _broker_client() -> redis.Redis:
    broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    return redis.from_url(broker_url, socket_connect_timeout=2, socket_timeout=2)


def inspect_legacy_queue(queue_name: str, sample_size: int) -> Dict[str, Any]:
    client = _broker_client()
    try:
        total_depth = int(client.llen(queue_name) or 0)
        sample = client.lrange(queue_name, -sample_size, -1) if total_depth else []
        summary = summarize_legacy_queue_messages(sample, source_queue=queue_name)
        return {
            "queue": queue_name,
            "total_depth": total_depth,
            **summary,
        }
    finally:
        client.close()


def _read_queue_depths(client: redis.Redis) -> Dict[str, int]:
    queue_names = [
        "celery",
        "market_data",
        "scoring",
        "portfolio",
        "ai_generation",
        "execution_critical",
    ]
    return {
        queue_name: int(client.llen(queue_name) or 0)
        for queue_name in queue_names
    }


def drain_legacy_queue(queue_name: str, limit: int, *, runtime_cap_seconds: float) -> Dict[str, Any]:
    client = _broker_client()
    temp_queue = f"{queue_name}__drain_tmp__{uuid.uuid4().hex}"
    processed = rerouted = kept = 0
    targets: Dict[str, int] = {}
    started = time.monotonic()
    before_depths = _read_queue_depths(client)
    stop_reason = "limit_reached"
    try:
        while processed < limit:
            if runtime_cap_seconds > 0 and (time.monotonic() - started) >= runtime_cap_seconds:
                stop_reason = "runtime_cap_reached"
                break

            raw_message = client.rpop(queue_name)
            if raw_message is None:
                stop_reason = "queue_drained"
                break

            decision = classify_legacy_queue_message(raw_message, source_queue=queue_name)
            processed += 1

            if decision.reroute:
                client.lpush(decision.target_queue, raw_message)
                rerouted += 1
                targets[decision.target_queue] = targets.get(decision.target_queue, 0) + 1
            else:
                client.lpush(temp_queue, raw_message)
                kept += 1

        while client.llen(temp_queue):
            raw_message = client.lpop(temp_queue)
            if raw_message is None:
                break
            client.rpush(queue_name, raw_message)

        after_depths = _read_queue_depths(client)
        remaining_depth = int(client.llen(queue_name) or 0)
        return {
            "queue": queue_name,
            "limit_requested": limit,
            "runtime_cap_seconds": runtime_cap_seconds,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "stop_reason": stop_reason,
            "processed": processed,
            "rerouted": rerouted,
            "kept": kept,
            "remaining_depth": remaining_depth,
            "rerouted_by_target": targets,
            "before_queue_depths": before_depths,
            "after_queue_depths": after_depths,
        }
    finally:
        client.delete(temp_queue)
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect or drain legacy Celery queue messages.")
    parser.add_argument("--queue", default=DEFAULT_QUEUE, help="Source queue to inspect/drain.")
    parser.add_argument("--sample-size", type=int, default=200, help="How many oldest messages to sample in inspect mode.")
    parser.add_argument("--limit", type=int, default=1000, help="Maximum messages to process in apply mode.")
    parser.add_argument("--runtime-cap-seconds", type=float, default=15.0, help="Maximum runtime for one drain run in apply mode.")
    parser.add_argument("--apply", action="store_true", help="Actually reroute messages instead of only inspecting.")
    args = parser.parse_args()

    if args.apply:
        result = drain_legacy_queue(
            args.queue,
            args.limit,
            runtime_cap_seconds=args.runtime_cap_seconds,
        )
    else:
        result = inspect_legacy_queue(args.queue, args.sample_size)

    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    main()
