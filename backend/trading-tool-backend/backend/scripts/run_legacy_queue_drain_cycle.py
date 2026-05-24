"""Run a bounded legacy default-queue drain in measured batches.

Usage examples:
    python3 backend/scripts/run_legacy_queue_drain_cycle.py
    python3 backend/scripts/run_legacy_queue_drain_cycle.py --apply --max-runs 5 --limit-per-run 1000
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.celery_task.queue_policy import DEFAULT_QUEUE
from backend.scripts.drain_legacy_celery_queue import (
    drain_legacy_queue,
    inspect_legacy_queue,
)


logger = logging.getLogger(__name__)


def _operator_summary(
    *,
    initial_sample: Dict[str, Any],
    final_sample: Dict[str, Any],
    totals: Dict[str, int],
    stop_reason: str,
) -> Dict[str, Any]:
    return {
        "reroute_ratio_before": float(initial_sample.get("reroute_ratio") or 0.0),
        "reroute_ratio_after": float(final_sample.get("reroute_ratio") or 0.0),
        "processed": int(totals.get("processed") or 0),
        "rerouted": int(totals.get("rerouted") or 0),
        "kept": int(totals.get("kept") or 0),
        "top_tasks_before": list(initial_sample.get("top_tasks") or []),
        "top_tasks_after": list(final_sample.get("top_tasks") or []),
        "stop_reason": stop_reason,
    }


def write_result_artifact(
    result: Dict[str, Any],
    *,
    output_dir: Optional[str] = None,
    output_file: Optional[str] = None,
) -> Optional[str]:
    if not output_dir and not output_file:
        return None

    if output_file:
        target = Path(output_file)
    else:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        mode = "apply" if result.get("apply") else "inspect"
        queue_name = str(result.get("queue") or DEFAULT_QUEUE).replace("/", "_")
        target = Path(output_dir) / f"legacy-queue-drain-{queue_name}-{mode}-{timestamp}.json"

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(target)


def run_drain_cycle(
    queue_name: str,
    *,
    apply: bool,
    sample_size: int,
    max_runs: int,
    limit_per_run: int,
    runtime_cap_seconds: float,
    sleep_seconds: float,
    min_reroute_ratio: float,
    max_processed_total: Optional[int] = None,
    max_rerouted_total: Optional[int] = None,
) -> Dict[str, Any]:
    runs: List[Dict[str, Any]] = []
    totals = {
        "processed": 0,
        "rerouted": 0,
        "kept": 0,
    }

    initial_sample = inspect_legacy_queue(queue_name, sample_size)
    final_sample = initial_sample
    stop_reason = "max_runs_reached"

    for run_index in range(1, max_runs + 1):
        sample = inspect_legacy_queue(queue_name, sample_size)
        final_sample = sample
        reroute_ratio = float(sample.get("reroute_ratio") or 0.0)
        total_depth = int(sample.get("total_depth") or 0)

        if total_depth <= 0:
            stop_reason = "queue_empty"
            break

        if sample.get("rerouteable_count", 0) <= 0:
            stop_reason = "no_rerouteable_messages"
            break

        if reroute_ratio < min_reroute_ratio:
            stop_reason = "reroute_ratio_below_threshold"
            break

        if max_processed_total is not None and totals["processed"] >= max_processed_total:
            stop_reason = "max_processed_total_reached"
            break

        if max_rerouted_total is not None and totals["rerouted"] >= max_rerouted_total:
            stop_reason = "max_rerouted_total_reached"
            break

        requested_limit = limit_per_run
        if max_processed_total is not None:
            requested_limit = min(requested_limit, max_processed_total - totals["processed"])
        if requested_limit <= 0:
            stop_reason = "max_processed_total_reached"
            break

        run_result = {
            "run": run_index,
            "sample_before": sample,
        }
        if apply:
            drain_result = drain_legacy_queue(
                queue_name,
                requested_limit,
                runtime_cap_seconds=runtime_cap_seconds,
            )
        else:
            drain_result = {
                "queue": queue_name,
                "limit_requested": requested_limit,
                "runtime_cap_seconds": runtime_cap_seconds,
                "elapsed_seconds": 0.0,
                "stop_reason": "inspect_only",
                "processed": 0,
                "rerouted": 0,
                "kept": 0,
                "remaining_depth": total_depth,
                "rerouted_by_target": {},
                "before_queue_depths": {},
                "after_queue_depths": {},
            }

        run_result["drain"] = drain_result
        runs.append(run_result)

        totals["processed"] += int(drain_result.get("processed") or 0)
        totals["rerouted"] += int(drain_result.get("rerouted") or 0)
        totals["kept"] += int(drain_result.get("kept") or 0)

        final_sample = inspect_legacy_queue(queue_name, sample_size)

        if max_rerouted_total is not None and totals["rerouted"] >= max_rerouted_total:
            stop_reason = "max_rerouted_total_reached"
            break

        if max_processed_total is not None and totals["processed"] >= max_processed_total:
            stop_reason = "max_processed_total_reached"
            break

        if not apply:
            stop_reason = "inspect_only"
            break

        if sleep_seconds > 0 and run_index < max_runs:
            time.sleep(sleep_seconds)
    else:
        stop_reason = "max_runs_reached"

    return {
        "queue": queue_name,
        "apply": apply,
        "sample_size": sample_size,
        "max_runs": max_runs,
        "limit_per_run": limit_per_run,
        "runtime_cap_seconds": runtime_cap_seconds,
        "sleep_seconds": sleep_seconds,
        "min_reroute_ratio": min_reroute_ratio,
        "max_processed_total": max_processed_total,
        "max_rerouted_total": max_rerouted_total,
        "stop_reason": stop_reason,
        "initial_sample": initial_sample,
        "final_sample": final_sample,
        "operator_summary": _operator_summary(
            initial_sample=initial_sample,
            final_sample=final_sample,
            totals=totals,
            stop_reason=stop_reason,
        ),
        "totals": totals,
        "runs": runs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run bounded legacy default-queue drain cycles.")
    parser.add_argument("--queue", default=DEFAULT_QUEUE, help="Source queue to inspect/drain.")
    parser.add_argument("--sample-size", type=int, default=100, help="How many oldest messages to sample before each run.")
    parser.add_argument("--max-runs", type=int, default=3, help="Maximum drain runs in one cycle.")
    parser.add_argument("--limit-per-run", type=int, default=1000, help="Maximum messages to process per run.")
    parser.add_argument("--runtime-cap-seconds", type=float, default=15.0, help="Maximum runtime for one drain run.")
    parser.add_argument("--sleep-seconds", type=float, default=1.0, help="Pause between runs when applying.")
    parser.add_argument("--min-reroute-ratio", type=float, default=0.5, help="Stop if rerouteable ratio falls below this threshold.")
    parser.add_argument("--max-processed-total", type=int, default=None, help="Optional cap across the whole cycle.")
    parser.add_argument("--max-rerouted-total", type=int, default=None, help="Optional reroute cap across the whole cycle.")
    parser.add_argument("--output-dir", default=None, help="Optional directory for timestamped JSON artifacts.")
    parser.add_argument("--output-file", default=None, help="Optional explicit JSON artifact path.")
    parser.add_argument("--apply", action="store_true", help="Actually reroute messages instead of only inspecting.")
    args = parser.parse_args()

    result = run_drain_cycle(
        args.queue,
        apply=args.apply,
        sample_size=args.sample_size,
        max_runs=args.max_runs,
        limit_per_run=args.limit_per_run,
        runtime_cap_seconds=args.runtime_cap_seconds,
        sleep_seconds=args.sleep_seconds,
        min_reroute_ratio=args.min_reroute_ratio,
        max_processed_total=args.max_processed_total,
        max_rerouted_total=args.max_rerouted_total,
    )
    artifact_path = write_result_artifact(
        result,
        output_dir=args.output_dir,
        output_file=args.output_file,
    )
    if artifact_path:
        result["artifact_path"] = artifact_path
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    main()
