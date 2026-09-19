#!/usr/bin/env python3
"""Exercise persisted guided creates through the public local FINN lifecycle."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
import uuid

from backend.scripts.run_finn_v2_full_action_matrix import (
    _create_local_user,
    _runtime_record,
)
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.scripts.run_finn_v2_sequential_action_chain import (
    _run_action,
    _safety_snapshot,
)
from backend.utils.auth_utils import create_access_token


def _guided_turn(
    *, base_url: str, token: str, message: str, operation_id: str,
    expected_missing: list[str], conversation_id: str,
) -> dict:
    observed = run_gate(
        base_url=base_url,
        bearer_token=token,
        conversation_id=conversation_id,
        message=message,
        timeout_seconds=75,
    )
    record = _runtime_record(observed["run_id"])
    projection = dict(record["terminal_projection"] or {})
    missing = list(projection.get("missing_inputs") or [])
    return {
        "message": message,
        "run_id": observed["run_id"],
        "conversation_id": observed["conversation_id"],
        "operation_id": observed["final_operation_id"],
        "terminal_status": observed["status"],
        "missing_inputs": missing,
        "supplied_inputs": projection.get("supplied_inputs"),
        "dispatch_count": projection.get("dispatch_count"),
        "attempt_count": projection.get("attempt_count"),
        "polling_sse_parity": observed["polling_sse_contract_projection"],
        "passed": all((
            observed["final_operation_id"] == operation_id,
            observed["status"] == "clarification_required",
            missing == expected_missing,
            projection.get("dispatch_count") == 1,
            projection.get("attempt_count") == 1,
            observed["polling_sse_contract_projection"],
        )),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    if urlparse(base_url).hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("guided_create_regression_requires_loopback_base_url")

    primary = _create_local_user()
    other = _create_local_user()
    user_id = int(primary["id"])
    token = create_access_token({"sub": str(user_id), "role": "user"})
    other_token = create_access_token({"sub": str(other["id"]), "role": "user"})
    suffix = uuid.uuid4().hex[:8]
    names = {
        "dependency_setup": f"Guided Dependency {suffix}",
        "setup": f"BTC Guided {suffix}",
        "strategy": f"BTC Plan {suffix}",
        "bot": f"BTC Bot {suffix}",
    }
    before = _safety_snapshot(user_id)

    dependency_setup = _run_action(
        base_url=base_url,
        token=token,
        other_token=other_token,
        message=(
            f"Maak een trade setup voor BTC op 4H met de naam "
            f"{names['dependency_setup']}."
        ),
        operation_id="create_setup",
    )
    conversation_id = dependency_setup["conversation_id"]

    setup_draft = _guided_turn(
        base_url=base_url,
        token=token,
        conversation_id=conversation_id,
        message="Maak nog een setup voor BTC op 4H.",
        operation_id="create_setup",
        expected_missing=["setup_type", "name"],
    )
    guided_setup = _run_action(
        base_url=base_url,
        token=token,
        other_token=other_token,
        conversation_id=conversation_id,
        message=f"Trade setup, naam {names['setup']}.",
        operation_id="create_setup",
    )

    strategy_draft = _guided_turn(
        base_url=base_url,
        token=token,
        conversation_id=conversation_id,
        message=(
            "Maak voor deze setup een fixed strategie met 100 euro per uitvoering, "
            "entry 76000, stop-loss 72000, targets 83000 en 87000 en gebalanceerd risico."
        ),
        operation_id="create_strategy",
        expected_missing=["name"],
    )
    guided_strategy = _run_action(
        base_url=base_url,
        token=token,
        other_token=other_token,
        conversation_id=conversation_id,
        message=names["strategy"],
        operation_id="create_strategy",
    )

    complete_bot = _run_action(
        base_url=base_url,
        token=token,
        other_token=other_token,
        conversation_id=conversation_id,
        message=(
            f"Maak een paper-bot met de naam {names['bot']} gekoppeld aan strategie "
            f"{names['strategy']}, met een budget van 1000 euro en Paper mode. "
            "Activeer geen live trading."
        ),
        operation_id="create_bot",
    )
    after = _safety_snapshot(user_id)
    steps = [dependency_setup, setup_draft, guided_setup, strategy_draft, guided_strategy, complete_bot]
    artifact = {
        "artifact_version": "finn_v2.guided_create_regression.v1",
        "synthetic_local_user": True,
        "names": names,
        "steps": steps,
        "database_before": before,
        "database_after": after,
        "safety": {
            "live_bots": after["live_bots"],
            "non_allowlisted_executions": after["non_allowlisted_executions"],
        },
        "passed": all(step["passed"] for step in steps)
        and after["live_bots"] == 0
        and after["non_allowlisted_executions"] == 0,
    }
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(artifact, sort_keys=True, indent=2) + "\n"
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({
        "passed": artifact["passed"],
        "output": str(output),
        "sha256": hashlib.sha256(payload.encode()).hexdigest(),
    }, sort_keys=True))
    if not artifact["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
