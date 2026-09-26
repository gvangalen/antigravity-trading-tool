#!/usr/bin/env python3
"""Exercise explicit chat-language switches through the public local FINN route."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import text

from backend.infrastructure.database import sync_engine
from backend.scripts.run_finn_v2_full_action_matrix import _create_local_user, _insert_setup, _runtime_record
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.services.finn_v2_responses_answer_verifier import FinnResponsesAnswerVerifier
from backend.utils.auth_utils import create_access_token


TURNS = (
    ("Antwoord vanaf nu in het Engels. Wat weet je over mijn BTC-setup?", "en"),
    ("Why?", "en"),
    ("Antworte ab jetzt auf Deutsch. Was fehlt meinem BTC-Plan noch?", "de"),
    ("Warum?", "de"),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.base_url.startswith(("http://localhost:", "http://127.0.0.1:")):
        raise SystemExit("This regression is local-only")
    user = _create_local_user()
    with sync_engine.begin() as connection:
        connection.execute(text("UPDATE users SET ai_preferences = CAST(:preferences AS jsonb) WHERE id = :user_id"), {
            "user_id": user["id"],
            "preferences": json.dumps({"selected_asset": "BTC", "locale": "nl"}),
        })
        _insert_setup(connection, user["id"], "Taalcontinuiteit BTC", setup_type="dca")
    token = create_access_token({"sub": str(user["id"]), "role": "user"})
    artifact = {"version": 1, "synthetic_local_only": True, "cases": []}
    conversation_id = None
    for message, expected_locale in TURNS:
        observed = run_gate(
            base_url=args.base_url, bearer_token=token, message=message,
            conversation_id=conversation_id, timeout_seconds=75,
        )
        conversation_id = observed["conversation_id"]
        record = _runtime_record(observed["run_id"])
        answer = str((record["runtime_state"].get("terminal_response") or {}).get("content") or "")
        with sync_engine.connect() as connection:
            cursor = connection.execute(text(
                "SELECT context_json -> 'responses_cursor' FROM finn_v2_conversations "
                "WHERE id = :conversation_id AND user_id = :user_id"
            ), {"conversation_id": conversation_id, "user_id": user["id"]}).scalar_one()
        checks = {
            "terminal": observed["status"] in {"completed", "clarification_required"},
            "answer_present": bool(answer.strip()),
            "language": FinnResponsesAnswerVerifier._language_matches(answer, expected_locale),
            "cursor_locale": (cursor or {}).get("locale") == expected_locale,
            "one_dispatch_attempt": observed["dispatch_count"] == observed["attempt_count"] == 1,
            "polling_sse_parity": bool(observed["polling_sse_contract_projection"]),
            "no_proposal": not record["proposal"],
        }
        artifact["cases"].append({
            "question": message, "run_id": observed["run_id"], "answer": answer,
            "expected_locale": expected_locale, "status": observed["status"],
            "elapsed_ms": observed["elapsed_ms"], "checks": checks, "pass": all(checks.values()),
        })
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(args.output)
    artifact["pass"] = all(case["pass"] for case in artifact["cases"])
    args.output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    if not artifact["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
