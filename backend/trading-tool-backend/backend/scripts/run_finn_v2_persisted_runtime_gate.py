#!/usr/bin/env python3
"""Exercise FINN V2 through its public persisted worker lifecycle.

This gate deliberately uses the authenticated HTTP API instead of internal
services: gateway, run creation, outbox dispatch, worker, polling and SSE all
remain part of the observed path. It never confirms or executes an action.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Tuple


TERMINAL_STATUSES = {
    "completed", "clarification_required", "unavailable", "downgraded",
    "rejected", "blocked", "failed", "canceled",
}


def _request_json(*, url: str, method: str, headers: Dict[str, str], body: Dict[str, Any] | None, timeout: float) -> Tuple[Dict[str, Any], int]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8")), int(response.status)
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read().decode("utf-8") or "{}"), int(exc.code)


def _terminal_sse(*, url: str, headers: Dict[str, str], timeout: float) -> Dict[str, Any]:
    request = urllib.request.Request(url, headers={**headers, "Accept": "text/event-stream"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        event_name = None
        payload = None
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if line.startswith("event: "):
                event_name = line[7:]
            elif line.startswith("data: "):
                payload = json.loads(line[6:])
            elif not line and event_name and payload is not None:
                if payload.get("status") in TERMINAL_STATUSES:
                    return payload
                event_name = None
                payload = None
    raise AssertionError("runtime_gate_missing_terminal_sse_envelope")


def run_gate(*, base_url: str, bearer_token: str, message: str, timeout_seconds: float) -> Dict[str, Any]:
    if not bearer_token.strip():
        raise ValueError("runtime_gate_requires_explicit_qa_bearer_token")
    base_url = base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {bearer_token}", "Content-Type": "application/json"}
    started_at = time.monotonic()
    created, status = _request_json(
        url=f"{base_url}/api/assistant/v2/runs",
        method="POST",
        headers=headers,
        body={"message": message, "transport": "chat"},
        timeout=timeout_seconds,
    )
    if status != 200:
        raise AssertionError(f"runtime_gate_create_failed_http_{status}")
    run_id = str(created.get("run_id") or "")
    contract = dict((created.get("runtime_trace") or {}).get("contract") or {})
    if not run_id or contract.get("run_id") != run_id or not contract.get("contract_id"):
        raise AssertionError("runtime_gate_contract_missing_at_run_creation")

    polling: Dict[str, Any] = created
    while time.monotonic() - started_at < timeout_seconds:
        polling, status = _request_json(
            url=f"{base_url}/api/assistant/v2/runs/{run_id}",
            method="GET",
            headers=headers,
            body=None,
            timeout=min(5.0, timeout_seconds),
        )
        if status != 200:
            raise AssertionError(f"runtime_gate_poll_failed_http_{status}")
        if polling.get("status") in TERMINAL_STATUSES:
            break
        time.sleep(0.25)
    else:
        raise TimeoutError("runtime_gate_timeout")

    sse = _terminal_sse(
        url=f"{base_url}/api/assistant/v2/runs/{run_id}/stream",
        headers=headers,
        timeout=min(5.0, timeout_seconds),
    )
    if sse != polling:
        raise AssertionError("runtime_gate_polling_sse_envelope_mismatch")
    projection = dict(polling.get("runtime_trace") or {})
    if projection.get("contract_id") != contract["contract_id"]:
        raise AssertionError("runtime_gate_terminal_projection_contract_mismatch")
    if projection.get("terminal_projection") == "legacy_compact":
        raise AssertionError("runtime_gate_legacy_compact_for_new_run")
    return {
        "run_id": run_id,
        "contract_id": contract["contract_id"],
        "status": polling["status"],
        "initial_operation_id": projection.get("initial_operation_id"),
        "final_operation_id": projection.get("final_operation_id"),
        "canonical_target": projection.get("canonical_target"),
        "elapsed_ms": round((time.monotonic() - started_at) * 1000, 2),
        "polling_sse_contract_projection": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--token-env", default="FINN_QA_BEARER_TOKEN")
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    args = parser.parse_args()
    print(json.dumps(run_gate(
        base_url=args.base_url,
        bearer_token=os.environ.get(args.token_env, ""),
        message=args.message,
        timeout_seconds=args.timeout_seconds,
    ), sort_keys=True))


if __name__ == "__main__":
    main()
