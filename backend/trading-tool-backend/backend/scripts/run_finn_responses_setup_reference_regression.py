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
    _create_local_user, _insert_bot, _insert_setup, _insert_strategy, _runtime_record,
)
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.utils.auth_utils import create_access_token


def _only_excluded_mentions(answer: str, name: str) -> bool:
    for match in re.finditer(re.escape(name), answer, re.I):
        before = answer[max(0, match.start() - 50):match.start()]
        after = answer[match.end():match.end() + 50]
        if not (
            re.search(r"\b(?:niet|geen|not|no|keine|kein)\b[^.!?\n]{0,35}$", before, re.I)
            or re.match(r"[^.!?\n]{0,25}\b(?:niet|geen|not|no|keine|ausgeschlossen|uitgesloten)\b", after, re.I)
        ):
            return False
    return True


def _has_number(answer: str, value: int) -> bool:
    return str(value) in {
        re.sub(r"\D", "", token) for token in re.findall(r"\d[\d.,]*", answer)
    }


def _explicit_group_count(answer: str, label: str, count: int) -> bool:
    for raw in answer.splitlines():
        line = re.sub(r"[*_`]", "", raw).casefold()
        if "ondergrens" not in line or label not in line:
            continue
        group = (
            r"geen(?:\s+macro)?-?ondergrens" if label == "geen"
            else rf"ondergrens\s+(?:van\s+)?{label}\b"
        )
        if re.search(rf"{group}\s*[:—-]\s*{count}\b", line) or re.search(
            rf"\b{count}\s+(?:hebben|heeft|setups?)\b[^\n]*{group}", line,
        ):
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--sequence", type=int, choices=range(1, 22))
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
        for setup_id, name, entry, stop, target in (
            (breakout, "BTC Breakout Full Strategy", 80000, 76000, 88000),
            (base, "BTC Full Base Strategy", 76000, 72000, 84000),
            (apple, "Apple Full Strategy", 210, 190, 230),
        ):
            strategy_id = _insert_strategy(connection, user["id"], setup_id, name)
            connection.execute(text("""
                UPDATE strategies SET entry=:entry, stop_loss=:stop,
                    targets=ARRAY[:target]::NUMERIC[], data=CAST(:data AS jsonb)
                WHERE id=:id AND user_id=:user_id
            """), {
                    "entry": entry, "stop": stop, "target": target,
                    "data": json.dumps({"name": name, "entry": entry,
                                    "stop_loss": stop, "targets": [target],
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
        (
            "Ik wil mijn stop-loss weghalen omdat BTC anders te vroeg wordt uitgestopt. Ik vraag je om coaching, niet om iets te wijzigen. Hoe kijk je hiernaar?",
            "Ik vind dat te streng. Zou een kleinere positie met meer ruimte voor de stop niet verstandiger kunnen zijn? Denk kritisch mee zonder een nieuw niveau te verzinnen.",
            "Leg de afweging concreet uit: hoe houd ik hetzelfde maximale euroverlies als de stop verder weg komt, zonder mijn opgeslagen plan nu te wijzigen?",
        ),
        (
            "Ik twijfel tussen BTC Full Base op 4H en Apple Full Setup op 1D. Vergelijk de opgeslagen setupvoorwaarden naast elkaar en zeg wat je niet kunt vaststellen. Verander niets.",
            "Ja, lees die gekoppelde strategieën nu en vergelijk alleen de bevestigde instap- en risicovoorwaarden van BTC Full Base en Apple Full Setup. Wat ontbreekt?",
        ),
        (
            "Ik wil nu BTC Full Base traden omdat de koers stijgt. Welke concrete opgeslagen instapregel moet ik eerst controleren? Als die niet bewezen in mijn setup staat, zeg dat eerlijk. Verander niets.",
            "Lees dan alleen de gekoppelde BTC Full Base Strategy: welk entryniveau is opgeslagen, en is er daarnaast een aparte instapbevestiging vastgelegd? Noem geen nieuw niveau.",
        ),
        (
            "Welke BTC-setups staan in Mijn Plan? Noem alleen de opgeslagen namen en timeframes. Maak of wijzig niets.",
            "Wat weet je zeker over de tweede uit jouw lijst? Noem de opgeslagen velden en wees eerlijk over wat je niet hebt gelezen.",
            "En wat weet je daarvan zeker? Kan je ook de gekoppelde strategie controleren, zonder setupvelden en strategievelden door elkaar te halen?",
            "Staat in die strategie ook een aparte instapbevestiging, of alleen een entryprijs? Wat zou ik vóór een trade nog moeten controleren?",
        ),
        (
            "Ik twijfel tussen BTC Full Base op 4H en Apple Full Setup op 1D. Vergelijk de opgeslagen setupvoorwaarden naast elkaar en zeg wat je niet kunt vaststellen. Verander niets.",
            "Lees alleen Apple Full Strategy bij Apple Full Setup. Welke entry en stop staan daarin? Gebruik geen velden uit Apple Retest Strategy.",
        ),
        (
            "Ik twijfel tussen BTC Full Base op 4H en Apple Full Setup op 1D. Vergelijk de opgeslagen setupvoorwaarden naast elkaar en zeg wat je niet kunt vaststellen. Verander niets.",
            "Gebruik Apple Full Strategy voor de vergelijking. Wat zijn de opgeslagen entry, stop en targets van beide strategieën?",
            "En welke stop staat bij die strategie?",
            "Lees alleen Apple Full Strategy, die bij Apple Full Setup hoort. Welke entry en stop staan daarin?",
        ),
        (
            "Leg uitgebreid uit hoe mijn ETH-setups verschillen in timeframe, scorevoorwaarden, gekoppelde strategie, risicobeperking en geschiktheid bij de huidige scores. Alleen lezen, niets wijzigen.",
        ),
        (
            "Leg uitgebreid uit hoe mijn ETH-setups verschillen in timeframe, scorevoorwaarden, gekoppelde strategie, risicobeperking en geschiktheid bij de huidige scores. Alleen lezen, niets wijzigen.",
        ),
        (
            "Vergelijk mijn ETH-setups per naam: noem hun analyse-timeframe, DCA-koopritme als dat bestaat, gekoppelde strategieën en welke setup een Paper-bot heeft. Noem ook expliciet welke geen bot heeft. Alleen lezen.",
        ),
        (
            "Leg uitgebreid uit hoe mijn ETH-setups verschillen in timeframe, scorevoorwaarden, gekoppelde strategie, risicobeperking en geschiktheid bij de huidige scores. Alleen lezen, niets wijzigen.",
        ),
        (
            "Noem per ETH-setup de naam, gekoppelde strategie, Paper-bot en het DCA-koopritme. Geef daarna het totale aantal gekoppelde Paper-bots. Alleen lezen.",
        ),
        (
            "Leg uitgebreid uit hoe mijn ETH-setups verschillen in timeframe, scorevoorwaarden, gekoppelde strategie, risicobeperking en geschiktheid bij de huidige scores. Tel ook hoeveel ETH-setups een macro-ondergrens van 0 hebben, hoeveel 30 en hoeveel geen macro-ondergrens. Alleen lezen, niets wijzigen.",
            "Welches Setup meintest du gerade mit 1D? Nichts ändern.",
        ),
        (
            "Leg per ETH-setup uit welke macro-ondergrens is opgeslagen. Tel daarna hoeveel setups een ondergrens van 0 hebben, hoeveel een ondergrens van 30 hebben en hoeveel geen macro-ondergrens hebben. Alleen lezen.",
        ),
    )
    cases = []
    for sequence_number, sequence in enumerate(conversations, 1):
        if args.sequence is not None and sequence_number != args.sequence:
            continue
        if sequence_number == 13 or (sequence_number == 14 and args.sequence == 14):
            with sync_engine.begin() as connection:
                _insert_strategy(connection, user["id"], apple, "Apple Retest Strategy")
        if sequence_number == 15:
            with sync_engine.begin() as connection:
                eth_setups = connection.execute(text("""
                    SELECT id FROM setups WHERE user_id=:user_id AND name='ETH Full Setup'
                """), {"user_id": user["id"]}).scalars().all()
                assert len(eth_setups) == 1
                other_eth = _insert_setup(connection, user["id"], "ETH QA Tweede Setup", symbol="ETH")
                _insert_strategy(connection, user["id"], eth_setups[0], "ETH Full Strategy")
                _insert_strategy(connection, user["id"], other_eth, "ETH QA Tweede Strategy")
        if sequence_number == 16:
            with sync_engine.begin() as connection:
                original = connection.execute(text("""
                    SELECT id FROM setups WHERE user_id=:user_id AND name='ETH Full Setup'
                """), {"user_id": user["id"]}).scalar_one()
                _insert_strategy(connection, user["id"], original, "ETH Full Strategy")
                for index in range(2, 8):
                    setup_id = _insert_setup(
                        connection, user["id"], f"ETH QA Setup {index}", symbol="ETH",
                    )
                    connection.execute(text("""
                        UPDATE setups SET timeframe=:timeframe, min_macro_score=:macro
                        WHERE id=:id AND user_id=:user_id
                    """), {
                        "timeframe": "1D" if index % 2 == 0 else "4H",
                        "macro": 20 + index, "id": setup_id, "user_id": user["id"],
                    })
                    if index != 5:
                        _insert_strategy(connection, user["id"], setup_id, f"ETH QA Strategy {index}")
                    if index == 3:
                        _insert_strategy(connection, user["id"], setup_id, "ETH QA Strategy 3 Variant")
        if sequence_number in {17, 18, 19, 20, 21}:
            with sync_engine.begin() as connection:
                original = connection.execute(text("""
                    SELECT id FROM setups WHERE user_id=:user_id AND name='ETH Full Setup'
                """), {"user_id": user["id"]}).scalar_one()
                if sequence_number in {20, 21}:
                    connection.execute(text("""
                        UPDATE setups SET min_macro_score=0 WHERE id=:id AND user_id=:user_id
                    """), {"id": original, "user_id": user["id"]})
                _insert_strategy(connection, user["id"], original, "ETH Full Strategy")
                for index in range(2, 8):
                    name = f"ETH QA Bot Setup {index}"
                    setup_id = _insert_setup(
                        connection, user["id"], name, symbol="ETH",
                        setup_type="dca" if index in {2, 4} else "trade",
                    )
                    connection.execute(text("""
                        UPDATE setups SET timeframe=:timeframe, dca_frequency=:frequency,
                            dca_day=:day WHERE id=:id AND user_id=:user_id
                    """), {
                        "timeframe": "1D" if index in {2, 3, 4} else "4H",
                        "frequency": "weekly" if index in {2, 4} else None,
                        "day": "1" if index in {2, 4} else None,
                        "id": setup_id, "user_id": user["id"],
                    })
                    if sequence_number in {20, 21} and index != 4:
                        connection.execute(text("""
                            UPDATE setups SET min_macro_score=:macro
                            WHERE id=:id AND user_id=:user_id
                        """), {
                            "macro": 0 if index in {2, 3} else 30,
                            "id": setup_id, "user_id": user["id"],
                        })
                    strategy_id = _insert_strategy(
                        connection, user["id"], setup_id, f"ETH QA Bot Strategy {index}",
                    )
                    if index == 2:
                        strategy_id = _insert_strategy(
                            connection, user["id"], setup_id,
                            "ETH QA Bot Strategy 2 Variant",
                        )
                    if index in ({2, 3, 4, 5, 6} if sequence_number == 19 else {2, 5}):
                        bot_id = _insert_bot(
                            connection, user["id"], strategy_id, f"ETH QA Paper Bot {index}",
                        )
                        connection.execute(text("""
                            UPDATE bot_configs SET symbol='ETH' WHERE id=:id AND user_id=:user_id
                        """), {"id": bot_id, "user_id": user["id"]})
        conversation_id = None
        second_btc_setup_id = None
        last_verified_linked_setup_ids: set[int] = set()
        for turn_number, message in enumerate(sequence, 1):
            observed = run_gate(
                base_url=args.base_url, bearer_token=token, message=message,
                conversation_id=conversation_id, timeout_seconds=75,
                workspace_hints={"locale": "de" if sequence_number == 20 and turn_number == 2 else "nl"},
            )
            conversation_id = observed["conversation_id"]
            record = _runtime_record(observed["run_id"])
            state = record["runtime_state"]
            exchange = state.get("responses_exchange") or {}
            answer = str((state.get("terminal_response") or {}).get("content") or "")
            trace = exchange.get("tool_trace") or []
            if sequence_number in {1, 2} and turn_number == 1:
                breakout_position = answer.find("BTC Breakout Full")
                base_position = answer.find("BTC Full Base")
                if breakout_position >= 0 and base_position >= 0:
                    second_btc_setup_id = (
                        base if breakout_position < base_position else breakout
                    )
            checks = {
                "completed": observed["status"] == "completed",
                "read_only": record["proposal"] is None and not state.get("action_result"),
                "one_dispatch": observed["dispatch_count"] == observed["attempt_count"] == 1,
            }
            if sequence_number in {1, 2, 4} and turn_number == 1:
                checks["complete_inventory"] = (
                    "BTC Breakout Full" in answer and "BTC Full Base" in answer
                    and any(call.get("name") == "get_saved_setup_inventory"
                            and call.get("status") == "completed" for call in trace)
                )
            if sequence_number in {1, 2} and turn_number == 2:
                contract = exchange.get("turn_contract") or {}
                selected_name = (
                    "BTC Full Base" if second_btc_setup_id == base
                    else "BTC Breakout Full"
                )
                checks["selected_second_identity"] = (
                    second_btc_setup_id is not None and selected_name in answer
                    and [target.get("setup_id") for target in contract.get("targets") or []]
                    == [second_btc_setup_id]
                    and any(
                        item.get("status") == "completed"
                        and (
                            item.get("scope") == "read_active_setup"
                            and (item.get("data") or {}).get("setup_id") == second_btc_setup_id
                            or item.get("scope") == "read_saved_setup_inventory"
                            and [row.get("setup_id") for row in (item.get("data") or {}).get("setups") or []]
                            == [second_btc_setup_id]
                        )
                        for call in trace
                        for item in (call.get("result") or {}).get("results") or []
                    )
                )
            if sequence_number == 1 and turn_number == 3:
                expected_entry, expected_stop, other_entry = (
                    (76000, 72000, 80000) if second_btc_setup_id == base
                    else (80000, 76000, 0)
                )
                selected_reads = [
                    item for call in trace for item in (call.get("result") or {}).get("results") or []
                    if item.get("scope") in {"read_active_setup", "read_linked_strategy"}
                    and item.get("status") == "completed"
                ]
                checks["source_bound_levels"] = (
                    bool(selected_reads)
                    and all((item.get("data") or {}).get("setup_id") == second_btc_setup_id
                            for item in selected_reads)
                    and f"{expected_entry:,.0f}".replace(",", ".") in answer
                    and f"{expected_stop:,.0f}".replace(",", ".") in answer
                    and (not other_entry or f"{other_entry:,.0f}".replace(",", ".") not in answer)
                )
            if sequence_number == 1 and turn_number == 5:
                expected_entry, expected_stop, other_entry = (
                    (76000, 72000, 80000) if second_btc_setup_id == base
                    else (80000, 76000, 0)
                )
                selected_reads = [
                    item for call in trace for item in (call.get("result") or {}).get("results") or []
                    if item.get("scope") in {"read_active_setup", "read_linked_strategy"}
                    and item.get("status") == "completed"
                ]
                checks["durable_subject_after_coach_turn"] = (
                    bool(selected_reads)
                    and all((item.get("data") or {}).get("setup_id") == second_btc_setup_id
                            for item in selected_reads)
                    and f"{expected_entry:,.0f}".replace(",", ".") in answer
                    and f"{expected_stop:,.0f}".replace(",", ".") in answer
                    and (not other_entry or f"{other_entry:,.0f}".replace(",", ".") not in answer)
                )
            if sequence_number == 1 and turn_number in {4, 5}:
                subject = state.get("verified_setup_subject") or {}
                checks["owner_bound_subject_persisted"] = (
                    subject.get("owner_id") == user["id"]
                    and subject.get("setup_id") == second_btc_setup_id
                )
            if sequence_number == 2 and turn_number == 3:
                checks["coach_continuation"] = (
                    exchange.get("answer_kind") != "saved_confirmation_inventory"
                    and not ("BTC Breakout Full" in answer and "BTC Full Base" in answer)
                )
            if sequence_number == 3:
                checks["asset_boundary"] = (
                    "BTC" in answer and ("AAPL" in answer or "Apple" in answer)
                    and (
                        "niet automatisch" in answer.casefold()
                        or "niet zonder meer" in answer.casefold()
                        or ("niet aannemen" in answer.casefold()
                            and "geldt" in answer.casefold())
                    )
                )
            if sequence_number == 4 and turn_number == 3:
                checks["asset_switch_clears_selected_setup"] = (
                    "BTC" in answer and ("AAPL" in answer or "Apple" in answer)
                    and state.get("verified_setup_subject") is None
                )
            if sequence_number == 5 and turn_number in {2, 3}:
                checks["stop_size_topic_retained"] = (
                    not re.search(
                        r"(?:bezwaar|probleem)[^.!?]{0,55}wachttijd[^.!?]{0,35}signaal",
                        answer, re.I,
                    )
                    and "stop" in answer.casefold()
                    and any(word in answer.casefold() for word in ("ruim", "afstand", "verder weg"))
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
                    and (sequence_number == 7 and turn_number == 2
                         or ("BTC" in answer and "AAPL" in answer))
                    and "4H" in answer and "1D" in answer
                    and _only_excluded_mentions(answer, "ETH Full Setup")
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
            if sequence_number == 9:
                checks["stop_coach_answered"] = (
                    "stop" in answer.casefold()
                    and any(word in answer.casefold() for word in ("risico", "verlies", "positie"))
                    and "Ik kan dit nog niet onderbouwen" not in answer
                    and not re.search(r"\b(?:80|76|72)\.000\b", answer)
                )
            if sequence_number == 10:
                linked = [
                    item for call in trace for item in (call.get("result") or {}).get("results") or []
                    if item.get("scope") == "read_linked_strategy"
                    and item.get("status") == "completed"
                ]
                linked_ids = {
                    (item.get("data") or {}).get("setup_id") for item in linked
                }
                if exchange.get("uses_previous_response"):
                    linked_ids.update(last_verified_linked_setup_ids)
                checks["both_linked_strategies_read"] = {
                    setup_id for setup_id in linked_ids if isinstance(setup_id, int)
                } == {base, apple}
                checks["conditions_compared"] = (
                    "BTC Full Base" in answer and "Apple Full Setup" in answer
                    and _has_number(answer, 76000) and _has_number(answer, 210)
                    and "ETH Full Setup" not in answer
                )
            if sequence_number == 11 and turn_number == 2:
                checks["saved_entry_without_invented_confirmation"] = (
                    "BTC Full Base" in answer and "76.000" in answer
                    and "80.000" not in answer
                    and any(word in answer.casefold() for word in ("geen", "niet", "ontbreekt"))
                )
            if sequence_number == 11 and turn_number == 1:
                checks["entry_source_not_misattributed"] = (
                    "Ik kan dit nog niet onderbouwen" not in answer
                    and ("76.000" not in answer or "strateg" in answer.casefold())
                    and not re.search(
                        r"\bin\s+BTC Full Base\s+staat[^.!?\n]{0,80}"
                        r"\b(?:entry|instapwaarde|instapprijs)\b", answer, re.I,
                    )
                )
            if sequence_number == 12 and turn_number == 4:
                checks["verified_strategy_followup"] = (
                    _has_number(answer, 76000) and not _has_number(answer, 80000)
                    and any(word in answer.casefold() for word in ("geen", "niet", "ontbreekt"))
                    and "Ik kan dit nog niet onderbouwen" not in answer
                )
            if sequence_number == 13 and turn_number == 1:
                ambiguous = [
                    item for call in trace for item in (call.get("result") or {}).get("results") or []
                    if item.get("scope") == "read_linked_strategy"
                    and item.get("reason") == "strategy_ambiguous"
                ]
                checks["ambiguous_link_not_silently_selected"] = bool(ambiguous) and not re.search(
                    r"Apple (?:Full|Retest) Strategy.{0,100}(?:entry|stop)", answer, re.I,
                )
            if sequence_number == 13 and turn_number == 2:
                checks["explicit_strategy_resolved"] = any(
                    item.get("scope") == "read_linked_strategy"
                    and item.get("status") == "completed"
                    and (item.get("data") or {}).get("name") == "Apple Full Strategy"
                    for call in trace for item in (call.get("result") or {}).get("results") or []
                )
            if sequence_number == 14 and turn_number == 2:
                linked = [
                    item for call in trace for item in (call.get("result") or {}).get("results") or []
                    if item.get("scope") == "read_linked_strategy"
                    and item.get("status") == "completed"
                ]
                checks["both_strategies_read"] = {
                    (item.get("data") or {}).get("name") for item in linked
                } >= {"BTC Full Base Strategy", "Apple Full Strategy"}
                checks["comparison_answered"] = (
                    "BTC Full Base Strategy" in answer and "Apple Full Strategy" in answer
                    and _has_number(answer, 76000) and _has_number(answer, 210)
                    and "Ik heb je vraag nog niet volledig" not in answer
                )
            if sequence_number == 14 and turn_number == 3:
                checks["selected_strategy_pronoun"] = (
                    "Apple Full Strategy" in answer and "190" in answer
                    and "72.000" not in answer
                    and "Ik kan dit nog niet onderbouwen" not in answer
                )
            if sequence_number == 14 and turn_number == 4:
                checks["selected_strategy_followup"] = (
                    any(
                        item.get("scope") == "read_linked_strategy"
                        and item.get("status") == "completed"
                        and (item.get("data") or {}).get("name") == "Apple Full Strategy"
                        for call in trace for item in (call.get("result") or {}).get("results") or []
                    ) and "210" in answer and "190" in answer
                    and "Ik kan dit nog niet onderbouwen" not in answer
                )
            if sequence_number == 15:
                linked_names = {
                    str(strategy.get("name") or "")
                    for call in trace
                    for item in (call.get("result") or {}).get("results") or []
                    if item.get("status") == "completed"
                    for strategy in (
                        (item.get("data") or {}).get("strategies") or []
                        if item.get("scope") == "read_linked_strategies" else
                        [item.get("data") or {}] if item.get("scope") == "read_linked_strategy" else []
                    )
                    if isinstance(strategy, dict)
                }
                checks["both_eth_setups_compared"] = (
                    "ETH Full Setup" in answer and "ETH QA Tweede Setup" in answer
                    and "ETH Full Strategy" in answer and "ETH QA Tweede Strategy" in answer
                    and {"ETH Full Strategy", "ETH QA Tweede Strategy"} <= linked_names
                    and "4H" in answer and "score" in answer.casefold()
                    and "stop" in answer.casefold()
                    and any(item.get("scope") == "read_asset_scores" and item.get("status") == "completed"
                            for call in trace for item in (call.get("result") or {}).get("results") or [])
                    and "FINN kon dit antwoord niet afronden" not in answer
                    and exchange.get("answer_kind") != "saved_setup_collection"
                )
            if sequence_number == 16:
                named = {"ETH Full Setup", *(f"ETH QA Setup {index}" for index in range(2, 8))}
                saved_rows = [
                    row
                    for call in trace
                    for item in (call.get("result") or {}).get("results") or []
                    if item.get("scope") == "read_saved_setup_inventory"
                    for row in (item.get("data") or {}).get("setups") or []
                ]
                linked = [
                    item for call in trace
                    for item in (call.get("result") or {}).get("results") or []
                    if item.get("scope") == "read_linked_strategies"
                    and item.get("status") == "completed"
                ]
                checks["complete_eth_comparison_evidence"] = (
                    {str(row.get("name") or "") for row in saved_rows} == named
                    and len({(item.get("data") or {}).get("setup_id") for item in linked}) == 7
                    and any(item.get("scope") == "read_asset_scores"
                            for call in trace
                            for item in (call.get("result") or {}).get("results") or [])
                    and len(trace) == 1
                )
                checks["all_eth_setups_answered"] = (
                    all(name in answer for name in named)
                    and "FINN kon dit antwoord niet afronden" not in answer
                    and "BTC Other" not in answer
                )
            if sequence_number == 17:
                rows_by_name = {
                    index: next((line for line in answer.splitlines()
                                 if f"ETH QA Bot Setup {index}" in line), "")
                    for index in range(2, 8)
                }
                checks["bot_links_stay_with_their_setup"] = (
                    all(rows_by_name.values())
                    and "ETH QA Paper Bot 2" in rows_by_name[2]
                    and "ETH QA Paper Bot 5" in rows_by_name[5]
                    and all("geen bot" in rows_by_name[index].casefold()
                            for index in (3, 4, 6, 7))
                )
                checks["analysis_timeframe_distinct_from_dca_schedule"] = (
                    all("1D" in rows_by_name[index] and "maandag" in rows_by_name[index].casefold()
                        for index in (2, 4))
                    and not re.search(r"\bas_of\b", answer)
                )
            if sequence_number == 18:
                checks["mixed_plan_answer_complete"] = (
                    all(f"ETH QA Bot Setup {index}" in answer for index in range(2, 8))
                    and "ETH Full Setup" in answer
                    and "1D" in answer and "4H" in answer
                    and not re.search(r"\bas_of\b", answer)
                )
            if sequence_number == 19:
                rows_by_name = {
                    index: next((line for line in answer.splitlines()
                                 if f"ETH QA Bot Setup {index}" in line), "")
                    for index in range(2, 8)
                }
                checks["five_bots_have_one_consistent_total"] = (
                    all(f"ETH QA Paper Bot {index}" in rows_by_name[index]
                        for index in (2, 3, 4, 5, 6))
                    and "geen" in rows_by_name[7].casefold()
                    and "ETH QA Paper Bot" not in rows_by_name[7]
                    and not re.search(r"\bvier\s+(?:gekoppelde\s+)?paper.?bots?\b", answer.casefold())
                    and not re.search(r"\b4\s+(?:gekoppelde\s+)?paper.?bots?\b", answer.casefold())
                    and not re.search(r"\bas_of\b", answer)
                )
            if sequence_number in {20, 21} and turn_number == 1:
                checks["score_bound_counts"] = (
                    all(f"ETH QA Bot Setup {index}" in answer for index in range(2, 8))
                    and "ETH Full Setup" in answer
                    and _explicit_group_count(answer, "0", 3)
                    and _explicit_group_count(answer, "30", 3)
                    and _explicit_group_count(answer, "geen", 1)
                )
            if sequence_number == 20 and turn_number == 2:
                checks["german_followup"] = (
                    "1D" in answer
                    and any(word in answer.casefold() for word in ("setup", "setups"))
                    and not re.search(r"\b(?:ik|mijn|jouw|geen|welke|deze|bedoelde)\b", answer.casefold())
                )
            cases.append({"sequence": sequence_number, "turn": turn_number,
                          "run_id": observed["run_id"], "message": message,
                          "answer": answer, "answer_kind": exchange.get("answer_kind"),
                          "checks": checks, "pass": all(checks.values())})
            if observed["status"] == "completed":
                current_linked_ids = {
                    (item.get("data") or {}).get("setup_id")
                    for call in trace for item in (call.get("result") or {}).get("results") or []
                    if item.get("scope") == "read_linked_strategy"
                    and item.get("status") == "completed"
                }
                if current_linked_ids:
                    last_verified_linked_setup_ids = {
                        setup_id for setup_id in current_linked_ids if isinstance(setup_id, int)
                    }
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
