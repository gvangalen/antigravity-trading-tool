#!/usr/bin/env python3
"""Public-route regression for a personal plan discussion across follow-up turns."""

from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import json
from pathlib import Path

from sqlalchemy import text

from backend.infrastructure.database import sync_engine
from backend.services.finn_v2_responses_answer_verifier import FinnResponsesAnswerVerifier
from backend.scripts.run_finn_v2_full_action_matrix import _create_local_user, _insert_setup, _runtime_record
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.utils.auth_utils import create_access_token


QUESTIONS = (
    "Mijn huidige BTC-plan is dagelijkse DCA, maar ik denk aan 100 euro per week. Past dat bij mijn voorzichtige risicostijl?",
    "Waarom?",
    "Welke keuze moet ik nu eerst maken?",
    "Beoordeel nu mijn volledige BTC-plan en mijn voorzichtige risicostijl met de beschikbare gegevens.",
    "Is mijn 4H DCA-setup langetermijnopbouw of een swingtrade?",
    "Voor de lange termijn, ongeveer vijf jaar.",
    "Mijn BTC-plan zegt te wachten op bevestiging voor een entry. Ik ben bang de beweging te missen. Moet ik die wachtregel nu negeren? Denk als coach met me mee, zonder te doen alsof je de actuele koers kent.",
)
TRANSLATED_QUESTIONS = {
    "nl": QUESTIONS,
    "en": (
        "My current BTC plan is daily DCA, but I am considering 100 euros per week. Does that suit my cautious risk style?",
        "Why?",
        "What decision should I make first?",
        "Assess my entire BTC plan and cautious risk style using the available evidence.",
        "Is my 4H DCA setup long-term accumulation or a swing trade?",
        "For the long term, around five years.",
        "My BTC plan says to wait for entry confirmation. I fear missing the move. Should I ignore that rule now? Coach me without pretending you know the current price.",
    ),
    "de": (
        "Mein aktueller BTC-Plan ist tägliches DCA, aber ich erwäge 100 Euro pro Woche. Passt das zu meinem vorsichtigen Risikostil?",
        "Warum?",
        "Welche Entscheidung sollte ich zuerst treffen?",
        "Bewerte meinen gesamten BTC-Plan und meinen vorsichtigen Risikostil anhand der verfügbaren Daten.",
        "Ist mein 4H-DCA-Setup langfristiger Vermögensaufbau oder ein Swingtrade?",
        "Langfristig, ungefähr fünf Jahre.",
        "Mein BTC-Plan verlangt eine Bestätigung vor dem Einstieg. Ich habe Angst, die Bewegung zu verpassen. Soll ich diese Regel jetzt ignorieren? Antworte als Coach, ohne den aktuellen Kurs zu behaupten.",
    ),
}
PROPOSAL_MARKERS = {
    "nl": ("je voorstel", "je overweegt", "je denkt aan", "je wilt", "voorgestelde wijziging",
           "kan nog niet beoordelen of", "kan niet beoordelen of"),
    "en": ("your proposal", "you are considering", "you consider", "proposed change"),
    "de": ("dein vorschlag", "du erwägst", "vorgeschlagene änderung", "du überlegst", "du ziehst in betracht"),
}
WEEK_MARKERS = {
    "nl": ("per week", "wekelijks"),
    "en": ("per week", "weekly"),
    "de": ("pro woche", "wöchentlich"),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", required=True)
    parser.add_argument("--evaluation-only", action="store_true")
    parser.add_argument("--horizon-only", action="store_true")
    parser.add_argument("--conditional-only", action="store_true")
    parser.add_argument("--locale", choices=tuple(TRANSLATED_QUESTIONS), default="nl")
    args = parser.parse_args()
    if not args.base_url.startswith(("http://localhost:", "http://127.0.0.1:")):
        raise SystemExit("This regression is local-only")
    user = _create_local_user()
    with sync_engine.begin() as connection:
        connection.execute(text("UPDATE users SET ai_preferences = CAST(:preferences AS jsonb) WHERE id = :user_id"), {
            "user_id": user["id"],
            "preferences": json.dumps({
                "selected_asset": "BTC", "trader_type": "dca_investor",
                "primary_timeframes": ["4h"], "asset_focus": ["bitcoin"],
                "investment_goals": ["wealth_building"], "experience_level": "beginner",
                "risk_profile": "conservative", "locale": args.locale,
            }),
        })
        _insert_setup(connection, user["id"], "Coach DCA Basis", setup_type="dca")
    token = create_access_token({"sub": str(user["id"]), "role": "user"})
    artifact = {"version": 1, "synthetic_local_only": True, "locale": args.locale, "cases": []}
    conversation_id = None
    questions = TRANSLATED_QUESTIONS[args.locale]
    selected_questions = (
        [(6, questions[6])] if args.conditional_only else
        [(3, questions[3])] if args.evaluation_only else
        list(enumerate(questions))[3:] if args.horizon_only else
        list(enumerate(questions))
    )
    previous_answer = ""
    for index, question in selected_questions:
        if index == 3:
            conversation_id = None
        if index == 6:
            conversation_id = None
        observed = run_gate(
            base_url=args.base_url, bearer_token=token, message=question,
            conversation_id=conversation_id, timeout_seconds=75,
        )
        conversation_id = observed["conversation_id"]
        record = _runtime_record(observed["run_id"])
        answer = str((record["runtime_state"].get("terminal_response") or {}).get("content") or "")
        trace = (record["runtime_state"].get("responses_exchange") or {}).get("tool_trace") or []
        checks = {
            "terminal": observed["status"] in ({"completed", "clarification_required"} if index in {2, 4} else {"completed"}),
            "one_dispatch_attempt": observed["dispatch_count"] == observed["attempt_count"] == 1,
            "polling_sse_parity": bool(observed["polling_sse_contract_projection"]),
            "no_proposal": not record["proposal"],
            "answer_present": bool(answer.strip()),
            "no_internal_choice_wrapper": all(label not in answer for label in (
                "Original user request:", "User's chosen answer:",
            )),
            "language": FinnResponsesAnswerVerifier._language_matches(answer, args.locale),
            "german_register": FinnResponsesAnswerVerifier._german_register_matches(answer, args.locale),
            "no_unsupported_positive_fit": not FinnResponsesAnswerVerifier._unevaluated_positive_fit_claim(answer),
            "conversation_reference": index in {0, 3, 6} or bool(observed.get("conversation_reference")),
            "saved_entity_type": FinnResponsesAnswerVerifier._saved_entity_type_supported(
                answer, ({"scope": "read_active_setup", "status": "completed"},
                         {"scope": "read_linked_strategy", "status": "unavailable"}),
            ),
            "saved_profile_not_denied": FinnResponsesAnswerVerifier._profile_presence_claim_supported(
                answer, ({"scope": "read_profile", "status": "completed",
                          "data": {"trader_profile": {"risk_profiles": ["conservative"]}}},),
            ),
            "unavailable_source_not_delegated": not (
                FinnResponsesAnswerVerifier._asks_user_to_supply_unavailable_source(answer)
            ),
            "hypothetical_proposal_preserved": index != 0 or (
                "100" in answer
                and any(marker in answer.casefold() for marker in WEEK_MARKERS[args.locale])
                and any(phrase in answer.casefold() for phrase in PROPOSAL_MARKERS[args.locale])
            ),
            "fresh_evaluation_tool": index != 3 or any(
                item.get("name") == "evaluate_plan"
                and (item.get("result") or {}).get("evaluation_operation_id") == "evaluate_plan"
                and bool((item.get("result") or {}).get("results"))
                for item in trace
            ),
            "initial_evaluation_tool": index != 0 or any(
                item.get("name") == "evaluate_plan"
                and (item.get("result") or {}).get("evaluation_operation_id") == "evaluate_plan"
                for item in trace
            ),
            "why_explains": args.locale != "nl" or index != 1 or (
                SequenceMatcher(None, previous_answer.casefold(), answer.casefold()).ratio() < 0.8
                and any(token in answer.casefold() for token in (
                    "omdat", "doordat", "waardoor", "reden", "zonder", "because", "weil",
                ))
                and any(token in answer.casefold() for token in (
                    "bewijs", "beoordel", "geschik", "markt", "evidence", "assessment",
                ))
            ),
            "next_decision": args.locale != "nl" or index != 2 or (
                observed["status"] == "completed"
                and any(item.get("name") == "answer_directly" for item in trace)
                and previous_answer.casefold().strip() != answer.casefold().strip()
            ),
            "horizon_not_inferred": index != 4 or (
                FinnResponsesAnswerVerifier._saved_horizon_claim_supported(
                    answer, ({"scope": "read_active_setup", "status": "completed",
                              "data": {"name": "Coach DCA Basis", "timeframe": "4H"}},),
                ) and (
                    "?" in answer
                    or any(phrase in answer.casefold() for phrase in {
                        "nl": ("geef aan welke termijn", "geef aan welke investeringshorizon", "verduidelijk je horizon"),
                        "en": ("please clarify your intended", "tell me your intended", "clarify your investment horizon"),
                        "de": ("bitte kläre", "sag mir, welchen zeitraum", "bitte teile mir mit"),
                    }[args.locale])
                )
                and not any(marker in answer.casefold() for marker in (
                    "ik begrijp je antwoord", "i understand your answer",
                    "ich verstehe deine antwort",
                ))
            ),
            "horizon_followup_used": index != 5 or (
                any(marker in answer.casefold() for marker in {
                    "nl": ("vijf jaar", "5 jaar"),
                    "en": ("five years", "5 years"),
                    "de": ("fünf jahre", "5 jahre"),
                }[args.locale])
                and "dca" in answer.casefold()
                and not FinnResponsesAnswerVerifier._unevaluated_positive_fit_claim(answer)
            ),
            "conditional_process_coaching": index != 6 or (
                observed["status"] == "completed"
                and any(word in answer.casefold() for word in {
                    "nl": ("wacht", "bevestig", "voorwaarde"),
                    "en": ("wait", "confirm", "condition"),
                    "de": ("wart", "bestätig", "bedingung"),
                }[args.locale])
                and any(word in answer.casefold() for word in {
                    "nl": ("koers", "markt", "actueel", "controleer"),
                    "en": ("price", "market", "current", "check"),
                    "de": ("kurs", "markt", "aktuell", "prüf"),
                }[args.locale])
                and not any(phrase in answer.casefold() for phrase in (
                    "ik kan dit nog niet onderbouwen met betrouwbare gegevens",
                    "ik kan nog niet beoordelen of dit bij je risicostijl past",
                ))
                and any(phrase in answer.casefold() for phrase in {
                    "nl": ("wacht tot", "controleer of", "controleer eerst of", "moet controleren of", "check of", "wachtregel niet negeren", "negeer de wachtregel niet"),
                    "en": ("wait until", "check whether", "verify that", "confirm whether", "not ignore the wait rule"),
                    "de": ("warte bis", "prüfe ob", "prüf ob", "sicherstellen, dass", "warteregel nicht ignorieren"),
                }[args.locale])
                and not any(detail in answer.casefold() and detail not in question.casefold()
                            for detail in {"bullish breakout", "prijsactie", "price action", "bullishe ausbruch"})
                and not answer.casefold().startswith({
                    "nl": "je hebt een dca-setup", "en": "you have a dca setup",
                    "de": "du hast ein dca-setup",
                }[args.locale])
                and not any(phrase in answer.casefold() for phrase in {
                    "nl": ("je opgeslagen strategie", "gekoppelde strategie vereist"),
                    "en": ("your saved strategy", "linked strategy requires"),
                    "de": ("deine gespeicherte strategie", "verknüpfte strategie verlangt"),
                }[args.locale])
            ),
            "user_rule_not_claimed_as_saved": index != 6 or not any(
                phrase in answer.casefold() for phrase in {
                    "nl": ("setup verwacht een bevestiging", "opgeslagen plan vereist bevestiging"),
                    "en": ("saved setup requires confirmation", "saved plan requires confirmation"),
                    "de": ("gespeicherte setup verlangt bestätigung", "gespeicherte plan verlangt bestätigung"),
                }[args.locale]
            ),
        }
        passed = all(checks.values())
        artifact["cases"].append({
            "question": question, "run_id": observed["run_id"],
            "status": observed["status"], "answer": answer,
            "tools": [item.get("name") for item in trace],
            "tool_statuses": [
                {"name": item.get("name"), "status": item.get("status"),
                 "reason": (item.get("result") or {}).get("reason")}
                for item in trace
            ],
            "conversation_reference": bool(observed.get("conversation_reference")),
            "elapsed_ms": observed["elapsed_ms"], "pass": passed,
            "checks": checks,
        })
        previous_answer = answer
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(output)
    artifact["pass"] = all(case["pass"] for case in artifact["cases"])
    Path(args.output).write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    if not artifact["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
