#!/usr/bin/env python3
"""Exercise a multi-slot DCA reply through the same stream facade as web chat.

The direct V2 endpoint does not send the browser's session ID or use the
visible delivery facade. Keep this as an authenticated local-provider gate.
No proposal is confirmed or executed.
"""
from __future__ import annotations

import argparse
import json

from backend.scripts.run_finn_v2_full_action_matrix import _create_local_user
from backend.scripts.run_finn_v2_persisted_runtime_gate import _request_json, _terminal_sse
from backend.scripts.run_finn_v2_visible_post_execution_reference_regression import _stream_envelope
from backend.utils.auth_utils import create_access_token


def _turn(base_url: str, token: str, session_id: str, query: str) -> tuple[str, dict]:
    visible = _stream_envelope(
        base_url=base_url, token=token, query=query, session_id=session_id,
        context={"page": "/setup", "locale": "nl", "page_type": "Mijn Plan",
                 "symbol": "BTC", "timeframe": "Day"},
    )
    run_id = str((visible.get("state") or {}).get("run_id") or
                 (visible.get("response_trace") or {}).get("run_id") or "")
    if not run_id:
        raise AssertionError("guided_dca_visible_run_missing")
    terminal = _terminal_sse(
        url=f"{base_url}/api/assistant/v2/runs/{run_id}/stream",
        headers={"Authorization": f"Bearer {token}"}, timeout=120,
    )
    if terminal.get("status") not in {"completed", "clarification_required"}:
        raise AssertionError(f"guided_dca_run_{terminal.get('status')}_{terminal.get('error_code')}")
    return str(visible.get("session_id") or session_id), terminal


def _projection(terminal: dict) -> dict:
    trace = terminal.get("runtime_trace") or {}
    return trace.get("terminal_projection") or trace


def run(base_url: str) -> dict:
    base_url = base_url.rstrip("/")
    owner = _create_local_user()
    token = create_access_token({"sub": str(owner["id"]), "role": "user"})
    session_id = "new"
    turns = (
        "Maak een BTC DCA-setup met primair timeframe 1D, naam QA concept BTC 13 oktober "
        "en elke vrijdag. Bedragtype en bedrag volgen.",
        "Vast bedrag. Gebruik 1D, noem de setup QA concept BTC 13 oktober "
        "en zet de frequentie op wekelijks op vrijdag.",
        "€50 per uitvoering.",
    )
    records = []
    for query in turns:
        session_id, terminal = _turn(base_url, token, session_id, query)
        projection = _projection(terminal)
        records.append({
            "status": terminal.get("status"),
            "missing": projection.get("missing_inputs") or [],
            "supplied": projection.get("supplied_inputs") or {},
            "proposal_id": (terminal.get("response") or {}).get("proposal_id"),
        })
    if records[1]["missing"] != ["base_amount"]:
        raise AssertionError(f"guided_dca_repeat_question_{records[1]['missing']}")
    if records[2]["status"] != "completed" or not records[2]["proposal_id"]:
        raise AssertionError("guided_dca_proposal_missing")
    expected = {
        "name": "QA concept BTC 13 oktober", "symbol": "BTC", "timeframe": "1D",
        "setup_type": "dca", "dca_frequency": "weekly", "dca_day": "friday",
        "dca_amount_mode": "fixed", "base_amount": 50.0,
    }
    if any(records[2]["supplied"].get(key) != value for key, value in expected.items()):
        raise AssertionError(f"guided_dca_fields_mismatch_{records[2]['supplied']}")
    proposal, status = _request_json(
        url=f"{base_url}/api/assistant/v2/proposals/{records[2]['proposal_id']}",
        method="GET", headers={"Authorization": f"Bearer {token}"}, body=None,
        timeout=20,
    )
    if status != 200 or proposal.get("can_confirm") is False:
        raise AssertionError(f"guided_dca_proposal_read_{status}")
    return {"checks": 3, "proposal_created": True, "confirmed": False,
            "browser_facade": True, "statuses": [item["status"] for item in records]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    args = parser.parse_args()
    print(json.dumps(run(args.base_url), ensure_ascii=False))


if __name__ == "__main__":
    main()
