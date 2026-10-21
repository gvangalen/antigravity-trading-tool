#!/usr/bin/env python3
"""Local worker-driven check for a new strategy after a blocked draft."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import text

from backend.infrastructure.database import sync_engine
from backend.scripts.run_finn_v2_full_action_matrix import (
    _create_local_user,
    _insert_setup,
    _runtime_record,
)
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.utils.auth_utils import create_access_token


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not args.base_url.startswith(("http://localhost:", "http://127.0.0.1:")):
        raise SystemExit("local_runtime_only")

    user = _create_local_user()
    with sync_engine.begin() as connection:
        _insert_setup(connection, user["id"], "BTC Breakout Full", "BTC")
    token = create_access_token({"sub": str(user["id"]), "role": "user"})

    blocked = run_gate(
        base_url=args.base_url, bearer_token=token, timeout_seconds=90,
        message=(
            "Maak voor mijn opgeslagen setup BTC Breakout Full een tweede Paper-strategie "
            "met naam BTC Oud. BTC 4H, vast bedrag €100, entry 84.000 USD, "
            "stop-loss 79.800 USD, target 92.400 USD en voorzichtig risico. "
            "Ik wil daarnaast alleen handelen bij stijgende 1D-trend en maximaal "
            "twee trades per dag. Toon het concept, sla niets op zonder bevestiging."
        ),
    )
    inherited = run_gate(
        base_url=args.base_url, bearer_token=token, timeout_seconds=90,
        conversation_id=blocked["conversation_id"],
        message=(
            "Maak voor mijn opgeslagen setup BTC Breakout Full een tweede Paper-strategie "
            "met naam BTC Overgenomen. De handelsregels blijven gelijk aan mijn vorige concept. "
            "Toon het concept, sla niets op zonder bevestiging."
        ),
    )
    pending = run_gate(
        base_url=args.base_url, bearer_token=token, timeout_seconds=90,
        conversation_id=blocked["conversation_id"],
        message=(
            "Maak voor mijn opgeslagen setup BTC Breakout Full een tweede Paper-strategie "
            "met naam BTC Nieuw. BTC 4H, vast bedrag €100, entry 84.000 USD, "
            "stop-loss 79.800 USD, target 92.400 USD en voorzichtig risico. "
            "Toon het concept, sla niets op zonder bevestiging."
        ),
    )
    fresh = run_gate(
        base_url=args.base_url, bearer_token=token, timeout_seconds=90,
        conversation_id=blocked["conversation_id"],
        message="Begin onafhankelijk nieuw strategievoorstel zonder eerdere automatische regels",
    )
    blocked_record = _runtime_record(blocked["run_id"])
    inherited_record = _runtime_record(inherited["run_id"])
    pending_record = _runtime_record(pending["run_id"])
    fresh_record = _runtime_record(fresh["run_id"])
    with sync_engine.connect() as connection:
        writes = connection.execute(text("""
            SELECT count(*) FROM strategies WHERE user_id = :user_id
              AND name IN ('BTC Oud', 'BTC Nieuw', 'BTC Overgenomen')
        """), {"user_id": user["id"]}).scalar_one()
    checks = {
        "unsupported_rule_blocked": blocked["status"] == "clarification_required"
        and blocked_record["proposal"] is None,
        "inherited_rules_still_blocked": inherited["status"] == "clarification_required"
        and inherited_record["proposal"] is None,
        "independent_choice_required": pending["status"] == "clarification_required"
        and pending_record["proposal"] is None,
        "new_request_targets_strategy": fresh["final_operation_id"] == "create_strategy",
        "new_strategy_proposal": fresh["status"] == "completed"
        and fresh_record["proposal"] is not None,
        "no_strategy_saved": writes == 0,
        "one_dispatch_each": all(
            turn["dispatch_count"] == turn["attempt_count"] == 1
            for turn in (blocked, inherited, pending, fresh)
        ),
        "polling_sse_parity": all(
            turn["polling_sse_contract_projection"] for turn in (blocked, inherited, pending, fresh)
        ),
    }
    artifact = {
        "synthetic_local_only": True,
        "blocked_run_id": blocked["run_id"],
        "inherited_run_id": inherited["run_id"],
        "pending_run_id": pending["run_id"],
        "fresh_run_id": fresh["run_id"],
        "blocked_status": blocked["status"],
        "inherited_status": inherited["status"],
        "pending_status": pending["status"],
        "fresh_status": fresh["status"],
        "fresh_operation_id": fresh["final_operation_id"],
        "checks": checks,
        "pass": all(checks.values()),
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    if not artifact["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
