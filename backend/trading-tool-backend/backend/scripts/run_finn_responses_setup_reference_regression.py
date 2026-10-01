#!/usr/bin/env python3
"""Local, non-sealed FINN continuation contract with distinct BTC strategies."""

from __future__ import annotations

import argparse
import json
import re
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
    parser.add_argument("--sequence", type=int, choices=range(1, 9))
    args = parser.parse_args()
    if not args.base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise SystemExit("setup_reference_regression_is_local_only")

    user = _create_local_user()
    with sync_engine.begin() as connection:
        breakout = _insert_setup(connection, user["id"], "BTC Breakout Full")
        base = _insert_setup(connection, user["id"], "BTC Full Base")
        apple = _insert_setup(connection, user["id"], "Apple Full Setup", symbol="AAPL")
        _insert_setup(connection, user["id"], "ETH Full Setup", symbol="ETH")
        connection.execute(text("UPDATE setups SET timeframe='1D' WHERE id=:id AND user_id=:user_id"), {
            "id": apple, "user_id": user["id"],
        })
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
        (
            "Ik wil mijn stop-loss weghalen omdat BTC anders te vroeg wordt uitgestopt. Ik vraag je om coaching, niet om iets te wijzigen. Hoe kijk je hiernaar?",
            "Ik vind dat te streng. Zou een kleinere positie met meer ruimte voor de stop niet verstandiger kunnen zijn? Denk kritisch mee zonder een nieuw niveau te verzinnen.",
            "Je hebt het over wachttijd, maar ik vroeg naar stopafstand en positieomvang. Kun je die afweging beantwoorden zonder mijn plan te wijzigen?",
            "Puur als algemene risicoles: als een stop verder weg ligt, hoe kun je dan met een kleinere positie hetzelfde maximale verlies begrenzen? Ik vraag niet om een koersniveau of uitvoering.",
        ),
        (
            "Ik twijfel tussen BTC Full Base op 4H en Apple Full Setup op 1D. Vergelijk de opgeslagen setupvoorwaarden naast elkaar en zeg wat je niet kunt vaststellen. Verander niets.",
            "Ik vroeg Apple Full Setup, niet ETH Full Setup. Kun je de twee genoemde setups opnieuw owner-scoped lezen en hun bevestigde velden vergelijken?",
            "Lees alleen Apple Full Setup. Welke asset, timeframe en type staan daar opgeslagen?",
            "Wat weet je zeker over die Apple Full Setup uit de database? Noem asset, timeframe en type, niet alleen de naam.",
        ),
        (
            "Vergelijk BTC Full Base met Apple Full Setup. Verander niets.",
            "Dat is een lijst, geen vergelijking. Wat verschilt er tussen precies die twee opgeslagen setups?",
        ),
        (
            "Welke strategie is gekoppeld aan BTC Full Base? Lees die opgeslagen strategie zonder iets te wijzigen.",
            "Welke strategienaam, welk entryniveau en welke aparte trigger staan daarin? Noem ook wat niet is vastgelegd.",
        ),
    )
    cases = []
    for sequence_number, sequence in enumerate(conversations, 1):
        if args.sequence is not None and sequence_number != args.sequence:
            continue
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
            if sequence_number == 5 and turn_number in {2, 3}:
                checks["stop_size_topic_retained"] = (
                    not re.search(
                        r"(?:bezwaar|probleem)[^.!?]{0,55}wachttijd[^.!?]{0,35}signaal",
                        answer, re.I,
                    )
                    and re.search(
                        r"(?:stopafstand|ruimere\s+stop|stop\s+verder\s+weg)",
                        answer, re.I,
                    ) is not None
                    and any(word in answer.casefold() for word in ("positie", "omvang", "grootte"))
                )
            if sequence_number == 5 and turn_number in {1, 4}:
                checks["stop_coaching_stays_on_risk"] = (
                    "stop" in answer.casefold()
                    and any(word in answer.casefold() for word in ("risico", "verlies", "positie"))
                )
            if sequence_number in {6, 7} and turn_number in {1, 2}:
                checks["two_named_setups_compared"] = (
                    "BTC Full Base" in answer and "Apple Full Setup" in answer
                    and "BTC" in answer and "AAPL" in answer
                    and "4H" in answer and "1D" in answer
                    and ("ETH Full Setup" not in answer or re.search(
                        r"\b(?:niet|not)\s+(?:om\s+)?ETH Full Setup\b", answer, re.I,
                    ) is not None)
                    and exchange.get("answer_kind") != "saved_setup_collection"
                )
                contract = exchange.get("turn_contract") or {}
                checks["turn_contract_pair"] = (
                    contract.get("answer_type") == "compare"
                    and {item.get("setup_id") for item in contract.get("targets") or []} == {base, apple}
                )
            if sequence_number == 6 and turn_number in {3, 4}:
                checks["apple_fields"] = (
                    "AAPL" in answer and "1D" in answer and "trade" in answer.casefold()
                )
            if sequence_number == 8 and turn_number == 2:
                checks["linked_strategy_fields"] = (
                    "BTC Full Base Strategy" in answer and "76.000" in answer
                    and "80.000" not in answer and "ETH Full Setup" not in answer
                    and exchange.get("answer_kind") != "saved_setup_collection"
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
