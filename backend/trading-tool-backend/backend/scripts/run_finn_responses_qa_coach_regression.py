#!/usr/bin/env python3
"""Local public-route regression for declassified live coach questions."""

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


QUESTIONS = (
    "Ik twijfel of ik vandaag nog een BTC-trade moet nemen. Mijn plan zegt wachten op "
    "bevestiging, maar ik ben bang de beweging te missen. Denk met me mee.",
    "Beoordeel mijn BTC Breakout Full plan alsof je mijn trading coach bent. Wat is "
    "sterk, waar zou je me nu afremmen en wat is mijn eerstvolgende concrete check?",
    "Mijn BTC Breakout Full Strategy heeft entry 80000, stop-loss 76000 en targets "
    "88000 en 92000. Zonder actuele koers: wat zegt de verhouding tussen risico en "
    "potentiële opbrengst, en wat kan je daarmee nog niet concluderen?",
    "Wat zijn vandaag mijn drie belangrijkste acties voor mijn bestaande BTC-plan, "
    "en wat moet ik juist laten liggen?",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", required=True)
    parser.add_argument("--case", type=int, choices=range(1, len(QUESTIONS) + 1))
    args = parser.parse_args()
    if not args.base_url.startswith(("http://localhost:", "http://127.0.0.1:")):
        raise SystemExit("This regression is local-only")
    user = _create_local_user()
    with sync_engine.begin() as connection:
        setup_id = _insert_setup(connection, user["id"], "BTC Breakout Full")
        strategy_id = _insert_strategy(connection, user["id"], setup_id, "BTC Breakout Full Strategy")
        connection.execute(text("""
            UPDATE strategies SET entry = 80000, stop_loss = 76000,
                targets = ARRAY[88000, 92000]::NUMERIC[],
                data = CAST(:data AS jsonb) WHERE id = :strategy_id AND user_id = :user_id
        """), {
            "strategy_id": strategy_id, "user_id": user["id"],
            "data": json.dumps({
                "name": "BTC Breakout Full Strategy", "execution_mode": "fixed",
                "base_amount": 100, "entry": 80000, "stop_loss": 76000,
                "targets": [88000, 92000],
            }),
        })
    token = create_access_token({"sub": str(user["id"]), "role": "user"})
    artifact = {"synthetic_local_only": True, "cases": []}
    for index, question in enumerate(QUESTIONS):
        if args.case is not None and index + 1 != args.case:
            continue
        observed = run_gate(
            base_url=args.base_url, bearer_token=token, message=question,
            timeout_seconds=75,
        )
        record = _runtime_record(observed["run_id"])
        state = record["runtime_state"]
        answer = str((state.get("terminal_response") or {}).get("content") or "")
        checks = {
            "terminal": observed["status"] == "completed",
            "one_dispatch_attempt": observed["dispatch_count"] == observed["attempt_count"] == 1,
            "polling_sse_parity": bool(observed["polling_sse_contract_projection"]),
            "no_proposal": record["proposal"] is None,
            "no_generic_fallback": all(phrase not in answer.casefold() for phrase in (
                "ik kan dit nog niet onderbouwen met betrouwbare gegevens",
                "ik kan nog niet beoordelen of dit bij je risicostijl past",
            )),
        }
        lower_answer = answer.casefold()
        checks["no_internal_runtime_keys"] = not bool(re.search(
            r"\b[a-z]+(?:_[a-z0-9]+)+\b", answer,
        ))
        checks["no_unsupported_level_advice"] = not bool(re.search(
            r"\b(?:stel|zet|set|place|activeer|activate)\b[^.!?;\n]{0,65}"
            r"\b(?:stop.?loss|target|doel|entry|instap|strategie|strategy|order)\b"
            r"|\b(?:pas\s+aan|adjust|change)\b[^.!?;\n]{0,65}"
            r"\b(?:doel|target|price|prijs|markt|market)\b"
            r"|\b(?:risico.?opbrengst\w*|risico.?rendement\w*|risk.?reward\w*|"
            r"reward.?risk\w*|verhouding\w*|ratio\w*)\b[^.!?;\n]{0,55}"
            r"\b(?:aantrekkelijk\w*|gunstig\w*|positiev\w*|positief|beter|"
            r"attractive|favorable|favourable|positive|better)\b"
            r"|\b(?:aantrekkelijk\w*|gunstig\w*|positiev\w*|positief|beter|"
            r"attractive|favorable|favourable|positive|better)\b"
            r"[^.!?;\n]{0,55}\b(?:verhouding\w*|ratio\w*)\b",
            answer, re.IGNORECASE,
        ))
        checks["no_unsupported_trade_planning"] = not bool(re.search(
            r"\b(?:winstneming\w*|profit.?tak\w*)\b[^.!?;\n]{0,20}"
            r"\b(?:plannen|plan|nemen|take)\b"
            r"|\b(?:plan|neem|take)\s+(?:je\s+)?(?:winstneming\w*|profit.?tak\w*)\b",
            answer, re.IGNORECASE,
        ))
        if index == 0:
            checks["no_unrequested_priority_list"] = not all(
                re.search(rf"(?m)^\s*{number}[.)]", answer) for number in (1, 2, 3)
            )
        elif index == 1:
            checks["balanced_review"] = (
                any(word in lower_answer for word in ("sterk", "pluspunt", "duidelijk", "meetbaar"))
                and any(word in lower_answer for word in ("risico", "afrem", "zwak", "beperking"))
                and any(word in lower_answer for word in ("controleer", "controleren", "check", "verifieer"))
            )
            checks["strategy_levels_not_attributed_to_setup"] = not bool(re.search(
                r"\bsetup\b[^.!?\n]{0,80}\b(?:met|heeft)\b[^.!?\n]{0,45}"
                r"\b(?:entry|instap|stop.?loss|targets?|doelen)\b",
                answer, re.IGNORECASE,
            ))
        elif index == 2:
            checks["risk_reward_math"] = (
                bool(re.search(r"(?:1:2|2:1|\b2[.,]0+\b|twee keer)", lower_answer))
                and bool(re.search(r"(?:1:3|3:1|\b3[.,]0+\b|drie keer)", lower_answer))
                and any(word in lower_answer for word in ("4.000", "4000", "5%", "5 procent"))
            )
        elif index == 3:
            checks["three_priorities_and_avoidance"] = (
                all(re.search(rf"\b{number}[.)]", answer) for number in (1, 2, 3))
                and any(word in lower_answer for word in ("laat", "vermijd", "niet doen", "negeer niet"))
            )
        artifact["cases"].append({
            "case": index + 1, "question": question, "run_id": observed["run_id"],
            "status": observed["status"], "operation_id": observed["final_operation_id"],
            "tool_names": [item.get("name") for item in (state.get("responses_exchange") or {}).get("tool_trace") or []],
            "candidate_answer": str((state.get("responses_exchange") or {}).get("answer") or ""),
            "answer": answer, "checks": checks, "pass": all(checks.values()),
        })
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    artifact["pass"] = all(case["pass"] for case in artifact["cases"])
    Path(args.output).write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    if not artifact["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
