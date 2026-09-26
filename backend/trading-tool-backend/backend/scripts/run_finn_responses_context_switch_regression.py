#!/usr/bin/env python3
"""Public-route regression: an open bot choice must not hijack a new turn."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.infrastructure.database import sync_engine
from backend.scripts.run_finn_v2_full_action_matrix import (
    _create_local_user, _insert_bot, _insert_setup, _insert_strategy, _runtime_record,
)
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.utils.auth_utils import create_access_token


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not args.base_url.startswith(("http://localhost:", "http://127.0.0.1:")):
        raise SystemExit("This regression is local-only")

    user = _create_local_user()
    with sync_engine.begin() as connection:
        target_setup = _insert_setup(connection, user["id"], "BTC Breakout Full")
        _insert_strategy(connection, user["id"], target_setup, "BTC Breakout Full Strategy")
        other_setup = _insert_setup(connection, user["id"], "BTC Bots Parent")
        other_strategy = _insert_strategy(connection, user["id"], other_setup, "BTC Bots Parent Strategy")
        _insert_bot(connection, user["id"], other_strategy, "BTC Alpha Paper Bot")
        _insert_bot(connection, user["id"], other_strategy, "BTC Beta Paper Bot")
    token = create_access_token({"sub": str(user["id"]), "role": "user"})
    artifact = {"synthetic_local_only": True, "cases": []}
    for new_message, expected_operation in (
        ("Verwijder mijn strategie BTC Breakout Full Strategy.", "delete_strategy"),
        ("Ik bekijk AAPL op 1D. De koersdata is verouderd. Zou je nu handelen of wachten?", None),
    ):
        first = run_gate(
            base_url=args.base_url, bearer_token=token,
            message="Verwijder mijn paper-bot; ik heb er meer dan één.", timeout_seconds=75,
        )
        next_turn = run_gate(
            base_url=args.base_url, bearer_token=token, message=new_message,
            conversation_id=first["conversation_id"], timeout_seconds=75,
        )
        record = _runtime_record(next_turn["run_id"])
        answer = str(dict(record["runtime_state"].get("terminal_response") or {}).get("content") or "")
        proposal = record["proposal"]
        checks = {
            "first_requested_bot_choice": first["status"] == "clarification_required",
            "terminal": next_turn["status"] in {"completed", "unavailable", "clarification_required"},
            "no_bot_choice_repeated": "welke paper-bot" not in answer.casefold(),
            "not_bot_action": next_turn["final_operation_id"] not in {"delete_bot", "update_bot"},
            "no_execution": not record["runtime_state"].get("action_result"),
            "polling_sse_parity": bool(next_turn["polling_sse_contract_projection"]),
            "one_dispatch_attempt": next_turn["dispatch_count"] == next_turn["attempt_count"] == 1,
        }
        if expected_operation:
            checks["strategy_operation"] = next_turn["final_operation_id"] == expected_operation
            checks["strategy_proposal_only"] = bool(proposal and proposal["target_type"] == "strategy")
        else:
            checks["no_proposal"] = proposal is None
        artifact["cases"].append({
            "first_run_id": first["run_id"], "run_id": next_turn["run_id"],
            "operation_id": next_turn["final_operation_id"],
            "status": next_turn["status"], "checks": checks, "pass": all(checks.values()),
        })
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    artifact["pass"] = all(case["pass"] for case in artifact["cases"])
    Path(args.output).write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    if not artifact["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
