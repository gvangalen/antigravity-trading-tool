#!/usr/bin/env python3
"""Local public-route proof of confirmed DCA -> same-conversation Paper proposal."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
import uuid

from backend.scripts.run_finn_v2_full_action_matrix import _create_local_user, _runtime_record
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.scripts.run_finn_v2_sequential_action_chain import _run_action, _safety_snapshot
from backend.utils.auth_utils import create_access_token


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    if urlparse(base_url).hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("dca_bot_continuation_requires_loopback_base_url")

    user = _create_local_user()
    other = _create_local_user()
    token = create_access_token({"sub": str(user["id"]), "role": "user"})
    other_token = create_access_token({"sub": str(other["id"]), "role": "user"})
    suffix = uuid.uuid4().hex[:8]
    parent = _run_action(
        base_url=base_url, token=token, other_token=other_token,
        message=(f"Maak een vast DCA-plan voor ETH met de naam Matrix DCA {suffix}: "
                 "1D, elke maandag, basisbedrag €80. Toon eerst een voorstel."),
        operation_id="create_setup",
    )
    action = dict(parent.get("action_result") or {})
    canonical = dict(action.get("canonical_entity") or {})
    strategy_id = canonical.get("strategy_id")
    conversation_id = (parent.get("proposal_lifecycle") or {}).get("execution_conversation_id")
    if not parent.get("passed") or not strategy_id or not conversation_id:
        raise AssertionError("confirmed_dca_parent_missing_verified_strategy")

    before_child = _safety_snapshot(int(user["id"]))
    child = run_gate(
        base_url=base_url, bearer_token=token, conversation_id=conversation_id,
        message=("Maak voor de strategie die bij het zojuist aangemaakte DCA-plan hoort "
                 f"een Paper-bot met de naam Matrix Direct Paper {suffix} en budget €20."),
        timeout_seconds=75,
    )
    child_record = _runtime_record(child["run_id"])
    after_child = _safety_snapshot(int(user["id"]))
    supplied = dict(child_record["terminal_projection"].get("supplied_inputs") or {})
    proposal = dict(child_record.get("proposal") or {})
    passed = all((
        child["conversation_id"] == conversation_id,
        child["final_operation_id"] == "create_bot",
        child["status"] == "completed",
        str(supplied.get("strategy_id")) == str(strategy_id),
        bool(proposal), child["polling_sse_contract_projection"],
        proposal.get("status") in {"draft", "pending_confirmation"},
        all(after_child[key] == before_child[key] for key in (
            "bots", "live_bots", "executions", "non_allowlisted_executions",
        )),
    ))
    artifact = {
        "artifact_version": "finn_v2.dca_bot_continuation.v1",
        "synthetic_local_user": True,
        "parent_run_id": parent["run_id"],
        "parent_passed": parent["passed"],
        "child_run_id": child["run_id"],
        "child_status": child["status"],
        "child_operation_id": child["final_operation_id"],
        "same_conversation": child["conversation_id"] == conversation_id,
        "linked_strategy_matches_confirmed_parent": str(supplied.get("strategy_id")) == str(strategy_id),
        "bot_proposal": bool(proposal),
        "bot_not_confirmed": proposal.get("status") in {"draft", "pending_confirmation"},
        "no_bot_or_execution_before_confirmation": all(
            after_child[key] == before_child[key] for key in (
                "bots", "live_bots", "executions", "non_allowlisted_executions",
            )
        ),
        "polling_sse_parity": child["polling_sse_contract_projection"],
        "passed": passed,
    }
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(artifact, indent=2, sort_keys=True) + "\n"
    output.write_text(payload, encoding="utf-8")
    print(json.dumps({"passed": passed, "output": str(output),
                      "sha256": hashlib.sha256(payload.encode()).hexdigest()}, sort_keys=True))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
