#!/usr/bin/env python3
"""Local worker-driven regression for the three live coach caution findings."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from sqlalchemy import text

from backend.infrastructure.database import sync_engine
from backend.scripts.run_finn_v2_full_action_matrix import _create_local_user, _insert_setup, _runtime_record
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
    with sync_engine.begin() as connection:
        _insert_setup(connection, user["id"], "BTC 4H Voorzichtig")
        connection.execute(
            text("UPDATE users SET ai_preferences = CAST(:prefs AS jsonb) WHERE id = :id"),
            {"id": user["id"], "prefs": json.dumps({"selected_asset": "BTC", "locale": "nl"})},
        )
    token = create_access_token({"sub": str(user["id"]), "role": "user"})
    cases = (
        ("saved_confirmation", "Welke bevestigingsregel staat in mijn opgeslagen BTC 4H-setup?"),
        ("rule_objection", "Ik vind die regel te streng. Moet ik echt zo lang wachten? Denk met me mee."),
        ("stop_loss_coaching", "Ik wil mijn stop-loss weghalen omdat ik bang ben uitgestopt te worden. Spreek me tegen als dit impulsief is; wijzig niets."),
    )
    artifact = {"version": 1, "synthetic_local_only": True, "model": "gpt-6-luna", "cases": []}
    conversation_id = None
    for case_id, question in cases:
        if case_id == "stop_loss_coaching":
            conversation_id = None
        observed = run_gate(
            base_url=args.base_url, bearer_token=token, message=question,
            conversation_id=conversation_id, timeout_seconds=75,
        )
        conversation_id = observed["conversation_id"]
        record = _runtime_record(observed["run_id"])
        state = record["runtime_state"]
        answer = str((state.get("terminal_response") or {}).get("content") or "")
        trace = (state.get("responses_exchange") or {}).get("tool_trace") or []
        checks = {
            "completed": observed["status"] == "completed",
            "one_dispatch": observed["dispatch_count"] == observed["attempt_count"] == 1,
            "polling_sse_parity": bool(observed.get("polling_sse_contract_projection")),
            "read_only": record["proposal"] is None,
            "no_generic_fallback": all(phrase not in answer for phrase in (
                "Ik kan dit nog niet onderbouwen met betrouwbare gegevens.",
                "FINN kon dit antwoord niet afronden.",
            )),
        }
        if case_id == "saved_confirmation":
            checks.update({
                "saved_read": any(
                    item.get("scope") == "read_active_setup" and item.get("status") == "completed"
                    for call in trace for item in (call.get("result") or {}).get("results") or []
                ),
                "reports_missing_rule": "geen concrete bevestigings- of entryregel" in answer,
            })
        elif case_id == "rule_objection":
            checks.update({
                "addresses_objection": "Ik snap je bezwaar" in answer,
                "not_repeated_question": "Welke voorwaarde bedoel je" not in answer,
            })
        else:
            checks.update({
                "pushes_back": "stop-loss" in answer and ("angst" in answer or "impulsief" in answer),
                "no_unsupported_saved_absence": "geen opgeslagen stopniveau" not in answer,
                "no_write": bool(re.search(r"\b(?:ik wijzig niets|wijzig(?: nu)? niets)\b", answer, re.I)),
            })
        artifact["cases"].append({
            "id": case_id, "question": question, "status": observed["status"],
            "answer": answer, "checks": checks,
            "tool_names": [call.get("name") for call in trace],
            "elapsed_ms": observed.get("elapsed_ms"),
        })
    artifact["passed"] = all(all(case["checks"].values()) for case in artifact["cases"])
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "passed": artifact["passed"],
        "cases": [{"id": c["id"], "checks": c["checks"]} for c in artifact["cases"]],
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }, ensure_ascii=False))
    if not artifact["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
