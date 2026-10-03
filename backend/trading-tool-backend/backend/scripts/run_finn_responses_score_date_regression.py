#!/usr/bin/env python3
"""Synthetic local API/Celery/Responses regression for dated saved scores."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

from sqlalchemy import text

from backend.infrastructure.database import sync_engine
from backend.scripts.run_finn_v2_full_action_matrix import _create_local_user, _runtime_record
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.utils.auth_utils import create_access_token


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not args.base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise SystemExit("local-only regression")

    user = _create_local_user()
    report_date = date.today() - timedelta(days=2)
    with sync_engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO daily_scores
                (user_id, report_date, symbol, market_score, macro_score, technical_score)
            VALUES (:user_id, :report_date, 'BTC', 100, 100, 75)
        """), {"user_id": user["id"], "report_date": report_date})

    token = create_access_token({"sub": str(user["id"]), "role": "user"})
    questions = (
        "Van welke datum zijn mijn opgeslagen BTC-scores voor Markt, Macro en Technisch? "
        "Noem de drie scores en wat hun brondatum betekent. Verander niets.",
        "Zijn die drie scores daarmee een actueel instapsignaal?",
    )
    artifact = {"synthetic_local_only": True, "report_date": str(report_date), "cases": []}
    conversation_id = None
    for question in questions:
        observed = run_gate(
            base_url=args.base_url, bearer_token=token, message=question,
            conversation_id=conversation_id, timeout_seconds=90,
        )
        conversation_id = observed["conversation_id"]
        record = _runtime_record(observed["run_id"])
        state = record["runtime_state"]
        answer = str((state.get("terminal_response") or {}).get("content") or "")
        trace = (state.get("responses_exchange") or {}).get("tool_trace") or []
        score_evidence = [
            item for call in trace
            for item in (call.get("result") or {}).get("results") or []
            if item.get("scope") == "read_asset_scores" and item.get("status") == "completed"
        ]
        checks = {
            "completed": observed["status"] == "completed",
            "one_dispatch": observed["dispatch_count"] == observed["attempt_count"] == 1,
            "read_only": record["proposal"] is None,
            "no_failure_copy": "FINN kon dit antwoord niet afronden" not in answer,
        }
        if question == questions[0]:
            checks.update({
                "score_read": bool(score_evidence),
                "latest_saved_date": any(item.get("as_of") == str(report_date) for item in score_evidence),
                "score_values": all(value in answer for value in ("100", "75")),
                "date_in_answer": str(report_date.year) in answer,
            })
        else:
            lower = answer.casefold()
            checks["no_current_trade_signal"] = "signaal" in lower and (
                "geen" in lower or "niet" in lower
            )
        artifact["cases"].append({
            "question": question, "run_id": observed["run_id"],
            "status": observed["status"], "answer": answer,
            "tool_names": [call.get("name") for call in trace],
            "checks": checks,
        })

    artifact["pass"] = all(all(case["checks"].values()) for case in artifact["cases"])
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "pass": artifact["pass"],
        "checks": [case["checks"] for case in artifact["cases"]],
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }, ensure_ascii=False))
    if not artifact["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
