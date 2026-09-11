#!/usr/bin/env python3
"""Run a public, production-shaped FINN V2 matrix against a local stack.

This harness deliberately contains no QA manifest, protected fixture identity,
or sealed wording. It combines the public natural action chain with 21 typed
read/evaluate/guided probes, so the matrix has the same 37-case shape as the
production gate while remaining Build-owned and reproducible.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
from time import monotonic
from urllib.parse import urlparse

from backend.scripts.run_finn_v2_full_action_matrix import _create_local_user
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.utils.auth_utils import create_access_token


PUBLIC_PROBES = (
    ("capability", "Wat kan FINN voor mij doen?", "capability"),
    ("concept", "What does RSI mean?", "explain_financial_concept"),
    ("off_topic", "Schrijf een gedicht over regen.", "off_topic"),
    ("active_asset", "Which asset is active?", "read_active_asset"),
    ("indicator_read", "Welche Indikatoren sind konfiguriert?", "read_indicator_configuration"),
    ("evaluate_plan", "Beoordeel mijn actieve plan eerlijk.", "evaluate_plan"),
    ("evaluate_setup", "Evaluate my current setup.", "evaluate_setup"),
    ("evaluate_strategy", "Bewerte meine aktive Strategie.", "evaluate_strategy"),
    ("evaluate_bot", "Wat zijn de risico's van mijn bot?", "evaluate_bot"),
    ("unsupported", "Koop zonder voorstel automatisch BTC voor mijn beleggingsrekening.", "unsupported_financial_operation"),
    ("clarify", "Doe hetzelfde ermee.", "clarify_request"),
    ("guided_setup", "Create a swing setup for ETH.", "create_setup"),
    ("read_setup", "Toon mijn actieve setup.", "read_active_setup"),
    ("read_bot", "Show the bot linked to my strategy.", "read_linked_bot"),
    ("scores", "Zeig mir meine Scores.", "read_scores"),
    ("portfolio", "Read my portfolio summary.", "read_portfolio"),
    ("indicator_evaluate", "Beoordeel mijn RSI-configuratie.", "evaluate_indicator_configuration"),
    ("asset_precedence", "Welke asset is actief als ik ETH noem?", "read_active_asset"),
    ("setup_graph", "Toon setup, strategie en bot samen.", "read_active_plan"),
    ("financial_concept_de", "Was bedeutet gleitender Durchschnitt?", "explain_financial_concept"),
    ("capability_en", "What support is available?", "capability"),
)


def _run_probe(*, base_url: str, token: str, item: tuple[str, str, str]) -> dict:
    case_id, message, expected_operation = item
    started = monotonic()
    try:
        observed = run_gate(
            base_url=base_url,
            bearer_token=token,
            message=message,
            timeout_seconds=60,
        )
        passed = (
            observed["initial_operation_id"] == expected_operation
            and observed["final_operation_id"] == expected_operation
            and observed["status"] in {"completed", "downgraded", "unavailable", "failed"}
            and observed["polling_sse_contract_projection"]
        )
        return {
            "case_id": case_id,
            "expected_operation_id": expected_operation,
            "actual_operation_id": observed["final_operation_id"],
            "run_id": observed["run_id"],
            "terminal_status": observed["status"],
            "elapsed_ms": observed["elapsed_ms"],
            "polling_sse_parity": observed["polling_sse_contract_projection"],
            "initial_http_status": 200,
            "retry_count": 0,
            "passed": passed,
        }
    except Exception as exc:
        return {
            "case_id": case_id,
            "expected_operation_id": expected_operation,
            "actual_operation_id": None,
            "run_id": None,
            "terminal_status": "runner_failure",
            "elapsed_ms": int((monotonic() - started) * 1000),
            "polling_sse_parity": False,
            "error": f"{type(exc).__name__}:{exc}",
            "initial_http_status": int(str(exc).rsplit("_", 1)[-1]) if "_http_" in str(exc) and str(exc).rsplit("_", 1)[-1].isdigit() else None,
            "retry_count": 0,
            "passed": False,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--output", required=True)
    parser.add_argument("--probe-interval-seconds", type=float, default=3.2)
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    if urlparse(base_url).hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("nonsealed_parity_matrix_requires_loopback")

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    namespace = f"build-{uuid.uuid4().hex[:12]}"
    chain_path = output.with_suffix(".action-chain.json")
    chain_command = [
        sys.executable,
        str(Path(__file__).with_name("run_finn_v2_sequential_action_chain.py")),
        "--base-url", base_url,
        "--output", str(chain_path),
        "--fixture-namespace", namespace,
    ]
    chain_result = subprocess.run(chain_command, check=False, capture_output=True, text=True)
    chain = json.loads(chain_path.read_text(encoding="utf-8")) if chain_path.exists() else {"steps": []}

    user = _create_local_user()
    token = create_access_token({"sub": str(user["id"]), "role": str(user["role"])})
    probes = []
    for item in PUBLIC_PROBES:
        probes.append(_run_probe(base_url=base_url, token=token, item=item))
        time.sleep(max(0.0, args.probe_interval_seconds))
    cases = [
        {
            "case_id": step["step_id"],
            "expected_operation_id": step["expected_operation_id"],
            "actual_operation_id": step["final_operation_id"],
            "run_id": step["run_id"],
            "terminal_status": step["terminal_status"],
            "elapsed_ms": None,
            "polling_sse_parity": step["polling_sse_parity"],
            "passed": step["passed"],
        }
        for step in chain.get("steps", [])
    ] + probes
    lineage = [step for step in chain.get("steps", []) if (step.get("identity_assertion") or {}).get("required")]
    artifact = {
        "artifact_version": "finn_v2.public_parity_matrix.v1",
        "sealed_qa_material_used": False,
        "fixture_namespace": namespace,
        "planned_cases": 37,
        "executed_cases": len(cases),
        "cases": cases,
        "action_contracts": {"passed": sum(bool(step.get("passed")) for step in chain.get("steps", [])), "total": 16},
        "lineage": {"passed": sum(bool((step.get("identity_assertion") or {}).get("passed")) for step in lineage), "total": 9},
        "safety": {
            "broker_orders": chain.get("broker_orders", 0),
            "live_trading_calls": chain.get("live_trading_calls", 0),
            "live_bot_activation_calls": chain.get("live_bot_activation_calls", 0),
        },
        "chain_exit_code": chain_result.returncode,
        "probe_interval_seconds": args.probe_interval_seconds,
        "original_http_statuses": [case.get("initial_http_status") for case in probes],
        "all_passed": len(cases) == 37 and all(case["passed"] for case in cases),
    }
    output.write_text(json.dumps(artifact, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(json.dumps({"output": str(output), "sha256": digest, "all_passed": artifact["all_passed"]}, sort_keys=True))
    if not artifact["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
