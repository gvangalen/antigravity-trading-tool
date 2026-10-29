#!/usr/bin/env python3
"""Run a public, production-shaped FINN V2 matrix against a local stack.

This harness deliberately contains no QA manifest, protected fixture identity,
or sealed wording. It combines the public natural action chain with 22 typed
read/evaluate/guided probes for 38 cases while remaining Build-owned and
reproducible.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from time import monotonic
from urllib.parse import urlparse

from sqlalchemy import text
from redis import Redis

from backend.scripts.run_finn_v2_full_action_matrix import (
    _create_local_user, _insert_bot, _insert_setup, _insert_strategy,
    _runtime_record,
)
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.infrastructure.database import sync_engine
from backend.utils.auth_utils import create_access_token


PUBLIC_PROBES = (
    ("capability", "Wat kan FINN voor mij doen?", "capability"),
    ("concept", "What does RSI mean?", "explain_financial_concept"),
    ("off_topic", "Schrijf een gedicht over regen.", "off_topic"),
    ("active_asset", "Which asset is active?", "read_active_asset"),
    ("indicator_read", "Welche Indikatoren sind konfiguriert?", "read_indicator_configuration"),
    ("indicator_pair_weight_read", "Lees mijn opgeslagen Volume-weging voor BTC/EUR en BTC/USDT", "read_indicator_configuration"),
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
    ("setup_graph", "Toon mijn actieve plan met setup, strategie en bot.", "read_active_plan"),
    ("financial_concept_de", "Was bedeutet gleitender Durchschnitt?", "explain_financial_concept"),
    ("capability_en", "What support is available?", "capability"),
)

# Read and coaching turns use the model-led Responses tool path. They do not
# have a legacy operation_id in the public runtime projection. Assert the
# actual owner-scoped tool used, a completed answer, and absence of a write
# proposal instead of accepting a missing operation ID as success by itself.
READ_TOOLS = {
    "active_asset": "get_active_asset_context",
    "indicator_read": "get_indicator_snapshot",
    "indicator_pair_weight_read": "get_indicator_snapshot",
    "evaluate_plan": "evaluate_plan",
    "evaluate_setup": "evaluate_setup",
    "evaluate_strategy": "evaluate_strategy",
    "evaluate_bot": "evaluate_bot",
    "read_setup": ("get_active_plan_and_strategy", "get_saved_setup"),
    "read_bot": "get_saved_bots",
    "scores": "get_current_asset_scores",
    "portfolio": "get_portfolio_and_exposure",
    "indicator_evaluate": "evaluate_indicator_configuration",
    "asset_precedence": "get_active_asset_context",
    "setup_graph": "get_active_plan_and_strategy",
}
DIRECT_ANSWER_CASES = {"capability", "concept", "off_topic", "clarify", "financial_concept_de", "capability_en"}
WRITE_TOOLS = {
    "create_or_update_trade_plan_proposal", "manage_paper_bot_proposal",
    "manage_watchlist_proposal", "manage_indicator_proposal",
}


def _probe_contract(case_id: str, expected_operation: str, observed: dict, record: dict) -> tuple[bool, list[str]]:
    exchange = dict((record.get("runtime_state") or {}).get("responses_exchange") or {})
    trace = list(exchange.get("tool_trace") or [])
    names = [str(call.get("name") or "") for call in trace]
    answer = str(exchange.get("answer") or "").strip()
    no_proposal = record.get("proposal") is None
    base = (
        observed.get("polling_sse_contract_projection") is True
        and bool(answer)
        and no_proposal
        and not any(call.get("status") == "error" for call in trace)
    )
    if case_id in READ_TOOLS:
        allowed_read_tools = READ_TOOLS[case_id]
        if isinstance(allowed_read_tools, str):
            allowed_read_tools = (allowed_read_tools,)
        wrong_object_read = case_id == "indicator_pair_weight_read" and bool(
            {"get_active_plan_and_strategy", "get_saved_setup", "get_saved_setup_inventory"}.intersection(names)
        )
        return bool(base and observed.get("status") == "completed"
                    and any(tool in names for tool in allowed_read_tools)
                    and not WRITE_TOOLS.intersection(names) and not wrong_object_read), names
    if case_id in DIRECT_ANSWER_CASES:
        return bool(base and observed.get("status") == "completed"
                    and not WRITE_TOOLS.intersection(names)), names
    if case_id == "unsupported":
        # A safe clarification may consult context or prepare an incomplete
        # Paper proposal, but may never persist a proposal or execute a write.
        return bool(base and observed.get("status") in {"completed", "clarification_required"}
                    and not any(call.get("status") == "completed" and call.get("name") in WRITE_TOOLS
                                for call in trace)), names
    if case_id == "guided_setup":
        return bool(base and observed.get("status") == "clarification_required"
                    and observed.get("final_operation_id") == expected_operation
                    and "create_or_update_trade_plan_proposal" in names), names
    return False, names


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
        record = _runtime_record(observed["run_id"])
        passed, tool_names = _probe_contract(case_id, expected_operation, observed, record)
        return {
            "case_id": case_id,
            "expected_operation_id": expected_operation,
            "actual_operation_id": observed["final_operation_id"],
            "responses_tool_names": tool_names,
            "run_id": observed["run_id"],
            "terminal_status": observed["status"],
            "run_create_elapsed_ms": observed["run_create_elapsed_ms"],
            "elapsed_ms": observed["elapsed_ms"],
            "phase_timestamps": observed.get("phase_timestamps") or {},
            "dispatch_count": observed.get("dispatch_count"),
            "attempt_count": observed.get("attempt_count"),
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


def _resource_snapshot() -> dict[str, int | None]:
    """Record only capacity counters, never credentials or customer content."""
    snapshot: dict[str, int | None] = {
        "postgres_connections": None,
        "postgres_waiting": None,
        "redis_interactive_depth": None,
    }
    try:
        with sync_engine.connect() as connection:
            row = connection.execute(text("""
                SELECT count(*) AS connections,
                       count(*) FILTER (
                           WHERE state = 'active' AND wait_event IS NOT NULL
                       ) AS waiting
                FROM pg_stat_activity
                WHERE datname = current_database()
            """)).mappings().one()
            snapshot["postgres_connections"] = int(row["connections"])
            snapshot["postgres_waiting"] = int(row["waiting"])
    except Exception:
        pass
    try:
        client = Redis.from_url(__import__("os").environ["CELERY_BROKER_URL"], socket_timeout=1)
        snapshot["redis_interactive_depth"] = int(client.llen("parity-finn_interactive"))
    except Exception:
        pass
    return snapshot


def _write_atomic(path: Path, artifact: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(artifact, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _latency_summary(values: list[object]) -> dict[str, float | int | None]:
    measured = sorted(float(value) for value in values if isinstance(value, (int, float)))
    if not measured:
        return {"count": 0, "p50_ms": None, "p95_ms": None, "max_ms": None}
    # Nearest-rank p95: the same conservative convention used for release gates.
    p95_index = max(0, min(len(measured) - 1, int(__import__("math").ceil(len(measured) * 0.95)) - 1))
    return {
        "count": len(measured),
        "p50_ms": measured[(len(measured) - 1) // 2],
        "p95_ms": measured[p95_index],
        "max_ms": measured[-1],
    }


def _case_from_action_step(step: dict) -> dict:
    """Preserve the public terminal evidence from an executed write action."""
    return {
        "case_id": step["step_id"],
        "expected_operation_id": step["expected_operation_id"],
        "actual_operation_id": step["final_operation_id"],
        "run_id": step["run_id"],
        "terminal_status": step["terminal_status"],
        "run_create_elapsed_ms": step.get("run_create_elapsed_ms"),
        "elapsed_ms": step.get("elapsed_ms"),
        "phase_timestamps": step.get("phase_timestamps") or {},
        "dispatch_count": step.get("dispatch_count"),
        "attempt_count": step.get("attempt_count"),
        "polling_sse_parity": step["polling_sse_parity"],
        "initial_http_status": step.get("initial_http_status"),
        "retry_count": 0,
        "passed": step["passed"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--output", required=True)
    parser.add_argument("--probe-interval-seconds", type=float, default=3.2)
    parser.add_argument("--action-interval-seconds", type=float, default=3.2)
    parser.add_argument("--production-parity", action="store_true")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    if urlparse(base_url).hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("nonsealed_parity_matrix_requires_loopback")

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.production_parity:
        if (
            os.getenv("CELERY_QUEUE_PREFIX") != "parity-"
            or os.getenv("APP_ENV") != "local_finn"
            or os.getenv("FINN_PARITY_TOPOLOGY_ASSERTED") != "true"
        ):
            raise ValueError("production_parity_requires_isolated_prefork_stack")
    namespace = f"build-{uuid.uuid4().hex[:12]}"
    chain_path = output.with_suffix(".action-chain.json")
    chain_command = [
        sys.executable,
        str(Path(__file__).with_name("run_finn_v2_sequential_action_chain.py")),
        "--base-url", base_url,
        "--output", str(chain_path),
        "--fixture-namespace", namespace,
        "--step-interval-seconds", str(max(0.0, args.action_interval_seconds)),
    ]
    chain_result = subprocess.run(chain_command, check=False, capture_output=True, text=True)
    chain = json.loads(chain_path.read_text(encoding="utf-8")) if chain_path.exists() else {"steps": []}

    user = _create_local_user()
    # Read and evaluation probes need an actual, unique saved plan. An empty
    # user makes inventory lookup a reasonable model choice and leaves the
    # specific plan-tool contracts untestable.
    with sync_engine.begin() as connection:
        setup_id = _insert_setup(connection, user["id"], "Matrix Probe BTC Setup")
        strategy_id = _insert_strategy(connection, user["id"], setup_id, "Matrix Probe BTC Strategie")
        _insert_bot(connection, user["id"], strategy_id, "Matrix Probe BTC Paper Bot")
    token = create_access_token({"sub": str(user["id"]), "role": str(user["role"])})
    probes = []
    for item in PUBLIC_PROBES:
        probes.append(_run_probe(base_url=base_url, token=token, item=item))
        partial_cases = [_case_from_action_step(step) for step in chain.get("steps", [])] + probes
        _write_atomic(output, {
            "artifact_version": "finn_v2.public_parity_matrix.v2",
            "incomplete": True,
            "sealed_qa_material_used": False,
            "fixture_namespace": namespace,
            "planned_cases": 38,
            "executed_cases": len(partial_cases),
            "cases": partial_cases,
            "resource_snapshot": _resource_snapshot(),
            "chain_checkpoint": str(chain_path),
        })
        time.sleep(max(0.0, args.probe_interval_seconds))
    cases = [_case_from_action_step(step) for step in chain.get("steps", [])] + probes
    lineage = [step for step in chain.get("steps", []) if (step.get("identity_assertion") or {}).get("required")]
    create_latency = _latency_summary([case.get("run_create_elapsed_ms") for case in cases])
    terminal_latency = _latency_summary([case.get("elapsed_ms") for case in cases])
    all_http_200 = all(case.get("initial_http_status") == 200 for case in cases)
    action_complete = sum(bool(step.get("passed")) for step in chain.get("steps", [])) == 16
    lineage_complete = sum(bool((step.get("identity_assertion") or {}).get("passed")) for step in lineage) == 9
    latency_within_budget = (
        (create_latency["p95_ms"] or float("inf")) < 1000
        and (create_latency["max_ms"] or float("inf")) < 3000
        and (terminal_latency["p95_ms"] or float("inf")) <= 10000
        and (terminal_latency["max_ms"] or float("inf")) <= 15000
    )
    artifact = {
        "artifact_version": "finn_v2.public_parity_matrix.v3",
        "incomplete": False,
        "sealed_qa_material_used": False,
        "fixture_namespace": namespace,
        "planned_cases": 38,
        "executed_cases": len(cases),
        "cases": cases,
        "action_contracts": {"passed": sum(bool(step.get("passed")) for step in chain.get("steps", [])), "total": 16},
        "lineage": {"passed": sum(bool((step.get("identity_assertion") or {}).get("passed")) for step in lineage), "total": 9},
        "latency_ms": {"run_create": create_latency, "terminal": terminal_latency},
        "acceptance": {
            "all_original_http_200": all_http_200,
            "action_contracts_16_of_16": action_complete,
            "lineage_9_of_9": lineage_complete,
            "latency_within_budget": latency_within_budget,
        },
        "safety": dict(chain.get("safety_observability") or {}),
        "chain_exit_code": chain_result.returncode,
        "probe_interval_seconds": args.probe_interval_seconds,
        "action_interval_seconds": args.action_interval_seconds,
        "original_http_statuses": [case.get("initial_http_status") for case in cases],
        "resource_snapshot": _resource_snapshot(),
        "production_parity": args.production_parity,
        "prefork_topology_asserted": os.getenv("FINN_PARITY_TOPOLOGY_ASSERTED") == "true",
        "chain_checkpoint": str(chain_path),
        "chain_process_evidence": chain.get("persistence_boundary_summary") or {},
        "all_passed": (
            len(cases) == 38
            and all(case["passed"] for case in cases)
            and chain_result.returncode == 0
            and all_http_200
            and action_complete
            and lineage_complete
            and latency_within_budget
        ),
    }
    _write_atomic(output, artifact)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(json.dumps({"output": str(output), "sha256": digest, "all_passed": artifact["all_passed"]}, sort_keys=True))
    if not artifact["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
