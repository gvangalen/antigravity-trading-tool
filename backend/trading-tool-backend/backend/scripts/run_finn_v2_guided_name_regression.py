#!/usr/bin/env python3
"""Exercise name suggestions through the persisted local FINN lifecycle."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

from backend.scripts.run_finn_v2_full_action_matrix import _create_local_user, _runtime_record
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.utils.auth_utils import create_access_token


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if urlparse(args.base_url).hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("guided_name_regression_requires_loopback_base_url")

    user = _create_local_user()
    token = create_access_token({"sub": str(user["id"]), "role": "user"})
    conversation_id = None
    observations = []
    for message in (
        "Maak een trade setup voor ETH op 4H.",
        "wat stel je voor",
        "ja, gebruik die naam",
    ):
        observed = run_gate(
            base_url=args.base_url.rstrip("/"), bearer_token=token,
            conversation_id=conversation_id, message=message, timeout_seconds=75,
        )
        conversation_id = observed["conversation_id"]
        record = _runtime_record(observed["run_id"])
        state = dict(record["runtime_state"] or {})
        observations.append({
            "message": message,
            "status": observed["status"],
            "operation_id": observed["final_operation_id"],
            "terminal": dict(state.get("terminal_response") or {}).get("content"),
            "supplied_inputs": dict(record["terminal_projection"] or {}).get("supplied_inputs"),
            "proposal_status": dict(record.get("proposal") or {}).get("status"),
            "polling_sse_parity": observed["polling_sse_contract_projection"],
        })

    ask_for_name = []
    conversation_id = None
    for message in (
        "Maak een ETH trade-setup op 4H. Vraag mij om de naam en sla niets op.",
        "ETH Rustig 4H",
    ):
        observed = run_gate(
            base_url=args.base_url.rstrip("/"), bearer_token=token,
            conversation_id=conversation_id, message=message, timeout_seconds=75,
        )
        conversation_id = observed["conversation_id"]
        record = _runtime_record(observed["run_id"])
        ask_for_name.append({
            "message": message,
            "status": observed["status"],
            "operation_id": observed["final_operation_id"],
            "missing_inputs": dict(record["terminal_projection"] or {}).get("missing_inputs"),
            "supplied_inputs": dict(record["terminal_projection"] or {}).get("supplied_inputs"),
            "proposal_status": dict(record.get("proposal") or {}).get("status"),
            "polling_sse_parity": observed["polling_sse_contract_projection"],
        })

    first, suggestion, accepted = observations
    prompted, typed = ask_for_name
    passed = all((
        first["status"] == "clarification_required",
        first["operation_id"] == "create_setup",
        suggestion["status"] == "completed",
        suggestion["operation_id"] is None,
        suggestion["proposal_status"] is None,
        "ETH 4H Trade" in str(suggestion["terminal"]),
        accepted["operation_id"] == "create_setup",
        dict(accepted["supplied_inputs"] or {}).get("name") == "ETH 4H Trade",
        accepted["proposal_status"] in {"draft", "pending", "ready", "awaiting_confirmation"},
        prompted["status"] == "clarification_required",
        prompted["missing_inputs"] == ["name"],
        prompted["proposal_status"] is None,
        "name" not in dict(prompted["supplied_inputs"] or {}),
        dict(typed["supplied_inputs"] or {}).get("name") == "ETH Rustig 4H",
        typed["proposal_status"] in {"draft", "pending", "ready", "awaiting_confirmation"},
        all(item["polling_sse_parity"] for item in observations + ask_for_name),
    ))
    artifact = {"version": "finn_v2.guided_name_regression.v2",
                "synthetic_local_user": True, "passed": passed,
                "observations": observations, "ask_for_name": ask_for_name}
    Path(args.output).write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n")
    if not passed:
        raise AssertionError("guided_name_regression_failed")
    print(json.dumps({"passed": passed, "turns": len(observations) + len(ask_for_name)}))


if __name__ == "__main__":
    main()
