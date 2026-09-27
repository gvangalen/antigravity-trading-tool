#!/usr/bin/env python3
"""Public-route check that an incomplete strategy never becomes an executable draft."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import text

from backend.infrastructure.database import sync_engine
from backend.scripts.run_finn_v2_full_action_matrix import _create_local_user, _insert_setup, _runtime_record
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
        _insert_setup(connection, user["id"], "Atlas Boundary", "XLM")
    token = create_access_token({"sub": str(user["id"]), "role": "user"})
    observed = run_gate(
        base_url=args.base_url,
        bearer_token=token,
        message="Create a manual strategy named Atlas Plan from my saved Atlas Boundary setup with 125 euros per execution.",
        timeout_seconds=75,
    )
    record = _runtime_record(observed["run_id"])
    projection = record["terminal_projection"]
    with sync_engine.connect() as connection:
        strategy_count = connection.execute(text("""
            SELECT count(*) FROM strategies WHERE user_id = :user_id AND name = 'Atlas Plan'
        """), {"user_id": user["id"]}).scalar_one()
    missing = set(projection.get("missing_inputs") or [])
    checks = {
        "correct_operation": observed["final_operation_id"] == "create_strategy",
        "trade_fields_still_missing": {"entry", "stop_loss", "targets", "risk_profile"}.issubset(missing),
        "no_premature_proposal": record["proposal"] is None,
        "no_business_write": strategy_count == 0,
        "typed_terminal": observed["status"] == "clarification_required",
        "single_dispatch_attempt": observed["dispatch_count"] == observed["attempt_count"] == 1,
        "polling_sse_parity": bool(observed["polling_sse_contract_projection"]),
    }
    artifact = {
        "synthetic_local_only": True,
        "run_id": observed["run_id"],
        "status": observed["status"],
        "operation_id": observed["final_operation_id"],
        "missing_inputs": sorted(missing),
        "proposal_present": record["proposal"] is not None,
        "original_http_statuses": observed.get("http_statuses"),
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
