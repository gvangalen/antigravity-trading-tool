#!/usr/bin/env python3
"""Exercise the exact visible-chat confirmation-to-reference boundary.

The browser's first response can be a pending assistant envelope. It then
observes the same persisted V2 terminal projection before rendering a proposal
card. This regression follows that public route, confirms the card, and sends
the next natural-language reference using only the execute response's
conversation id. No database identity is supplied to a user message.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
import uuid

from backend.scripts.run_finn_v2_full_action_matrix import (
    _create_local_user,
    _proposal_lifecycle,
)
from backend.scripts.run_finn_v2_persisted_runtime_gate import _request_json, _terminal_sse
from backend.utils.auth_utils import create_access_token


def _stream_envelope(*, base_url: str, token: str, query: str, session_id: str | None) -> dict:
    """Read the single assistant SSE envelope without retaining the stream."""
    import urllib.request

    request = urllib.request.Request(
        f"{base_url}/api/assistant/chat/stream",
        data=json.dumps({"query": query, "context": {}, "history": [], "session_id": session_id or "new"}).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "text/event-stream"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        event_name = None
        payload = None
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if line.startswith("event: "):
                event_name = line[7:]
            elif line.startswith("data: "):
                payload = json.loads(line[6:])
            elif not line and event_name == "envelope" and isinstance(payload, dict):
                return payload
    raise AssertionError("visible_reference_missing_envelope")


def _terminal_from_visible_envelope(*, base_url: str, token: str, envelope: dict) -> dict:
    run_id = str((envelope.get("state") or {}).get("run_id") or (envelope.get("response_trace") or {}).get("run_id") or "")
    if not run_id:
        raise AssertionError("visible_reference_missing_pending_run_id")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    terminal = _terminal_sse(
        url=f"{base_url}/api/assistant/v2/runs/{run_id}/stream",
        headers=headers,
        timeout=75,
    )
    if terminal.get("status") != "completed":
        raise AssertionError(f"visible_reference_noncompleted_{terminal.get('status')}")
    return terminal


def _public_runtime_record(*, base_url: str, token: str, run_id: str) -> dict:
    """Read the same persisted delivery projection that the browser receives.

    The parity stack runs in Docker, while this runner executes on the host.
    Reading ``sync_engine`` here can therefore accidentally inspect a different
    database.  The visible browser never has that privilege: it only receives
    the owner-scoped run and proposal routes, so the regression must use them
    too.
    """
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    run, run_status = _request_json(
        url=f"{base_url}/api/assistant/v2/runs/{run_id}",
        method="GET",
        headers=headers,
        body=None,
        timeout=20,
    )
    if run_status != 200:
        raise AssertionError(f"visible_reference_run_read_failed_{run_status}")
    projection = dict(run.get("runtime_trace") or {})
    proposal_id = str((run.get("response") or {}).get("proposal_id") or "")
    proposal = None
    if proposal_id:
        proposal_payload, proposal_status = _request_json(
            url=f"{base_url}/api/assistant/v2/proposals/{proposal_id}",
            method="GET",
            headers=headers,
            body=None,
            timeout=20,
        )
        if proposal_status != 200:
            raise AssertionError(f"visible_reference_proposal_read_failed_{proposal_status}")
        # Keep the existing lifecycle helper's minimal input shape while
        # sourcing every value from its public proposal summary.
        proposal = {
            "id": proposal_payload.get("proposal_id"),
            "payload_hash": proposal_payload.get("payload_hash"),
        }
    return {
        "runtime_contract_id": projection.get("contract_id"),
        "runtime_state": {},
        "terminal_projection": projection,
        "proposal": proposal,
    }


def _visible_action(*, base_url: str, token: str, other_token: str, query: str, session_id: str | None, expected_operation: str) -> dict:
    envelope = _stream_envelope(base_url=base_url, token=token, query=query, session_id=session_id)
    terminal = _terminal_from_visible_envelope(base_url=base_url, token=token, envelope=envelope)
    run_id = str(terminal.get("run_id") or "")
    record = _public_runtime_record(base_url=base_url, token=token, run_id=run_id)
    proposal = record.get("proposal")
    lifecycle = _proposal_lifecycle(base_url, token, other_token, proposal) if proposal else {}
    # Execution writes the canonical action result after the first terminal
    # proposal projection. Re-read the persisted contract just as the browser
    # will on its next natural-language turn.
    record_after_execution = _public_runtime_record(base_url=base_url, token=token, run_id=run_id)
    projection = record_after_execution.get("terminal_projection") or {}
    next_session_id = str(lifecycle.get("execution_conversation_id") or "")
    checks = {
        "expected_operation": (terminal.get("runtime_trace") or {}).get("final_operation_id") == expected_operation,
        "proposal_visible": bool(proposal),
        "confirmed": lifecycle.get("confirmed") is True,
        "executed": lifecycle.get("execution_result") == "succeeded",
        "idempotent_replay": lifecycle.get("idempotency_result") == "already_executed",
        "execute_matches_visible_session": next_session_id == envelope.get("session_id"),
        "action_result_persisted": bool(projection.get("action_result")),
    }
    return {
        "query": query,
        "pending_session_id": envelope.get("session_id"),
        "run_id": run_id,
        "operation_id": (terminal.get("runtime_trace") or {}).get("final_operation_id"),
        "runtime_contract_id": (terminal.get("runtime_trace") or {}).get("contract_id"),
        "proposal_id": proposal.get("id") if proposal else None,
        "execution_conversation_id": next_session_id or None,
        "checks": checks,
        "polling_sse_parity": bool(run_id and record.get("runtime_contract_id")),
        "passed": all(checks.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18001")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    if urlparse(base_url).hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("visible_post_execution_reference_requires_loopback_base_url")

    primary = _create_local_user()
    other = _create_local_user()
    token = create_access_token({"sub": str(primary["id"]), "role": "user"})
    other_token = create_access_token({"sub": str(other["id"]), "role": "user"})
    suffix = uuid.uuid4().hex[:8]
    setup_name = f"Visible Reference Setup {suffix}"
    strategy_name = f"Visible Reference Strategy {suffix}"

    setup_create = _visible_action(
        base_url=base_url, token=token, other_token=other_token,
        query=f"Maak een trade setup voor BTC op 4H met de naam {setup_name}.",
        session_id=None, expected_operation="create_setup",
    )
    setup_update = _visible_action(
        base_url=base_url, token=token, other_token=other_token,
        query="Wijzig deze setup naar timeframe 1D.",
        session_id=setup_create["execution_conversation_id"], expected_operation="update_setup",
    )
    setup_update_after_execution = _visible_action(
        base_url=base_url, token=token, other_token=other_token,
        query="Wijzig deze setup terug van 1D naar 4H.",
        session_id=setup_update["execution_conversation_id"], expected_operation="update_setup",
    )
    strategy_create = _visible_action(
        base_url=base_url, token=token, other_token=other_token,
        query=(
            f"Maak voor deze setup een vaste strategie met de naam {strategy_name}, "
            "100 euro per uitvoering, entry 76000, stop-loss 72000, "
            "targets 83000 en 87000 en gebalanceerd risico."
        ),
        session_id=setup_update_after_execution["execution_conversation_id"], expected_operation="create_strategy",
    )
    strategy_update = _visible_action(
        base_url=base_url, token=token, other_token=other_token,
        query="Wijzig deze strategie en zet het bedrag naar 150 euro.",
        session_id=strategy_create["execution_conversation_id"], expected_operation="update_strategy",
    )
    strategy_update_after_execution = _visible_action(
        base_url=base_url, token=token, other_token=other_token,
        query="Wijzig deze strategie terug naar 100 euro per uitvoering.",
        session_id=strategy_update["execution_conversation_id"], expected_operation="update_strategy",
    )
    steps = (
        setup_create,
        setup_update,
        setup_update_after_execution,
        strategy_create,
        strategy_update,
        strategy_update_after_execution,
    )
    artifact = {
        "artifact_version": "finn_v2.visible_post_execution_reference.v1",
        "synthetic_local_user": True,
        "steps": list(steps),
        "passed": all(step["passed"] for step in steps),
    }
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(artifact, sort_keys=True, indent=2) + "\n"
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({"passed": artifact["passed"], "output": str(output), "sha256": hashlib.sha256(payload.encode()).hexdigest()}, sort_keys=True))
    if not artifact["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
