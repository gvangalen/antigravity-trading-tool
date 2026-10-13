#!/usr/bin/env python3
"""Exercise strategy creation and an open Paper draft correction through web SSE.

Uses only a synthetic local owner. Neither proposal is confirmed or executed.
"""
from __future__ import annotations

import argparse
import json

from backend.infrastructure.database import sync_engine
from backend.scripts.run_finn_v2_full_action_matrix import (
    _create_local_user, _insert_setup, _insert_strategy,
)
from backend.scripts.run_finn_v2_persisted_runtime_gate import _request_json, _terminal_sse
from backend.scripts.run_finn_v2_visible_post_execution_reference_regression import _stream_envelope
from backend.utils.auth_utils import create_access_token


def _turn(base_url: str, token: str, session_id: str, query: str) -> tuple[str, dict]:
    visible = _stream_envelope(
        base_url=base_url, token=token, query=query, session_id=session_id,
        context={"page": "/setup", "locale": "nl", "symbol": "ETH", "timeframe": "Day"},
    )
    run_id = str((visible.get("state") or {}).get("run_id") or
                 (visible.get("response_trace") or {}).get("run_id") or "")
    if not run_id:
        raise AssertionError("visible_draft_run_missing")
    terminal = _terminal_sse(
        url=f"{base_url}/api/assistant/v2/runs/{run_id}/stream",
        headers={"Authorization": f"Bearer {token}"}, timeout=120,
    )
    if terminal.get("status") not in {"completed", "clarification_required"}:
        raise AssertionError(f"visible_draft_{terminal.get('status')}_{terminal.get('error_code')}")
    return str(visible.get("session_id") or session_id), terminal


def _fields(terminal: dict) -> dict:
    trace = terminal.get("runtime_trace") or {}
    projection = trace.get("terminal_projection") or trace
    return projection.get("supplied_inputs") or {}


def run(base_url: str) -> dict:
    base_url = base_url.rstrip("/")
    owner = _create_local_user()
    token = create_access_token({"sub": str(owner["id"]), "role": "user"})
    with sync_engine.begin() as connection:
        dca_setup_id = _insert_setup(
            connection, owner["id"], "QA vaste ETH vrijdag 2026-10-11", "ETH", setup_type="dca",
        )
        trade_setup_id = _insert_setup(connection, owner["id"], "QA ETH bot parent", "ETH")
        strategy_id = _insert_strategy(
            connection, owner["id"], trade_setup_id,
            "QA vaste ETH vrijdag strategie 2026-10-11",
        )
    session, first = _turn(
        base_url, token, "new",
        "Maak een DCA-strategie voor mijn setup QA vaste ETH vrijdag 2026-10-11.",
    )
    if first["status"] != "clarification_required" or _fields(first).get("setup_id") != dca_setup_id:
        raise AssertionError("dca_strategy_draft_not_bound_to_saved_setup")
    session, second = _turn(
        base_url, token, session,
        "€50 per uitvoering; noem de strategie QA ETH plan 13 oktober. "
        "Uitvoering handmatig, gebalanceerd risico.",
    )
    if second["status"] != "completed" or not (second.get("response") or {}).get("proposal_id"):
        raise AssertionError("dca_strategy_proposal_missing")
    if _fields(second).get("base_amount") != 50 or _fields(second).get("setup_id") != dca_setup_id:
        raise AssertionError("dca_strategy_proposal_fields_mismatch")

    session, third = _turn(
        base_url, token, "new",
        "Maak een Paper-bot voor de bestaande strategie QA vaste ETH vrijdag strategie "
        "2026-10-11. Activeer geen live trading.",
    )
    session, fourth = _turn(
        base_url, token, session,
        "Noem hem QA Paper Bot 13 oktober; budget €500, alleen Paper en nooit live.",
    )
    old_proposal_id = (fourth.get("response") or {}).get("proposal_id")
    if fourth["status"] != "completed" or not old_proposal_id:
        raise AssertionError("paper_draft_missing")
    if _fields(fourth).get("strategy_id") != strategy_id:
        raise AssertionError("paper_draft_wrong_strategy")
    session, fifth = _turn(
        base_url, token, session,
        "Corrigeer dit Paper-botconcept naar een botbudgetlimiet van €750; "
        "houd dezelfde strategie en blijf niet-live. Bevestig niets.",
    )
    new_proposal_id = (fifth.get("response") or {}).get("proposal_id")
    if fifth["status"] != "completed" or not new_proposal_id or new_proposal_id == old_proposal_id:
        raise AssertionError("paper_replacement_proposal_missing")
    if _fields(fifth).get("budget_total_eur") != 750 or _fields(fifth).get("strategy_id") != strategy_id:
        raise AssertionError("paper_replacement_fields_mismatch")
    old, old_status = _request_json(
        url=f"{base_url}/api/assistant/v2/proposals/{old_proposal_id}", method="GET",
        headers={"Authorization": f"Bearer {token}"}, body=None, timeout=20,
    )
    new, new_status = _request_json(
        url=f"{base_url}/api/assistant/v2/proposals/{new_proposal_id}", method="GET",
        headers={"Authorization": f"Bearer {token}"}, body=None, timeout=20,
    )
    if old_status != 200 or old.get("status") != "cancelled":
        raise AssertionError("superseded_paper_draft_still_confirmable")
    if new_status != 200 or new.get("status") not in {"draft", "pending_confirmation"}:
        raise AssertionError("replacement_paper_draft_not_confirmable")
    return {"checks": 5, "strategy_proposal": True, "paper_revision": True,
            "old_card_revoked": True, "confirmed": False, "browser_facade": True}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    args = parser.parse_args()
    print(json.dumps(run(args.base_url), ensure_ascii=False))


if __name__ == "__main__":
    main()
