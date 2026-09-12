#!/usr/bin/env python3
"""Exercise 100 real FINN runtime turns without write-capable operations."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

from backend.scripts.run_finn_v2_nonsealed_parity_matrix import _resource_snapshot
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.scripts.run_finn_v2_full_action_matrix import _create_local_user
from backend.utils.auth_utils import create_access_token


PROBES = (
    ("Wat kan FINN voor mij doen?", "capability"),
    ("What does RSI mean?", "explain_financial_concept"),
    ("Schrijf een gedicht over regen.", "off_topic"),
    ("Welche Hilfe bietet FINN?", "capability"),
)


def _write_atomic(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _runtime_resource_snapshot() -> dict:
    """Capture bounded local-capacity evidence without reading configuration secrets."""
    snapshot = _resource_snapshot()
    try:
        snapshot["runtime_cgroup_memory_bytes"] = int(
            Path("/sys/fs/cgroup/memory.current").read_text(encoding="utf-8").strip()
        )
    except (OSError, ValueError):
        snapshot["runtime_cgroup_memory_bytes"] = None
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--interval-seconds", type=float, default=3.2)
    args = parser.parse_args()
    if args.runs != 100:
        raise ValueError("runtime_endurance_requires_exactly_100_runs")
    if os.getenv("FINN_PARITY_TOPOLOGY_ASSERTED") != "true":
        raise ValueError("runtime_endurance_requires_asserted_prefork_topology")

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    user = _create_local_user()
    token = create_access_token({"sub": str(user["id"]), "role": str(user["role"])})
    snapshots = [{"after_run": 0, **_runtime_resource_snapshot()}]
    cases = []
    for index in range(args.runs):
        message, expected_operation = PROBES[index % len(PROBES)]
        started = time.monotonic()
        try:
            observed = run_gate(
                base_url=args.base_url,
                bearer_token=token,
                message=message,
                timeout_seconds=60,
            )
            passed = (
                observed["initial_operation_id"] == expected_operation
                and observed["final_operation_id"] == expected_operation
                and observed["status"] in {"completed", "downgraded", "unavailable"}
                and observed["dispatch_count"] == 1
                and observed["attempt_count"] == 1
                and observed["polling_sse_contract_projection"]
            )
            case = {
                "index": index + 1,
                "expected_operation_id": expected_operation,
                "actual_operation_id": observed["final_operation_id"],
                "run_id": observed["run_id"],
                "terminal_status": observed["status"],
                "elapsed_ms": observed["elapsed_ms"],
                "initial_http_status": observed["run_create_http_status"],
                "passed": passed,
            }
        except Exception as exc:
            case = {
                "index": index + 1,
                "expected_operation_id": expected_operation,
                "terminal_status": "runner_failure",
                "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
                "error": f"{type(exc).__name__}:{exc}",
                "passed": False,
            }
        cases.append(case)
        if (index + 1) % 10 == 0:
            snapshots.append({"after_run": index + 1, **_runtime_resource_snapshot()})
        _write_atomic(output, {
            "artifact_version": "finn_v2.runtime_endurance.v1",
            "incomplete": True,
            "runs_planned": args.runs,
            "runs_completed": len(cases),
            "write_operations": 0,
            "cases": cases,
            "resource_snapshots": snapshots,
        })
        if index + 1 < args.runs:
            time.sleep(max(0.0, args.interval_seconds))
    artifact = {
        "artifact_version": "finn_v2.runtime_endurance.v1",
        "incomplete": False,
        "runs_planned": args.runs,
        "runs_completed": len(cases),
        "write_operations": 0,
        "all_passed": all(case["passed"] for case in cases),
        "cases": cases,
        "resource_snapshots": snapshots,
    }
    _write_atomic(output, artifact)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(json.dumps({"output": str(output), "sha256": digest, "all_passed": artifact["all_passed"]}))
    if not artifact["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
