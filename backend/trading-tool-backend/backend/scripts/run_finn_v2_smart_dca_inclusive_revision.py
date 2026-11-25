#!/usr/bin/env python3
"""Check inclusive Smart DCA creation and open-card revision on the local stack.

Only synthetic local owners and unconfirmed proposals are used. No bot or order.
"""
from __future__ import annotations

import argparse
import json

from backend.scripts.run_finn_v2_full_action_matrix import _create_local_user
from backend.scripts.run_finn_v2_persisted_runtime_gate import _request_json, _terminal_sse
from backend.scripts.run_finn_v2_visible_post_execution_reference_regression import _stream_envelope
from backend.utils.auth_utils import create_access_token


def _turn(base_url: str, token: str, session_id: str, message: str) -> tuple[str, dict]:
    visible = _stream_envelope(
        base_url=base_url, token=token, query=message, session_id=session_id,
        context={"page": "/setup", "locale": "nl", "symbol": "BTC", "quote_currency": "USDT"},
    )
    run_id = str((visible.get("state") or {}).get("run_id") or
                 (visible.get("response_trace") or {}).get("run_id") or "")
    if not run_id:
        raise AssertionError("smart_dca_run_missing")
    terminal = _terminal_sse(
        url=f"{base_url}/api/assistant/v2/runs/{run_id}/stream",
        headers={"Authorization": f"Bearer {token}"}, timeout=120,
    )
    if terminal.get("status") != "completed":
        raise AssertionError(f"smart_dca_{terminal.get('status')}_{terminal.get('error_code')}")
    return str(visible.get("session_id") or session_id), terminal


def _fields(terminal: dict) -> dict:
    trace = terminal.get("runtime_trace") or {}
    projection = trace.get("terminal_projection") or trace
    return projection.get("supplied_inputs") or {}


def run(base_url: str) -> dict:
    base_url = base_url.rstrip("/")
    owner = _create_local_user()
    token = create_access_token({"sub": str(owner["id"]), "role": "user"})
    session, initial = _turn(
        base_url, token, "new",
        "Maak een nieuwe BTC/USDT Smart DCA-setup met naam QA Inclusief DCA, "
        "analysetijdsframe 1D, wekelijks maximaal één aankoop zonder vaste koopdag "
        "zodra de volledige benchmarkscore beschikbaar is. Basisbedrag €200. "
        "Scorebanden: 0–24: 150%, 25–75: 100%, 76–100: 50%. "
        "Toon eerst een voorstel; plaats geen order.",
    )
    first_id = (initial.get("response") or {}).get("proposal_id")
    if not first_id or (_fields(initial).get("low_threshold"), _fields(initial).get("high_threshold")) != (25, 76):
        raise AssertionError("initial_smart_dca_proposal_wrong")
    session, revised = _turn(
        base_url, token, session,
        "Corrigeer de scorebanden exact: 0 tot en met 25 krijgt 150%, "
        "26 tot en met 75 krijgt 100%, 76 tot en met 100 krijgt 50%. "
        "Score 25 moet €300 geven en score 26 €200. Toon opnieuw het voorstel.",
    )
    second_id = (revised.get("response") or {}).get("proposal_id")
    if not second_id or second_id == first_id or (
        _fields(revised).get("low_threshold"), _fields(revised).get("high_threshold")
    ) != (26, 76):
        raise AssertionError("inclusive_smart_dca_revision_missing")
    old, old_status = _request_json(
        url=f"{base_url}/api/assistant/v2/proposals/{first_id}", method="GET",
        headers={"Authorization": f"Bearer {token}"}, body=None, timeout=20,
    )
    if old_status != 200 or old.get("status") != "cancelled":
        raise AssertionError("old_smart_dca_proposal_still_confirmable")
    return {"initial_proposal": True, "revised_proposal": True,
            "old_card_revoked": True, "confirmations": 0, "orders": 0}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    args = parser.parse_args()
    print(json.dumps(run(args.base_url), ensure_ascii=False))


if __name__ == "__main__":
    main()
