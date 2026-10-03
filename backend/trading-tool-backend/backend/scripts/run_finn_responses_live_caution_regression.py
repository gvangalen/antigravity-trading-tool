#!/usr/bin/env python3
"""Local worker-driven regression for the reported live coach conversation."""

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
        _insert_setup(connection, user["id"], "BTC 4H Alternatief")
        dca_id = _insert_setup(connection, user["id"], "BTC DCA Maandag", setup_type="dca")
        connection.execute(text("UPDATE setups SET timeframe = '1D' WHERE id = :id"), {"id": dca_id})
        connection.execute(
            text("UPDATE users SET ai_preferences = CAST(:prefs AS jsonb) WHERE id = :id"),
            {"id": user["id"], "prefs": json.dumps({"selected_asset": "BTC", "locale": "nl"})},
        )
    token = create_access_token({"sub": str(user["id"]), "role": "user"})
    cases = (
        ("saved_confirmation", "Welke bevestigingsvoorwaarde staat concreet in mijn opgeslagen 4H-setup? En welke van mijn BTC-setups bedoel je eigenlijk?"),
        ("stop_loss_coaching", "Ik wil mijn stop-loss weghalen omdat BTC anders te vroeg wordt uitgestopt. Ik vraag je om coaching, niet om iets te wijzigen. Hoe kijk je hiernaar?"),
        ("hypothetical_reflection", "Stel: ik nam deze maand 8 impulsieve trades, 6 verlies en 2 winst, samen -4,2%. Wat is volgens jou het belangrijkste patroon en welke ene regel zou ik volgende week testen?"),
        ("stop_loss_fresh", "Ik wil mijn stop-loss weghalen omdat BTC anders te vroeg wordt uitgestopt. Ik vraag je om coaching, niet om iets te wijzigen. Hoe kijk je hiernaar?"),
    )
    artifact = {"version": 1, "synthetic_local_only": True, "model": "gpt-6-luna", "cases": []}
    conversation_id = None
    for case_id, question in cases:
        if case_id == "stop_loss_fresh":
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
                    item.get("scope") in {"read_active_setup", "read_saved_setup_inventory"}
                    and item.get("status") == "completed"
                    for call in trace for item in (call.get("result") or {}).get("results") or []
                ),
                "identifies_or_disambiguates": all(
                    name in answer for name in ("BTC 4H Voorzichtig", "BTC 4H Alternatief")
                ) and "BTC DCA Maandag" not in answer,
                "reports_missing_rule_or_asks": "geen concrete bevestigings- of entryregel" in answer or "Welke" in answer,
            })
        elif case_id == "hypothetical_reflection":
            checks.update({
                "answers_pattern": "impuls" in answer.casefold() or "6 van de 8" in answer,
                "not_a_setup_card": "setup voorbereiden" not in answer.casefold(),
                "stays_hypothetical": bool(re.search(r"\b(?:voorbeeld|stel|hypothetisch)\b", answer, re.I)),
            })
        else:
            checks.update({
                "pushes_back": "stop" in answer.casefold() and bool(re.search(
                    r"\b(?:verlies|exitregel|risico|grens|angst)\b", answer, re.I,
                )),
                "no_unsupported_saved_absence": "geen opgeslagen stopniveau" not in answer,
                "no_unrelated_setup": all(
                    name not in answer for name in ("BTC 4H Voorzichtig", "BTC 4H Alternatief")
                ),
                "no_mental_stop_substitute": not bool(re.search(
                    r"\bhoeft.{0,30}niet.{0,20}order\b", answer, re.I,
                )),
                "no_write": record["proposal"] is None,
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
