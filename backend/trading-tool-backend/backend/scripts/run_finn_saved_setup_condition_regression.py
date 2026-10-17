"""Local public-route multi-turn check for a saved Friday DCA preset.

Creates only a disposable synthetic local user and never confirms an action.
The artifact contains answers and read scopes, never bearer credentials.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import text

from backend.infrastructure.database import sync_engine
from backend.scripts.run_finn_v2_full_action_matrix import _create_local_user, _runtime_record
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.utils.auth_utils import create_access_token


QUESTIONS = (
    "Wat heb ik voor mijn BTC-DCA opgeslagen: de weekdag, marktsituatie, mijn toelichting en het bedrag? Verander niets.",
    "Wat betekent mijn keuze ‘Onder druk’ voor deze vrijdag-DCA? Koop ik dan zeker voor €100, of moet er nog iets worden gecontroleerd?",
    "En als je geen actuele geverifieerde marktscore hebt, kun je dan zeggen of deze vrijdag een aankoop volgt?",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if urlparse(args.base_url).hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("local_synthetic_fixture_only")

    user = _create_local_user()
    with sync_engine.begin() as connection:
        setup_id = connection.execute(text("""
            INSERT INTO setups (
                user_id, name, symbol, timeframe, setup_type, dca_frequency,
                dca_day, description, min_market_score, max_market_score, created_at
            ) VALUES (
                :user_id, 'Vrijdag BTC DCA', 'BTC', '1D', 'dca', 'weekly',
                '5', 'Ik wil geduldig opbouwen; dit is mijn vrije toelichting.',
                26, 45, NOW()
            ) RETURNING id
        """), {"user_id": user["id"]}).scalar_one()
        connection.execute(text("""
            INSERT INTO strategies (
                user_id, setup_id, name, setup_type, execution_mode,
                base_amount, data, created_at
            ) VALUES (
                :user_id, :setup_id, 'Vrijdag BTC €100', 'dca', 'fixed',
                100, CAST(:data AS jsonb), NOW()
            )
        """), {
            "user_id": user["id"], "setup_id": setup_id,
            "data": json.dumps({"name": "Vrijdag BTC €100", "base_amount": 100,
                                "execution_mode": "fixed"}),
        })

    turns = []
    conversation_id = None
    for index, question in enumerate(QUESTIONS):
        # A fresh token on the second turn represents a new authenticated session.
        token = create_access_token({"sub": str(user["id"]), "role": "user"})
        observed = run_gate(
            base_url=args.base_url, bearer_token=token, message=question,
            conversation_id=conversation_id, timeout_seconds=90,
        )
        conversation_id = observed["conversation_id"]
        state = _runtime_record(observed["run_id"])["runtime_state"]
        answer = str((state.get("terminal_response") or {}).get("content") or "")
        read_scopes = [
            item.get("scope")
            for call in ((state.get("responses_exchange") or {}).get("tool_trace") or [])
            for item in ((call.get("result") or {}).get("results") or [])
            if item.get("status") == "completed"
        ]
        checks = {
            "completed": observed["status"] == "completed",
            "answer_visible": bool(answer.strip()),
            "polling_sse_parity": bool(observed["polling_sse_contract_projection"]),
            "no_false_description_only_claim": not any(
                phrase in answer.casefold() for phrase in (
                    "slechts onderdeel van de beschrijving", "geen vastgelegde dca-voorwaarde",
                    "geen scoregrens", "alleen een beschrijving",
                )
            ),
            "no_guaranteed_purchase": not any(
                phrase in answer.casefold() for phrase in (
                    "koop je zeker", "wordt zeker gekocht", "aankoop is gegarandeerd",
                )
            ),
        }
        if index == 0:
            checks["owner_scoped_setup_read"] = "read_active_setup" in read_scopes
            checks["saved_weekday_and_condition"] = (
                "vrijdag" in answer.casefold() and "onder druk" in answer.casefold()
                and "26" in answer and "45" in answer
            )
            checks["strategy_amount_separate"] = "100" in answer
        if index in (1, 2):
            checks["uncertain_purchase_without_current_score"] = (
                "niet" in answer.casefold() and "score" in answer.casefold()
                and "garande" in answer.casefold()
            )
        turns.append({
            "question": question, "answer": answer, "status": observed["status"],
            "run_id": observed["run_id"], "read_scopes": read_scopes,
            "checks": checks, "pass": all(checks.values()),
        })
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({
            "synthetic_local_only": True, "setup_id": setup_id,
            "turns": turns, "complete": len(turns) == len(QUESTIONS),
            "pass": len(turns) == len(QUESTIONS) and all(turn["pass"] for turn in turns),
        }, ensure_ascii=False, indent=2) + "\n")

    if not all(turn["pass"] for turn in turns):
        raise SystemExit("saved_setup_condition_regression_failed")


if __name__ == "__main__":
    main()
