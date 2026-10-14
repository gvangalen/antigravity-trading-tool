#!/usr/bin/env python3
"""Replay the rejected guided trade setup flow through the visible chat facade.

Uses a synthetic local owner and stops at the proposal. Nothing is confirmed.
"""
from __future__ import annotations

import argparse
import json
import urllib.request

from sqlalchemy import text

from backend.infrastructure.database import sync_engine
from backend.scripts.run_finn_v2_full_action_matrix import _create_local_user, _insert_setup
from backend.scripts.run_finn_v2_persisted_runtime_gate import _request_json, _terminal_sse
from backend.scripts.run_finn_v2_visible_guided_dca_regression import _projection
from backend.scripts.run_finn_v2_visible_post_execution_reference_regression import _stream_envelope
from backend.utils.auth_utils import create_access_token


def run(base_url: str) -> dict:
    owner = _create_local_user()
    token = create_access_token({"sub": str(owner["id"]), "role": "user"})
    session_id = "new"
    turns = (
        "Maak een nieuwe setup voor ETH, maar stel eerst de ontbrekende vragen. Bevestig of sla niets op.",
        "Een eenmalige trade-setup op 4H. Noem hem QA Paneel ETH 1410. Stel nog ontbrekende setupvragen en sla niets op.",
        "Laat scoregrenzen voorlopig weg. Toon alleen het voorstel; bevestig niets.",
    )
    records = []
    for query in turns:
        visible = _stream_envelope(
            base_url=base_url.rstrip("/"), token=token, query=query, session_id=session_id,
            context={"page": "/setup", "locale": "nl", "page_type": "Mijn Plan",
                     "symbol": "ETH", "timeframe": "4H"},
        )
        session_id = str(visible.get("session_id") or session_id)
        run_id = str((visible.get("state") or {}).get("run_id") or
                     (visible.get("response_trace") or {}).get("run_id") or "")
        if not run_id:
            raise AssertionError("trade_setup_visible_run_missing")
        terminal = _terminal_sse(
            url=f"{base_url.rstrip('/')}/api/assistant/v2/runs/{run_id}/stream",
            headers={"Authorization": f"Bearer {token}"}, timeout=120,
        )
        projection = _projection(terminal)
        records.append({
            "status": terminal.get("status"),
            "operation_id": projection.get("operation_id"),
            "missing": projection.get("missing_inputs") or [],
            "supplied": projection.get("supplied_inputs") or {},
            "proposal_id": (terminal.get("response") or {}).get("proposal_id"),
            "run_id": run_id,
        })
    final = records[-1]
    if final["status"] != "completed" or not final["proposal_id"]:
        raise AssertionError(f"trade_setup_proposal_missing:{records}")
    expected = {"symbol": "ETH", "timeframe": "4H", "setup_type": "trade", "name": "QA Paneel ETH 1410"}
    if any(final["supplied"].get(key) != value for key, value in expected.items()):
        raise AssertionError(f"trade_setup_fields_mismatch:{final['supplied']}")
    headers = {"Authorization": f"Bearer {token}"}
    list_request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/assistant/v2/conversations", headers=headers,
    )
    with urllib.request.urlopen(list_request, timeout=20) as response:
        listing = json.load(response)
        list_status = response.status
    if list_status != 200 or not isinstance(listing, list) or not any(item.get("id") == session_id for item in listing):
        raise AssertionError("trade_setup_conversation_not_listed")
    detail, detail_status = _request_json(
        url=f"{base_url.rstrip('/')}/api/assistant/v2/conversations/{session_id}",
        method="GET", headers=headers, body=None, timeout=20,
    )
    messages = detail.get("messages") or []
    if detail_status != 200 or [message.get("content") for message in messages if message.get("role") == "user"] != list(turns):
        raise AssertionError("trade_setup_conversation_not_restored")
    return {"checks": len(records) + 2, "proposal_created": True, "confirmed": False,
            "history_restored": True, "records": records}


def run_featured_plan(base_url: str) -> dict:
    owner = _create_local_user()
    with sync_engine.begin() as connection:
        featured = _insert_setup(connection, owner["id"], "QA Paper herstel ETH", symbol="ETH")
        decoy = _insert_setup(connection, owner["id"], "QA Positief ETH", symbol="ETH")
        connection.execute(text("UPDATE setups SET timeframe='1D' WHERE id=:id"), {"id": featured})
        connection.execute(text("UPDATE setups SET timeframe='4H' WHERE id=:id"), {"id": decoy})
    token = create_access_token({"sub": str(owner["id"]), "role": "user"})
    visible = _stream_envelope(
        base_url=base_url.rstrip("/"), token=token,
        query="Welke ETH-setup is nu uitgelicht en welk timeframe staat daarbij opgeslagen? Wijzig niets.",
        session_id="new",
        context={"page": "/setup", "locale": "nl", "page_type": "Mijn Plan",
                 "symbol": "ETH", "setup_id": featured, "setup_name": "QA Paper herstel ETH"},
    )
    run_id = str((visible.get("state") or {}).get("run_id") or
                 (visible.get("response_trace") or {}).get("run_id") or "")
    if not run_id:
        raise AssertionError("featured_plan_visible_run_missing")
    terminal = _terminal_sse(
        url=f"{base_url.rstrip('/')}/api/assistant/v2/runs/{run_id}/stream",
        headers={"Authorization": f"Bearer {token}"}, timeout=120,
    )
    answer = str((terminal.get("response") or {}).get("content") or "")
    if terminal.get("status") != "completed" or "QA Paper herstel ETH" not in answer or "1D" not in answer:
        raise AssertionError(f"featured_plan_answer_mismatch:{terminal.get('status')}:{answer}")
    return {"featured_plan_read": True, "run_id": run_id}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    args = parser.parse_args()
    print(json.dumps({"guided_trade": run(args.base_url),
                      "featured_plan": run_featured_plan(args.base_url)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
