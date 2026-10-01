#!/usr/bin/env python3
"""Local, non-sealed FINN continuation contract with distinct BTC strategies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import text

from backend.infrastructure.database import sync_engine
from backend.scripts.run_finn_v2_full_action_matrix import (
    _create_local_user, _insert_setup, _insert_strategy, _runtime_record,
)
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.utils.auth_utils import create_access_token


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not args.base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise SystemExit("setup_reference_regression_is_local_only")

    user = _create_local_user()
    with sync_engine.begin() as connection:
        breakout = _insert_setup(connection, user["id"], "BTC Breakout Full")
        base = _insert_setup(connection, user["id"], "BTC Full Base")
        _insert_setup(connection, user["id"], "Apple swing", symbol="AAPL")
        for setup_id, name, entry, stop in (
            (breakout, "BTC Breakout Full Strategy", 80000, 76000),
            (base, "BTC Full Base Strategy", 76000, 72000),
        ):
            strategy_id = _insert_strategy(connection, user["id"], setup_id, name)
            connection.execute(text("""
                UPDATE strategies SET entry=:entry, stop_loss=:stop,
                    targets=ARRAY[:target]::NUMERIC[], data=CAST(:data AS jsonb)
                WHERE id=:id AND user_id=:user_id
            """), {
                "entry": entry, "stop": stop, "target": entry + 8000,
                "data": json.dumps({"name": name, "entry": entry,
                                    "stop_loss": stop, "targets": [entry + 8000],
                                    "base_amount": 100, "execution_mode": "fixed"}),
                "id": strategy_id, "user_id": user["id"],
            })

    token = create_access_token({"sub": str(user["id"]), "role": "user"})
    conversations = (
        (
            "Wat zijn de namen van mijn BTC-plannen?",
            "Nummer twee: wat weet je daarvan uit mijn opgeslagen gegevens?",
            "Ik krijg FOMO bij dat plan. Wat zijn de instap en stop, en wat zou je eerst checken?",
            "Ik twijfel bij dat plan. Welke korte pauze helpt me om niet impulsief te handelen?",
            "En welke entry en stop horen daarbij volgens mijn opgeslagen strategie?",
        ),
        (
            "Welke Bitcoin-setups heb ik opgeslagen?",
            "Vertel me meer over de tweede, inclusief wat je zeker weet.",
            "En als ik daardoor nu impulsief wil instappen?",
        ),
        ("Als ik Apple koop vanwege FOMO, mag ik dan dezelfde regel als bij BTC hanteren?",),
        (
            "Welke BTC-setups heb ik opgeslagen?",
            "De tweede uit de lijst: wat staat daarvan vast?",
            "Mag ik dezelfde BTC-regel ook voor Apple gebruiken?",
        ),
    )
    cases = []
    for sequence_number, sequence in enumerate(conversations, 1):
        conversation_id = None
        for turn_number, message in enumerate(sequence, 1):
            observed = run_gate(
                base_url=args.base_url, bearer_token=token, message=message,
                conversation_id=conversation_id, timeout_seconds=75,
            )
            conversation_id = observed["conversation_id"]
            record = _runtime_record(observed["run_id"])
            state = record["runtime_state"]
            exchange = state.get("responses_exchange") or {}
            answer = str((state.get("terminal_response") or {}).get("content") or "")
            trace = exchange.get("tool_trace") or []
            checks = {
                "completed": observed["status"] == "completed",
                "read_only": record["proposal"] is None and not state.get("action_result"),
                "one_dispatch": observed["dispatch_count"] == observed["attempt_count"] == 1,
            }
            if sequence_number in {1, 2} and turn_number == 1:
                checks["complete_inventory"] = (
                    "BTC Breakout Full" in answer and "BTC Full Base" in answer
                    and exchange.get("answer_kind") == "saved_setup_collection"
                )
            if sequence_number in {1, 2} and turn_number == 2:
                checks["selected_base_identity"] = (
                    "BTC Full Base" in answer
                    and any(
                        call.get("name") == "get_saved_setup_inventory"
                        and (call.get("arguments") or {}).get("setup_ids") == [base]
                        for call in trace
                    )
                )
            if sequence_number == 1 and turn_number == 3:
                selected_reads = [
                    item for call in trace for item in (call.get("result") or {}).get("results") or []
                    if item.get("scope") in {"read_active_setup", "read_linked_strategy"}
                    and item.get("status") == "completed"
                ]
                checks["source_bound_levels"] = (
                    bool(selected_reads)
                    and all((item.get("data") or {}).get("setup_id") == base for item in selected_reads)
                    and "76.000" in answer and "72.000" in answer
                    and "80.000" not in answer
                )
            if sequence_number == 1 and turn_number == 5:
                selected_reads = [
                    item for call in trace for item in (call.get("result") or {}).get("results") or []
                    if item.get("scope") in {"read_active_setup", "read_linked_strategy"}
                    and item.get("status") == "completed"
                ]
                checks["durable_subject_after_coach_turn"] = (
                    bool(selected_reads)
                    and all((item.get("data") or {}).get("setup_id") == base for item in selected_reads)
                    and "76.000" in answer and "72.000" in answer
                    and "80.000" not in answer
                )
            if sequence_number == 1 and turn_number in {4, 5}:
                subject = state.get("verified_setup_subject") or {}
                checks["owner_bound_subject_persisted"] = (
                    subject.get("owner_id") == user["id"]
                    and subject.get("setup_id") == base
                )
            if sequence_number == 2 and turn_number == 3:
                checks["coach_continuation"] = (
                    exchange.get("answer_kind") != "saved_confirmation_inventory"
                    and not ("BTC Breakout Full" in answer and "BTC Full Base" in answer)
                )
            if sequence_number == 3:
                checks["asset_boundary"] = (
                    exchange.get("answer_kind") == "cross_asset_rule_scope"
                    and "BTC" in answer and "AAPL" in answer
                    and "niet automatisch" in answer.casefold()
                )
            if sequence_number == 4 and turn_number == 3:
                checks["asset_switch_clears_selected_setup"] = (
                    exchange.get("answer_kind") == "cross_asset_rule_scope"
                    and state.get("verified_setup_subject") is None
                )
            cases.append({"sequence": sequence_number, "turn": turn_number,
                          "run_id": observed["run_id"], "message": message,
                          "answer": answer, "answer_kind": exchange.get("answer_kind"),
                          "checks": checks, "pass": all(checks.values())})
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps({"cases": cases}, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps({"sequence": sequence_number, "turn": turn_number,
                              "pass": all(checks.values()), "checks": checks}), flush=True)
    result = {"synthetic_local_only": True, "total": len(cases),
              "passed": sum(case["pass"] for case in cases), "cases": cases}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    if result["passed"] != result["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
