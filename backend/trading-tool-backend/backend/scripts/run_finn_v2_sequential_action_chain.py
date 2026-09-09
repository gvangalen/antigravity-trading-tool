#!/usr/bin/env python3
"""Exercise FINN's natural-language action chain without downstream fixtures.

Each dependent object is created by a confirmed, safe local execution and is
then referenced only by its user-facing name in a new FINN run.  Database reads
verify the resulting identity; they never provide an ID to a user message.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import uuid

from sqlalchemy import text

from backend.infrastructure.database import sync_engine
from backend.scripts.run_finn_v2_full_action_matrix import (
    _create_local_user,
    _proposal_lifecycle,
    _runtime_record,
)
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.utils.auth_utils import create_access_token


def _lookup(connection, query: str, user_id: int, name: str) -> dict[str, Any] | None:
    row = connection.execute(text(query), {"user_id": user_id, "name": name}).mappings().one_or_none()
    return dict(row) if row else None


def _created_objects(user_id: int, names: dict[str, str]) -> dict[str, Any]:
    with sync_engine.connect() as connection:
        return {
            "indicator": _lookup(connection, """
                SELECT id, indicator, category, symbol FROM user_indicator_configs
                WHERE user_id = :user_id AND indicator = :name ORDER BY id DESC LIMIT 1
            """, user_id, "rsi"),
            "setup": _lookup(connection, """
                SELECT id, name, symbol, timeframe, setup_type FROM setups
                WHERE user_id = :user_id AND name = :name
            """, user_id, names["setup"]),
            "strategy": _lookup(connection, """
                SELECT id, name, setup_id, execution_mode FROM strategies
                WHERE user_id = :user_id AND name = :name
            """, user_id, names["strategy"]),
            "bot": _lookup(connection, """
                SELECT id, name, strategy_id, is_active, is_live FROM bot_configs
                WHERE user_id = :user_id AND name = :name
            """, user_id, names["bot"]),
        }


def _run_action(*, base_url: str, token: str, other_token: str, message: str, operation_id: str) -> dict[str, Any]:
    observed = run_gate(base_url=base_url, bearer_token=token, message=message, timeout_seconds=75)
    record = _runtime_record(observed["run_id"])
    projection = record["terminal_projection"]
    proposal = record["proposal"]
    outcome: dict[str, Any] = {
        "message": message,
        "expected_operation_id": operation_id,
        "initial_operation_id": observed["initial_operation_id"],
        "final_operation_id": observed["final_operation_id"],
        "run_id": observed["run_id"],
        "runtime_contract_id": record["runtime_contract_id"],
        "supplied_inputs": projection.get("supplied_inputs"),
        "missing_inputs": projection.get("missing_inputs"),
        "dispatch_count": projection.get("dispatch_count"),
        "attempt_count": projection.get("attempt_count"),
        "terminal_status": observed["status"],
        "terminal_reason": projection.get("terminal_reason"),
        "polling_sse_parity": observed["polling_sse_contract_projection"],
        "proposal_id": proposal.get("id") if proposal else None,
    }
    if proposal:
        outcome["proposal_lifecycle"] = _proposal_lifecycle(base_url, token, other_token, proposal)
    lifecycle = outcome.get("proposal_lifecycle") or {}
    outcome["passed"] = all((
        outcome["initial_operation_id"] == operation_id,
        outcome["final_operation_id"] == operation_id,
        not outcome["missing_inputs"],
        bool(outcome["runtime_contract_id"]),
        outcome["dispatch_count"] == 1,
        outcome["attempt_count"] == 1,
        outcome["polling_sse_parity"],
        lifecycle.get("confirmed") is True,
        lifecycle.get("execution_result") == "succeeded",
        lifecycle.get("idempotency_result") == "already_executed",
    ))
    return outcome


def _prior_object_id(steps: list[dict[str, Any]], object_type: str) -> int | None:
    """Return the last persisted identity while it still existed in the chain."""
    for step in reversed(steps):
        candidate = (step.get("objects_after_step") or {}).get(object_type)
        if candidate and candidate.get("id") is not None:
            return int(candidate["id"])
    return None


def _assert_resolved_identity(step_id: str, result: dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, Any]:
    """Prove a natural-language reference resolved to the prior owned object."""
    input_name_by_step = {
        "setup_update": ("setup", "setup_id"),
        "strategy_create": ("setup", "setup_id"),
        "strategy_update": ("strategy", "strategy_id"),
        "bot_create": ("strategy", "strategy_id"),
        "bot_update": ("bot", "bot_id"),
        "bot_deactivate": ("bot", "bot_id"),
        "bot_delete": ("bot", "bot_id"),
        "strategy_delete": ("strategy", "strategy_id"),
        "setup_delete": ("setup", "setup_id"),
    }
    expected = input_name_by_step.get(step_id)
    if expected is None:
        return {"required": False, "passed": True}
    object_type, input_name = expected
    expected_id = _prior_object_id(steps, object_type)
    actual_id = (result.get("supplied_inputs") or {}).get(input_name)
    assertion = {
        "required": True,
        "object_type": object_type,
        "input_name": input_name,
        "expected_prior_object_id": expected_id,
        "resolved_object_id": actual_id,
        "passed": expected_id is not None and actual_id == expected_id,
    }
    result["passed"] = result["passed"] and assertion["passed"]
    return assertion


def _specifications(names: dict[str, str]) -> tuple[tuple[str, str, str], ...]:
    """Natural-language steps; object IDs never enter these user messages."""
    return (
        ("select_asset", "Selecteer SOL als mijn actieve asset.", "select_asset"),
        ("watchlist_add", "Voeg SOL toe aan mijn watchlist.", "watchlist_add"),
        ("watchlist_remove", "Verwijder SOL weer uit mijn watchlist.", "watchlist_remove"),
        ("indicator_create", "Maak een technische RSI indicatorconfiguratie voor SOL.", "create_indicator_configuration"),
        ("indicator_update", "Werk mijn RSI indicatorconfiguratie voor SOL bij en zet de periode naar 21.", "update_indicator_configuration"),
        ("indicator_delete", "Verwijder mijn RSI indicatorconfiguratie voor SOL.", "delete_indicator_configuration"),
        ("setup_create", f"Maak een dagelijkse DCA setup voor SOL op 4 uur met de naam {names['setup']}.", "create_setup"),
        ("setup_update", f"Werk de setup {names['setup']} bij en zet het tijdframe naar 1 uur.", "update_setup"),
        ("strategy_create", f"Maak een fixed strategie voor setup {names['setup']} met een basisinleg van 100 euro en de naam {names['strategy']}.", "create_strategy"),
        ("strategy_update", f"Werk de strategie {names['strategy']} bij en zet de basisinleg naar 120 euro.", "update_strategy"),
        ("bot_create", f"Maak een paper bot voor strategie {names['strategy']} met de naam {names['bot']}.", "create_bot"),
        ("bot_update", f"Werk de bot {names['bot']} bij en zet de cadence naar weekly.", "update_bot"),
        ("bot_deactivate", f"Deactiveer de bot {names['bot']}.", "deactivate_bot"),
        ("bot_delete", f"Verwijder de bot {names['bot']}.", "delete_bot"),
        ("strategy_delete", f"Verwijder de strategie {names['strategy']}.", "delete_strategy"),
        ("setup_delete", f"Verwijder de setup {names['setup']}.", "delete_setup"),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--output", required=True)
    parser.add_argument("--step-index", type=int, help="Run one persisted chain step (zero based).")
    parser.add_argument("--read-regressions", action="store_true", help="Run persisted evaluate and bot-consequence checks after a completed chain.")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    if urlparse(base_url).hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("sequential_action_chain_requires_loopback_base_url")

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.read_regressions:
        if not output.exists():
            raise ValueError("read_regressions_requires_completed_chain_artifact")
        artifact = json.loads(output.read_text(encoding="utf-8"))
        if len(artifact.get("steps") or []) != 16 or artifact.get("passed") != 16:
            raise ValueError("read_regressions_requires_passing_completed_chain")
        primary = {"id": artifact["user_id"], "role": "user"}
        other = {"id": artifact["other_user_id"], "role": "user"}
        names = dict(artifact["names"])
        steps = list(artifact["steps"])
        selected_specs = ()
    elif args.step_index is not None:
        if not 0 <= args.step_index < 16:
            raise ValueError("step_index_out_of_range")
        if output.exists():
            artifact = json.loads(output.read_text(encoding="utf-8"))
            primary = {"id": artifact["user_id"], "role": "user"}
            other = {"id": artifact["other_user_id"], "role": "user"}
            names = dict(artifact["names"])
            steps = list(artifact["steps"])
        else:
            primary, other = _create_local_user(), _create_local_user()
            suffix = uuid.uuid4().hex[:8]
            names = {
                "indicator": f"chain_rsi_{suffix}",
                "setup": f"Chain DCA Setup {suffix}",
                "strategy": f"Chain Strategy {suffix}",
                "bot": f"Chain Bot {suffix}",
            }
            steps = []
        if len(steps) != args.step_index:
            raise ValueError("sequential_step_order_violation")
        selected_specs = (_specifications(names)[args.step_index],)
    else:
        primary, other = _create_local_user(), _create_local_user()
        suffix = uuid.uuid4().hex[:8]
        names = {
            "indicator": f"chain_rsi_{suffix}",
            "setup": f"Chain DCA Setup {suffix}",
            "strategy": f"Chain Strategy {suffix}",
            "bot": f"Chain Bot {suffix}",
        }
        steps = []
        selected_specs = _specifications(names)
    user_id = int(primary["id"])
    token = create_access_token({"sub": str(user_id), "role": "user"})
    other_token = create_access_token({"sub": str(other["id"]), "role": "user"})
    for step_id, message, operation_id in selected_specs:
        result = _run_action(
            base_url=base_url, token=token, other_token=other_token,
            message=message, operation_id=operation_id,
        )
        result["step_id"] = step_id
        result["objects_after_step"] = _created_objects(user_id, names)
        result["identity_assertion"] = _assert_resolved_identity(step_id, result, steps)
        steps.append(result)

    read_regressions: list[dict[str, Any]] = list(artifact.get("read_regressions") or []) if args.read_regressions else []
    if args.read_regressions:
        evaluate = run_gate(
            base_url=base_url,
            bearer_token=token,
            message="Beoordeel mijn huidige plan en noem de belangrijkste ontbrekende informatie.",
            timeout_seconds=75,
        )
        consequence = run_gate(
            base_url=base_url,
            bearer_token=token,
            message="Welke gevolgen heeft die beoordeling voor mijn bot?",
            conversation_id=evaluate["conversation_id"],
            timeout_seconds=75,
        )
        read_regressions = [
            {
                "case_id": "evaluate_plan_terminalization",
                "expected_operation_id": "evaluate_plan",
                "actual": evaluate,
                "passed": evaluate["initial_operation_id"] == "evaluate_plan"
                and evaluate["final_operation_id"] == "evaluate_plan"
                and evaluate["status"] in {"completed", "downgraded", "unavailable", "failed"},
            },
            {
                "case_id": "bot_consequence_contract",
                "expected_operation_id": "evaluate_bot",
                "actual": consequence,
                "passed": consequence["initial_operation_id"] == "evaluate_bot"
                and consequence["final_operation_id"] == "evaluate_bot"
                and consequence["status"] in {"completed", "downgraded", "unavailable", "failed"},
            },
        ]

    artifact = {
        "artifact_version": "finn_v2.sequential_action_chain.v2",
        "synthetic_local_only": True,
        "downstream_fixtures_seeded": False,
        "user_id": user_id,
        "other_user_id": int(other["id"]),
        "names": names,
        "steps": steps,
        "read_regressions": read_regressions,
        "passed": sum(item["passed"] for item in steps),
        "total": len(steps),
        "broker_orders": 0,
        "live_trading_calls": 0,
        "live_bot_activation_calls": 0,
    }
    output.write_text(json.dumps(artifact, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(json.dumps({"output": str(output), "sha256": digest, "passed": artifact["passed"], "total": artifact["total"]}, sort_keys=True))
    if args.step_index is None and not args.read_regressions and artifact["passed"] != artifact["total"]:
        raise SystemExit(1)
    if args.step_index is not None and not steps[-1]["passed"]:
        raise SystemExit(1)
    if args.read_regressions and not all(item["passed"] for item in read_regressions):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
