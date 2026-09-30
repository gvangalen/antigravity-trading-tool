"""Public-route, real-provider multi-turn coach evidence for a synthetic local user."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import text

from backend.infrastructure.database import sync_engine
from backend.scripts.run_finn_v2_full_action_matrix import (
    _create_local_user, _insert_setup, _proposal_lifecycle, _runtime_record,
)
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.services.finn_v2_responses_answer_verifier import FinnResponsesAnswerVerifier
from backend.utils.auth_utils import create_access_token


CONVERSATIONS = {
    "nl": (
        "Ik twijfel of ik me aan mijn regel moet houden om op bevestiging te wachten voordat ik een BTC-trade neem. Denk met me mee over die keuze; verander niets.",
        "Waarom zou ik op die bevestiging wachten?",
        "Welke BTC-setup heb ik opgeslagen?",
        "Wat betekent die setup voor de afweging van zojuist?",
    ),
    "en": (
        "I am torn about sticking to my rule of waiting for confirmation before a BTC trade. Think that choice through with me; change nothing.",
        "Why wait for that confirmation?",
        "Which BTC setup have I saved?",
        "How does that setup affect the decision we just discussed?",
    ),
    "de": (
        "Ich bin unsicher, ob ich meiner Regel folgen soll, vor einem BTC-Trade auf Bestätigung zu warten. Denk mit mir über diese Entscheidung nach; ändere nichts.",
        "Warum sollte ich auf diese Bestätigung warten?",
        "Welches BTC-Setup habe ich gespeichert?",
        "Was bedeutet dieses Setup für unsere vorige Abwägung?",
    ),
}

ALTERNATE_CONVERSATIONS = {
    "nl": (
        "BTC beweegt en ik ben bang de kans te missen. Ik had mezelf voorgenomen pas na een duidelijk signaal te handelen. Denk met me mee, zonder iets te wijzigen.",
        "Waarom is zo'n vooraf gekozen controle nuttig als ik daardoor een beweging mis?",
        "Lees mijn opgeslagen BTC-setup.",
        "Wat zegt die setup over mijn keuze van daarnet, zonder actuele koers aan te nemen?",
    ),
    "en": (
        "BTC is moving and I fear missing out. I intended to act only after a clear signal. Help me weigh this without changing anything.",
        "Why use that prior check if it means I might miss the move?",
        "Read my saved BTC setup.",
        "What does that setup add to the earlier choice without assuming a current quote?",
    ),
    "de": (
        "BTC bewegt sich und ich habe Angst, die Chance zu verpassen. Ich wollte erst nach einem klaren Signal handeln. Denk mit mir darüber nach, ohne etwas zu ändern.",
        "Warum ist diese vorher festgelegte Prüfung sinnvoll, wenn ich die Bewegung verpasse?",
        "Lies mein gespeichertes BTC-Setup.",
        "Was trägt dieses Setup zu unserer früheren Entscheidung bei, ohne einen aktuellen Kurs anzunehmen?",
    ),
}

STRATEGY_REQUESTS = {
    "nl": "Maak voor {setup} een strategie met de naam {strategy}, vaste uitvoering van 100 euro, entry 76000, stop-loss 72000, targets 83000 en 87000 en gebalanceerd risico.",
    "en": "Create a strategy for {setup} named {strategy}, fixed execution of 100 euros, entry 76000, stop-loss 72000, targets 83000 and 87000, with balanced risk.",
    "de": "Erstelle für {setup} eine Strategie namens {strategy}, feste Ausführung mit 100 Euro, Einstieg 76000, Stop-Loss 72000, Ziele 83000 und 87000 und ausgewogenem Risiko.",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--locale", choices=tuple(CONVERSATIONS))
    parser.add_argument("--variant", choices=("baseline", "alternate"), default="baseline")
    parser.add_argument("--include-proposal", action="store_true")
    args = parser.parse_args()
    if urlparse(args.base_url).hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("coach_gate_requires_loopback")
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "synthetic_local_only": True,
        "chat_model": os.getenv("FINN_RESPONSES_CHAT_MODEL", "gpt-6-luna"),
        "verifier_model": os.getenv("FINN_V2_SEMANTIC_VERIFIER_MODEL", "gpt-6-sol"),
        "conversations": [], "action_followups": [], "complete": False,
    }
    prompts_by_locale = ALTERNATE_CONVERSATIONS if args.variant == "alternate" else CONVERSATIONS
    selected_conversations = (
        {args.locale: prompts_by_locale[args.locale]} if args.locale else prompts_by_locale
    )
    for locale, prompts in selected_conversations.items():
        user = _create_local_user()
        setup_name = f"Coach {args.variant} {locale.upper()} BTC Setup"
        with sync_engine.begin() as connection:
            connection.execute(
                text("UPDATE users SET ai_preferences = CAST(:preferences AS jsonb) WHERE id = :user_id"),
                {"preferences": json.dumps({
                    "selected_asset": "BTC", "locale": locale,
                    "trader_types": ["swing_trader"], "primary_timeframes": ["4h"],
                    "asset_focus": ["bitcoin"], "investment_goals": ["capital_preservation"],
                    "risk_profiles": ["balanced"],
                }), "user_id": user["id"]},
            )
            _insert_setup(connection, user["id"], setup_name)
        token = create_access_token({"sub": str(user["id"]), "role": "user"})
        conversation_id = None
        turns = []
        for turn_index, message in enumerate(prompts):
            observed = run_gate(
                base_url=args.base_url, bearer_token=token, message=message,
                conversation_id=conversation_id, timeout_seconds=75,
            )
            conversation_id = observed["conversation_id"]
            persisted = _runtime_record(observed["run_id"])
            state = persisted["runtime_state"]
            answer = str((state.get("terminal_response") or {}).get("content") or "")
            tool_names = [
                item.get("name") for item in
                (state.get("responses_exchange") or {}).get("tool_trace") or []
            ]
            checks = {
                "terminal": observed["status"] in {"completed", "clarification_required"},
                "answer_visible": bool(answer.strip()),
                "one_dispatch_attempt": observed["dispatch_count"] == 1 and observed["attempt_count"] <= 1,
                "polling_sse_parity": bool(observed["polling_sse_contract_projection"]),
                "no_proposal": persisted["proposal"] is None,
                "no_internal_identifier": not FinnResponsesAnswerVerifier._contains_internal_identifier(answer),
                "no_unverified_outcome_promise": not FinnResponsesAnswerVerifier._promises_unverified_trading_outcome(answer)
                and not re.search(
                    r"\b(?:verlies voorkomen|verliezen vermijden|voorkom(?:en)? dat je .*verlies|"
                    r"prevent losses|avoid losses|verluste vermeiden|verluste verhindern|"
                    r"verhoog(?:t|de|en)? (?:de )?kans|increases? the chance)\b",
                    answer, re.IGNORECASE,
                ),
                "saved_setup_read": turn_index != 2 or any(name.startswith("get_") for name in tool_names if name),
            }
            turns.append({
                "message": message,
                "run_id": observed["run_id"],
                "status": observed["status"],
                "operation_id": observed["final_operation_id"],
                "answer": answer,
                "tool_names": tool_names,
                "conversation_reference": observed["conversation_reference"],
                "dispatch_count": observed["dispatch_count"],
                "attempt_count": observed["attempt_count"],
                "polling_sse_parity": observed["polling_sse_contract_projection"],
                "elapsed_ms": observed["elapsed_ms"],
                "proposal_created": persisted["proposal"] is not None,
                "checks": checks,
                "pass": all(checks.values()),
            })
            artifact["conversations"] = [
                *[item for item in artifact["conversations"] if item["locale"] != locale],
                {"locale": locale, "setup_name": setup_name, "turns": turns},
            ]
            output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
        if args.include_proposal:
            strategy_name = f"Coach {args.variant} {locale.upper()} Strategy"
            action_message = STRATEGY_REQUESTS[locale].format(setup=setup_name, strategy=strategy_name)
            action = run_gate(
                base_url=args.base_url, bearer_token=token, message=action_message,
                conversation_id=conversation_id, timeout_seconds=75,
            )
            action_record = _runtime_record(action["run_id"])
            proposal = action_record["proposal"]
            lifecycle = None
            if proposal is not None:
                other = _create_local_user()
                other_token = create_access_token({"sub": str(other["id"]), "role": "user"})
                lifecycle = _proposal_lifecycle(args.base_url, token, other_token, proposal)
            action_checks = {
                "create_strategy_selected": action["final_operation_id"] == "create_strategy",
                "proposal_created": proposal is not None,
                "one_dispatch_attempt": action["dispatch_count"] == 1 and action["attempt_count"] <= 1,
                "polling_sse_parity": bool(action["polling_sse_contract_projection"]),
                "cross_user_rejected": bool(lifecycle and lifecycle["cross_user_rejected"]),
                "confirmed": bool(lifecycle and lifecycle["confirmed"]),
                "executed": bool(lifecycle and lifecycle["execution_result"] == "succeeded"),
                "idempotent_replay": bool(lifecycle and lifecycle["idempotency_result"] == "already_executed"),
            }
            artifact["action_followups"].append({
                "locale": locale, "message": action_message,
                "run_id": action["run_id"], "status": action["status"],
                "operation_id": action["final_operation_id"],
                "runtime_contract_id": action_record["runtime_contract_id"],
                "proposal_id": str(proposal["id"]) if proposal else None,
                "lifecycle": lifecycle, "checks": action_checks,
                "pass": all(action_checks.values()),
            })
            output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    artifact["complete"] = all(
        len(conversation["turns"]) == len(prompts_by_locale[conversation["locale"]])
        and all(turn["pass"] for turn in conversation["turns"])
        for conversation in artifact["conversations"]
    ) and len(artifact["conversations"]) == len(selected_conversations)
    if args.include_proposal:
        artifact["complete"] = artifact["complete"] and len(artifact["action_followups"]) == len(selected_conversations) and all(
            action["pass"] for action in artifact["action_followups"]
        )
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    if not artifact["complete"]:
        raise SystemExit("coach_gate_failed; inspect the local artifact")


if __name__ == "__main__":
    main()
