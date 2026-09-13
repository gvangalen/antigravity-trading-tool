#!/usr/bin/env python3
"""Run the public 48-contract FINN acceptance matrix on an isolated stack.

The runner combines the expressly declassified acceptance records with the
nine registry contracts not represented there.  It never opens a QA-owned
manifest: every request is either a committed declassified regression or a
generic public probe.  It delegates delivery to ``run_gate`` so Build and QA
exercise the same public run/poll/SSE path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import uuid
from pathlib import Path
from time import monotonic, sleep
from urllib.parse import urlparse

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.scripts.run_finn_v2_full_action_matrix import _create_local_user, _runtime_record, _seed_fixtures
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.utils.auth_utils import create_access_token


# These generic probes cover only contracts absent from the declassified
# artifact.  Expected operation, polarity and inputs remain registry-owned.
PUBLIC_REMAINDER = (
    ("public-40-evaluate-portfolio", "Evaluate my portfolio with the available evidence.", "evaluate_portfolio"),
    ("public-41-evaluate-setup", "Evaluate my active setup.", "evaluate_setup"),
    ("public-42-evaluate-strategy", "Bewerte meine aktive Strategie.", "evaluate_strategy"),
    ("public-43-off-topic", "Write a short poem about rain.", "off_topic"),
    ("public-44-read-active-asset", "Welke asset is actief?", "read_active_asset"),
    ("public-45-read-indicator", "Show my RSI configuration.", "read_indicator_configuration"),
    ("public-46-read-scores", "Zeig mir meine Scores.", "read_scores"),
    ("public-47-read-watchlist", "Toon mijn watchlist.", "read_watchlist"),
    ("public-48-unsupported", "Buy BTC automatically without confirmation.", "unsupported_financial_operation"),
)


def _write_atomic(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _run_remainder(*, base_url: str, token: str, item: tuple[str, str, str]) -> dict:
    case_id, message, operation_id = item
    started = monotonic()
    try:
        observed = run_gate(base_url=base_url, bearer_token=token, message=message, timeout_seconds=60)
        projection = _runtime_record(observed["run_id"])["terminal_projection"]
        contract = FinnV2OperationRegistry().require_supported(operation_id)
        checks = {
            "http_200": observed["run_create_http_status"] == 200,
            "initial_operation": observed["initial_operation_id"] == operation_id,
            "final_operation": observed["final_operation_id"] == operation_id,
            "polarity": projection.get("action_polarity") == contract.action_polarity.value,
            "runtime_contract": bool(projection.get("contract_id")),
            "single_dispatch": projection.get("dispatch_count") == 1,
            "single_attempt": projection.get("attempt_count") == 1,
            "polling_sse": observed["polling_sse_contract_projection"],
        }
        return {
            "case_id": case_id,
            "classification": "PUBLIC_REMAINDER",
            "expected_operation_id": operation_id,
            "expected_action_polarity": contract.action_polarity.value,
            "run_id": observed["run_id"],
            "runtime_contract_id": projection.get("contract_id"),
            "initial_http_status": observed["run_create_http_status"],
            "initial_operation_id": observed["initial_operation_id"],
            "final_operation_id": observed["final_operation_id"],
            "terminal_status": observed["status"],
            "required_inputs": projection.get("required_inputs"),
            "supplied_inputs": projection.get("supplied_inputs"),
            "missing_inputs": projection.get("missing_inputs"),
            "dispatch_count": projection.get("dispatch_count"),
            "attempt_count": projection.get("attempt_count"),
            "polling_sse_parity": observed["polling_sse_contract_projection"],
            "elapsed_ms": observed["elapsed_ms"],
            "checks": checks,
            "passed": all(checks.values()),
        }
    except Exception as exc:
        return {
            "case_id": case_id,
            "classification": "PUBLIC_REMAINDER",
            "expected_operation_id": operation_id,
            "initial_http_status": None,
            "elapsed_ms": int((monotonic() - started) * 1000),
            "error_category": type(exc).__name__,
            "error": str(exc),
            "passed": False,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--case-interval-seconds",
        type=float,
        default=3.2,
        help="Production-shaped pacing shared with the QA matrix engine.",
    )
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    if urlparse(base_url).hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("public_acceptance_matrix_requires_loopback")

    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    declassified_path = output.with_suffix(".declassified.json")
    command = [
        sys.executable,
        str(Path(__file__).with_name("run_finn_v2_declassified_347462_acceptance.py")),
        "--base-url", base_url,
        "--output", str(declassified_path),
        "--case-interval-seconds", str(max(0.0, args.case_interval_seconds)),
    ]
    delegated = subprocess.run(command, check=False, capture_output=True, text=True)
    declassified = json.loads(declassified_path.read_text(encoding="utf-8")) if declassified_path.exists() else {"cases": []}

    user = _create_local_user()
    _seed_fixtures(int(user["id"]))
    token = create_access_token({"sub": str(user["id"]), "role": str(user["role"])})
    cases = list(declassified.get("cases") or [])
    fixture_namespace = f"build-{uuid.uuid4().hex[:12]}"
    for item in PUBLIC_REMAINDER:
        cases.append(_run_remainder(base_url=base_url, token=token, item=item))
        _write_atomic(output, {
            "artifact_version": "finn_v2.public_action_contract_acceptance.v1",
            "sealed_qa_material_used": False,
            "fixture_namespace": fixture_namespace,
            "planned_cases": 48,
            "attempted_cases": len(cases),
            "incomplete": True,
            "cases": cases,
        })
        sleep(max(0.0, args.case_interval_seconds))

    registry_ids = {contract.operation_id for contract in FinnV2OperationRegistry().list()}
    observed_ids = {case.get("expected_operation_id") for case in cases}
    artifact = {
        "artifact_version": "finn_v2.public_action_contract_acceptance.v1",
        "sealed_qa_material_used": False,
        "fixture_namespace": fixture_namespace,
        "planned_cases": 48,
        "attempted_cases": len(cases),
        "completed_cases": len(cases),
        "passed_cases": sum(bool(case.get("passed")) for case in cases),
        "incomplete": False,
        "declassified_runner_exit_code": delegated.returncode,
        "registry_coverage": sorted(observed_ids) == sorted(registry_ids),
        "cases": cases,
    }
    _write_atomic(output, artifact)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(json.dumps({"output": str(output), "sha256": digest, "passed": artifact["passed_cases"], "total": len(cases)}))
    if delegated.returncode or artifact["passed_cases"] != 48 or not artifact["registry_coverage"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
