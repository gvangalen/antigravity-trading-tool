#!/usr/bin/env python3
"""Read-only local regression for a saved DCA plan and consecutive coach turns."""

from __future__ import annotations

import json
import uuid

from sqlalchemy import text

from backend.infrastructure.database import sync_engine
from backend.scripts.run_finn_v2_full_action_matrix import _create_local_user, _insert_bot, _insert_setup, _runtime_record
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.utils.auth_utils import create_access_token


def main() -> None:
    user = _create_local_user()
    with sync_engine.begin() as connection:
        setup_name = f"BTC Vrijdag DCA {uuid.uuid4().hex[:6]}"
        sibling_name = f"BTC Andere DCA {uuid.uuid4().hex[:6]}"
        setup_id = _insert_setup(connection, user["id"], setup_name, setup_type="dca")
        sibling_id = _insert_setup(connection, user["id"], sibling_name, setup_type="dca")
        connection.execute(text("""
            UPDATE setups SET timeframe='1D', dca_frequency='weekly', dca_day='friday',
                              min_benchmark_score=26, max_benchmark_score=45
            WHERE id=:id
        """), {"id": setup_id})
        connection.execute(text("""
            UPDATE setups SET timeframe='1D', dca_frequency='weekly', dca_day='monday',
                              min_benchmark_score=34, max_benchmark_score=55
            WHERE id=:id
        """), {"id": sibling_id})
        strategy_id = connection.execute(text("""
            INSERT INTO strategies (user_id, setup_id, name, setup_type, execution_mode,
                                    base_amount, data, created_at)
            VALUES (:user_id, :setup_id, 'BTC Vrijdag Strategie', 'dca', 'fixed', 75,
                    CAST(:data AS jsonb), NOW()) RETURNING id
        """), {"user_id": user["id"], "setup_id": setup_id,
               "data": json.dumps({"execution_mode": "fixed", "base_amount": 75})}).scalar_one()
        _insert_bot(connection, user["id"], strategy_id, "BTC Vrijdag Paper")
    token = create_access_token({"sub": str(user["id"]), "role": "user"})
    prompts = (
        f"Wat weet je zeker over {setup_name}, de DCA-dag, het bedrag, de Paper-bot en de scores?",
        "Ik ben bang de boot te missen en wil vandaag €100 extra kopen. Hoe zou je me als coach helpen dit tegen mijn plan en risico af te wegen? Doe geen aankoop of wijziging.",
        "Ik voel FOMO bij BTC. Wat zegt mijn plan hierover? Alleen sparren.",
        "Welke dag staat mijn BTC DCA gepland?",
        "Welke dag staat mijn BTC DCA gepland? Koopt de bot dan automatisch op die dag?",
        "Vergelijk de actuele scores met deze setup. Welke opgeslagen benchmarkgrens geldt hiervoor?",
    )
    conversation_id = None
    failed = False
    for index, prompt in enumerate(prompts, 1):
        observed = run_gate(base_url="http://127.0.0.1:18000", bearer_token=token,
                            message=prompt, conversation_id=conversation_id, timeout_seconds=75)
        conversation_id = observed["conversation_id"]
        record = _runtime_record(observed["run_id"])
        state = record["runtime_state"]
        response = state.get("terminal_response") or {}
        summary = {
            "turn": index, "status": observed["status"], "error_code": observed.get("error_code"),
            "answer": response.get("content"), "run_id": observed["run_id"],
            "verifier": state.get("verifier"),
            "tool_names": [item.get("name") for item in (state.get("responses_exchange") or {}).get("tool_trace") or []],
        }
        if index == len(prompts):
            target_ids = [
                row.get("setup_id") for call in (state.get("responses_exchange") or {}).get("tool_trace") or []
                for item in (call.get("result") or {}).get("results") or []
                if item.get("scope") in {"read_setup_market_matches", "read_saved_setup_inventory", "read_active_setup"}
                and item.get("status") == "completed"
                for row in (
                    (item.get("data") or {}).get("matches") or []
                    if item.get("scope") == "read_setup_market_matches" else
                    (item.get("data") or {}).get("setups") or []
                    if item.get("scope") == "read_saved_setup_inventory" else
                    [item.get("data") or {}]
                )
            ]
            summary["selected_setup_ids"] = target_ids
            failed |= not target_ids or set(target_ids) != {setup_id}
            failed |= sibling_name in str(response.get("content") or "")
        print(json.dumps(summary, ensure_ascii=False, default=str), flush=True)
        failed |= observed["status"] != "completed" or "Ik kan dit nog niet onderbouwen" in str(response.get("content") or "")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
