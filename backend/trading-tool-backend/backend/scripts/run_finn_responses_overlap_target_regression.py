#!/usr/bin/env python3
"""Public-route regression for a strategy whose name contains its setup name."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import text

from backend.infrastructure.database import sync_engine
from backend.scripts.run_finn_v2_full_action_matrix import (
    _create_local_user, _insert_setup, _insert_strategy, _runtime_record,
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
        setup_id = _insert_setup(connection, user["id"], "BTC Breakout Full")
        strategy_id = _insert_strategy(
            connection, user["id"], setup_id, "BTC Breakout Full Strategy",
        )
        connection.execute(text("""
            UPDATE strategies SET base_amount = 250,
                data = jsonb_set(data, '{base_amount}', '250'::jsonb)
            WHERE id = :strategy_id AND user_id = :user_id
        """), {"strategy_id": strategy_id, "user_id": user["id"]})
    token = create_access_token({"sub": str(user["id"]), "role": "user"})
    observed = run_gate(
        base_url=args.base_url, bearer_token=token,
        message="Wijzig BTC Breakout Full Strategy van 250 naar 300 euro per uitvoering.",
        timeout_seconds=75,
    )
    record = _runtime_record(observed["run_id"])
    proposal = record["proposal"]
    projection = record["terminal_projection"]
    with sync_engine.connect() as connection:
        saved_amount = connection.execute(text("""
            SELECT base_amount FROM strategies WHERE id = :strategy_id AND user_id = :user_id
        """), {"strategy_id": strategy_id, "user_id": user["id"]}).scalar_one()
        setup_investment = connection.execute(text("""
            SELECT min_investment FROM setups WHERE id = :setup_id AND user_id = :user_id
        """), {"setup_id": setup_id, "user_id": user["id"]}).scalar_one()
    checks = {
        "strategy_operation": observed["final_operation_id"] == "update_strategy",
        "strategy_target": bool(proposal and proposal["target_type"] == "strategy"
                                and str(proposal["target_id"]) == str(strategy_id)),
        "strategy_amount_field": dict(projection.get("supplied_inputs") or {}).get(
            "changed_fields",
        ) == {"base_amount": 300},
        "no_setup_proposal": not proposal or proposal["target_type"] != "setup",
        "no_write_before_confirmation": float(saved_amount) == 250 and setup_investment is None,
        "one_dispatch_attempt": observed["dispatch_count"] == observed["attempt_count"] == 1,
        "polling_sse_parity": bool(observed["polling_sse_contract_projection"]),
    }
    artifact = {
        "synthetic_local_only": True, "run_id": observed["run_id"],
        "status": observed["status"], "proposal_type": (proposal or {}).get("target_type"),
        "operation_id": observed["final_operation_id"],
        "target_source": projection.get("target_source"),
        "original_http_statuses": observed.get("http_statuses"),
        "checks": checks, "pass": all(checks.values()),
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    if not artifact["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
