#!/usr/bin/env python3
"""Local, public-API Responses scenarios with a synthetic owner fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import text

from backend.scripts.run_finn_v2_full_action_matrix import (
    _create_local_user,
    _proposal_lifecycle,
    _runtime_record,
    _seed_fixtures,
)
from backend.scripts.run_finn_v2_persisted_runtime_gate import _request_json, run_gate
from backend.infrastructure.database import sync_engine
from backend.domain.macro_indicator_catalog import get_active_macro_indicator_definitions
from backend.services.finn_v2_responses_answer_verifier import FinnResponsesAnswerVerifier
from backend.utils.auth_utils import create_access_token


READ_SCENARIOS = (
    ("general_education", "Wat betekent RSI in algemene zin?"),
    ("capabilities", "Gebaseerd op mijn profiel, waar kan je mij mee helpen?"),
    ("plan", "Wat is een logisch tradingplan voor mijn doel en risicostijl?"),
    ("plan_risks", "Mijn aanpak: waar liggen de grootste resterende risico's?"),
    ("plan_coherence", "Geef een onderbouwd oordeel over de samenhang van mijn hele BTC-handelsplan."),
    ("macro", "Welk macro-indicator mis ik nog en waarom?"),
    ("dca_fit", "Past een wekelijkse BTC-DCA bij mijn plan?"),
    ("indicators", "Wat zegt RSI en MA200 nu samen?"),
    ("missing_evidence", "Wat moet ik eerst invullen voordat dit een verantwoord plan is?"),
    ("cross_asset", "Wat zeggen de actuele AAPL- en MSFT-koersen over mijn plan? Gebruik geen BTC-koers als vervanging."),
    ("why_followup", "Waarom?"),
    ("plan_followup", "Wat verandert dit aan mijn plan?"),
    ("new_setup_topic_after_missing_market_data", "Please answer in English: what can you safely say about my BTC DCA setup?"),
    ("english", "Please answer in English: explain what my plan can safely conclude from the available evidence."),
    ("german", "Bitte antworte auf Deutsch: Erkläre, welche Daten für meinen Plan noch fehlen."),
)

TYPED_LIMITATION_CASES = {
    "plan": {"setup_ambiguous"},
    "plan_risks": {"setup_ambiguous"},
    "missing_evidence": {"setup_ambiguous"},
    "plan_followup": {"setup_ambiguous", "source_unavailable", "scope_unavailable"},
    "plan_coherence": {"setup_ambiguous", "scope_unavailable"},
    "dca_fit": {"setup_ambiguous"},
    "indicators": {"source_unavailable", "scope_unavailable"},
    "cross_asset": {"source_unavailable", "scope_unavailable"},
    "why_followup": {"source_unavailable", "scope_unavailable"},
    "new_setup_topic_after_missing_market_data": {"setup_ambiguous"},
    "english": {"setup_ambiguous", "source_unavailable"},
    "german": {"setup_ambiguous", "source_unavailable"},
}


def _owner_setup_count(user_id: int, name: str) -> int:
    with sync_engine.connect() as connection:
        return int(connection.execute(
            text("SELECT count(*) FROM setups WHERE user_id = :user_id AND name = :name"),
            {"user_id": user_id, "name": name},
        ).scalar() or 0)


def run_scenarios(*, base_url: str, output: Path, only_case: str | None = None,
                  conversation_only: bool = False) -> dict:
    if urlparse(base_url).hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("responses_build_scenarios_require_loopback")
    owner = _create_local_user()
    outsider = _create_local_user()
    _seed_fixtures(int(owner["id"]))
    token = create_access_token({"sub": str(owner["id"]), "role": "user"})
    other_token = create_access_token({"sub": str(outsider["id"]), "role": "user"})
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    artifact: dict = {
        "version": 1, "local_synthetic_only": True,
        "targeted_only": only_case, "cases": [], "draft": {},
    }
    conversation_id = None

    def checkpoint() -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        temporary.replace(output)

    for case_id, question in READ_SCENARIOS:
        if conversation_only:
            break
        if only_case and case_id != only_case:
            continue
        if case_id not in {"why_followup", "plan_followup", "new_setup_topic_after_missing_market_data"}:
            conversation_id = None
        observed = run_gate(
            base_url=base_url, bearer_token=token, message=question,
            timeout_seconds=75, conversation_id=conversation_id,
        )
        conversation_id = observed["conversation_id"]
        terminal, http_status = _request_json(
            url=f"{base_url.rstrip('/')}/api/assistant/v2/runs/{observed['run_id']}",
            method="GET", headers=headers, body=None, timeout=10,
        )
        record = _runtime_record(observed["run_id"])
        exchange = dict(record["runtime_state"].get("responses_exchange") or {})
        trace = list(exchange.get("tool_trace") or [])
        selected_tools = [item.get("name") for item in trace]
        response = dict(terminal.get("response") or {})
        error_code = record["terminal_projection"].get("error_code")
        missing_profile_clarification = (
            case_id in {"capabilities", "plan"}
            and error_code == "user_detail_required"
            and any(
                result.get("scope") == "read_profile"
                and result.get("status") == "completed"
                and result.get("data", {}).get("has_profile") is False
                for call in trace
                for result in (call.get("result", {}).get("results") or [])
            )
        )
        typed_limitation = (
            observed["status"] in {"unavailable", "clarification_required"}
            and (
                missing_profile_clarification
                or error_code in TYPED_LIMITATION_CASES.get(case_id, set())
            )
        )
        passed = (
            http_status == 200
            and (observed["status"] == "completed" or typed_limitation)
            and observed["dispatch_count"] == 1
            and observed["attempt_count"] == 1
            and bool(str(response.get("content") or "").strip())
            and (bool(exchange.get("response_id")) or typed_limitation)
            and not record["proposal"]
        )
        if case_id == "general_education":
            passed = passed and all(item.get("name") == "answer_directly" for item in trace)
        if case_id in {"capabilities", "plan", "plan_risks", "plan_coherence", "dca_fit"}:
            passed = passed and any(item.get("name") != "answer_directly" for item in trace)
        if case_id == "cross_asset":
            passed = passed and all(
                str(item.get("arguments", {}).get("asset") or "").upper() != "BTC"
                for item in trace if item.get("name") == "get_market_snapshot"
            )
        if case_id == "indicators":
            answer_lower = str(response.get("content") or "").casefold()
            passed = passed and any(item.get("name") == "get_current_technical_snapshot" for item in trace)
            passed = passed and not any(phrase in answer_lower for phrase in (
                "tijdelijke storing", "temporary outage", "vorübergehende störung",
                "onder 30 overbought", "below 30 overbought",
            ))
        if case_id == "macro" and observed["status"] == "completed":
            answer_lower = str(response.get("content") or "").casefold()
            passed = passed and FinnResponsesAnswerVerifier._assistant_does_not_claim_user_mutation(
                answer_lower,
            )
            named_options = {
                str(item["name"])
                for item in get_active_macro_indicator_definitions()
                if any(
                    str(label).casefold() in answer_lower
                    for label in (item["name"], item["display_name"])
                )
            }
            passed = passed and len(named_options) == 1
            passed = passed and "ik kan nog niet beoordelen of dit bij je risicostijl past" not in answer_lower
        if case_id in {"why_followup", "plan_followup"}:
            passed = passed and bool(observed.get("conversation_reference"))
        if case_id == "why_followup":
            lower_answer = str(response.get("content") or "").casefold()
            passed = passed and not any(
                phrase in lower_answer
                for phrase in (
                    "technische storing", "technische problemen", "probleem met de gegevensbron",
                    "vertragingen in gegevensverwerking", "providerstoring", "technical outage",
                    "provider failure", "datenquellenproblem",
                )
            )
        if case_id == "new_setup_topic_after_missing_market_data":
            lower_answer = str(response.get("content") or "").casefold()
            passed = (
                passed
                and bool(observed.get("conversation_reference"))
                and "get_active_plan_and_strategy" in selected_tools
                and "cause of the missing data" not in lower_answer
                and "can't establish why" not in lower_answer
            )
        if case_id in {"new_setup_topic_after_missing_market_data", "english", "german"}:
            expected_locale = "de" if case_id == "german" else "en"
            passed = passed and FinnResponsesAnswerVerifier._language_matches(
                str(response.get("content") or ""), expected_locale,
            )
            passed = passed and FinnResponsesAnswerVerifier._german_register_matches(
                str(response.get("content") or ""), expected_locale,
            )
        artifact["cases"].append({
            "case_id": case_id, "question": question, "run_id": observed["run_id"],
            "status": observed["status"], "tools": selected_tools,
            "error_code": error_code, "outcome": "typed_limitation" if typed_limitation else observed["status"],
            "tool_results": [{"name": item.get("name"), "status": item.get("status")} for item in trace],
            "answer": response.get("content"), "conversation_reference": observed.get("conversation_reference"),
            "elapsed_ms": observed["elapsed_ms"], "polling_sse_parity": observed["polling_sse_contract_projection"],
            "dispatch_count": observed["dispatch_count"], "attempt_count": observed["attempt_count"],
            "pass": passed,
        })
        checkpoint()
    if only_case:
        artifact["passed"] = sum(case["pass"] for case in artifact["cases"])
        artifact["total"] = len(artifact["cases"])
        checkpoint()
        return artifact

    conversation_owner = _create_local_user()
    _seed_fixtures(int(conversation_owner["id"]))
    with sync_engine.begin() as connection:
        connection.execute(
            text("UPDATE users SET ai_preferences = CAST(:preferences AS jsonb) WHERE id = :user_id"),
            {
                "user_id": int(conversation_owner["id"]),
                "preferences": json.dumps({
                    "trader_types": ["swing_trader"],
                    "primary_timeframes": ["4h"],
                    "asset_focus": ["bitcoin"],
                    "investment_goals_list": ["wealth_building"],
                    "experience_levels": ["intermediate"],
                    "risk_profiles": ["balanced"],
                    "selected_asset": "BTC",
                }),
            },
        )
    conversation_token = create_access_token({"sub": str(conversation_owner["id"]), "role": "user"})
    conversation_headers = {"Authorization": f"Bearer {conversation_token}", "Content-Type": "application/json"}
    conversation_turns = []
    conversation_id = None
    for question in (
        "Wat is een logisch tradingplan voor mijn doel en risicostijl?",
        "Matrix Strategy Update Parent",
        "Waarom?",
        "Wat betekent RSI in algemene zin?",
    ):
        observed = run_gate(
            base_url=base_url, bearer_token=conversation_token, message=question,
            timeout_seconds=75, conversation_id=conversation_id,
        )
        conversation_id = observed["conversation_id"]
        record = _runtime_record(observed["run_id"])
        terminal, http_status = _request_json(
            url=f"{base_url.rstrip('/')}/api/assistant/v2/runs/{observed['run_id']}",
            method="GET", headers=conversation_headers, body=None, timeout=10,
        )
        conversation_turns.append({
            "question": question, "run_id": observed["run_id"],
            "http_status": http_status, "status": observed["status"],
            "answer": str((terminal.get("response") or {}).get("content") or ""),
            "tools": [
                item.get("name") for item in
                (record["runtime_state"].get("responses_exchange") or {}).get("tool_trace", [])
            ],
            "clarification_persisted": bool(record["runtime_state"].get("responses_clarification")),
            "conversation_reference": bool(observed.get("conversation_reference")),
            "dispatch_count": observed["dispatch_count"],
            "attempt_count": observed["attempt_count"],
            "polling_sse_parity": observed["polling_sse_contract_projection"],
            "elapsed_ms": observed["elapsed_ms"],
        })
        artifact["conversation"] = {"turns": conversation_turns, "pass": False}
        checkpoint()
    why_answer = conversation_turns[2]["answer"].casefold()
    why_explains = (
        any(marker in why_answer for marker in (
            "omdat", "want", "daarom", "de reden", "heeft te maken met", "om verder",
            "zonder een actuele", "zonder actuele", "zonder deze gegevens",
            "zonder deze informatie", "zonder die informatie",
            "om te zien",
        ))
        and any(marker in why_answer for marker in (
            "matrix strategy update parent", "matrix update strategie",
            "entry", "stop-loss", "risico", "doel", "setup",
        ))
        and "wat wil je dat er verder in je plan wordt opgenomen?" not in why_answer
    )
    unsupported_fit_claim = any(
        phrase in turn["answer"].casefold()
        for turn in conversation_turns[1:3]
        for phrase in ("sluit goed aan bij je risicoprofiel", "is afgestemd op je risicoprofiel",
                       "is well aligned with your risk", "fits your risk profile")
    )
    lost_profile_context = any(
        phrase in turn["answer"].casefold()
        for turn in conversation_turns[1:3]
        for phrase in ("geen specifieke informatie over je risicoprofiel",
                       "risicoprofiel ontbreekt", "risk profile is missing",
                       "geen toegang heb tot je risicoprofiel",
                       "je risicoprofiel te kennen",
                       "risicoprofiel en beleggingsdoelen verder te verduidelijken")
    )
    artifact["conversation"]["pass"] = bool(
        [turn["status"] for turn in conversation_turns]
        == ["clarification_required", "completed", "completed", "completed"]
        and conversation_turns[0]["clarification_persisted"]
        and all(turn["http_status"] == 200 and turn["dispatch_count"] == 1
                and turn["attempt_count"] == 1 and turn["polling_sse_parity"]
                for turn in conversation_turns)
        and all(turn["conversation_reference"] for turn in conversation_turns[1:])
        and "Matrix Strategy Update Parent" in conversation_turns[1]["answer"]
        and "evaluate_plan" in conversation_turns[1]["tools"]
        and not any(phrase in conversation_turns[1]["answer"].casefold() for phrase in (
            "je overweegt een update", "je wilt de strategie wijzigen",
            "je hebt de setup opgeslagen",
        ))
        and why_explains
        and conversation_turns[2]["tools"] == ["answer_directly"]
        and not unsupported_fit_claim
        and not lost_profile_context
        and "RSI" in conversation_turns[3]["answer"]
        and conversation_turns[3]["tools"] == ["answer_directly"]
    )
    checkpoint()

    if conversation_only:
        artifact["passed"] = int(artifact["conversation"]["pass"])
        artifact["total"] = 1
        checkpoint()
        return artifact

    name = f"Responses Build DCA {uuid.uuid4().hex[:8]}"
    first = run_gate(
        base_url=base_url, bearer_token=token,
        message=f"Maak een BTC DCA setup op 4H met de naam {name}, 150 euro per week op maandag.",
        timeout_seconds=75,
    )
    first_record = _runtime_record(first["run_id"])
    revised = run_gate(
        base_url=base_url, bearer_token=token,
        conversation_id=first["conversation_id"],
        message="Maak er 100 euro per week van.", timeout_seconds=75,
    )
    revised_record = _runtime_record(revised["run_id"])
    proposal = revised_record["proposal"]
    before = _owner_setup_count(int(owner["id"]), name)
    lifecycle = _proposal_lifecycle(base_url, token, other_token, proposal) if proposal else {}
    after = _owner_setup_count(int(owner["id"]), name)
    artifact["draft"] = {
        "first_run_id": first["run_id"], "revision_run_id": revised["run_id"],
        "same_conversation": first["conversation_id"] == revised["conversation_id"],
        "first_proposal_id": (first_record["proposal"] or {}).get("id"),
        "revised_proposal_id": (proposal or {}).get("id"),
        "revised_supplied_inputs": revised_record["terminal_projection"].get("supplied_inputs"),
        "before_rows": before, "after_rows": after, "lifecycle": lifecycle,
        "pass": bool(
            first_record["proposal"] and proposal
            and first_record["proposal"]["id"] != proposal["id"]
            and revised_record["terminal_projection"].get("supplied_inputs", {}).get("timeframe") == "4H"
            and revised_record["terminal_projection"].get("supplied_inputs", {}).get("min_investment") == 100
            and revised_record["terminal_projection"].get("supplied_inputs", {}).get("name") == name
            and before == 0 and after == 1
            and lifecycle.get("confirmed")
            and lifecycle.get("execution_result") == "succeeded"
            and lifecycle.get("idempotency_result") == "already_executed"
            and lifecycle.get("cross_user_rejected")
        ),
    }
    readback = run_gate(
        base_url=base_url, bearer_token=token,
        conversation_id=first["conversation_id"],
        message="Wat zijn naam, frequentie en bedrag van de setup die je net hebt opgeslagen?",
        timeout_seconds=75,
    )
    readback_record = _runtime_record(readback["run_id"])
    readback_terminal, readback_status = _request_json(
        url=f"{base_url.rstrip('/')}/api/assistant/v2/runs/{readback['run_id']}",
        method="GET", headers=headers, body=None, timeout=10,
    )
    readback_answer = str((readback_terminal.get("response") or {}).get("content") or "")
    readback_exchange = dict(readback_record["runtime_state"].get("responses_exchange") or {})
    artifact["readback"] = {
        "run_id": readback["run_id"],
        "status": readback["status"],
        "tools": [item.get("name") for item in readback_exchange.get("tool_trace", [])],
        "answer": readback_answer,
        "pass": bool(readback_status == 200 and readback["status"] == "completed"
                     and readback["dispatch_count"] == 1 and readback["attempt_count"] == 1
                     and name in readback_answer and "100" in readback_answer
                     and ("week" in readback_answer.casefold() or "wekel" in readback_answer.casefold())),
    }
    ambiguous = run_gate(
        base_url=base_url, bearer_token=token,
        conversation_id=first["conversation_id"],
        message="Bitte antworte auf Deutsch: Was kann ich derzeit sicher über meinen BTC-Plan sagen?",
        timeout_seconds=75,
    )
    ambiguous_record = _runtime_record(ambiguous["run_id"])
    ambiguous_terminal, ambiguous_status = _request_json(
        url=f"{base_url.rstrip('/')}/api/assistant/v2/runs/{ambiguous['run_id']}",
        method="GET", headers=headers, body=None, timeout=10,
    )
    ambiguous_answer = str((ambiguous_terminal.get("response") or {}).get("content") or "")
    artifact["ambiguous_plan_read"] = {
        "run_id": ambiguous["run_id"], "status": ambiguous["status"],
        "reason": ambiguous_record["terminal_projection"].get("error_code"),
        "answer": ambiguous_answer,
        "pass": bool(
            ambiguous_status == 200
            and ambiguous["dispatch_count"] == 1 and ambiguous["attempt_count"] == 1
            and "150" not in ambiguous_answer
            and (
                (ambiguous["status"] in {"unavailable", "clarification_required"}
                 and ambiguous_record["terminal_projection"].get("error_code") in {
                     "setup_ambiguous", "responses_evidence_not_verified",
                 })
                or (ambiguous["status"] == "completed" and "100" in ambiguous_answer)
            )
        ),
    }
    newer_name = f"Responses Latest DCA {uuid.uuid4().hex[:8]}"
    newer = run_gate(
        base_url=base_url, bearer_token=token,
        conversation_id=first["conversation_id"],
        message=f"Maak daarnaast een nieuwe BTC 4H DCA-setup met de naam {newer_name}, 200 euro per week op dinsdag.",
        timeout_seconds=75,
    )
    newer_proposal = _runtime_record(newer["run_id"])["proposal"]
    newer_lifecycle = _proposal_lifecycle(base_url, token, other_token, newer_proposal) if newer_proposal else {}
    if newer_lifecycle.get("execution_result") == "succeeded":
        with sync_engine.begin() as connection:
            connection.execute(text("""
                UPDATE finn_v2_runtime_contracts
                SET updated_at = NOW() + INTERVAL '1 hour'
                WHERE run_id = :older_run_id AND user_id = :user_id
            """), {"older_run_id": revised["run_id"], "user_id": int(owner["id"])})
    latest = run_gate(
        base_url=base_url, bearer_token=token,
        conversation_id=first["conversation_id"],
        message="Wat zijn naam en bedrag van de setup die je net hebt opgeslagen?",
        timeout_seconds=75,
    )
    latest_terminal, latest_status = _request_json(
        url=f"{base_url.rstrip('/')}/api/assistant/v2/runs/{latest['run_id']}",
        method="GET", headers=headers, body=None, timeout=10,
    )
    latest_answer = str((latest_terminal.get("response") or {}).get("content") or "")
    artifact["latest_of_two_executions"] = {
        "newer_run_id": newer["run_id"], "read_run_id": latest["run_id"],
        "execution_result": newer_lifecycle.get("execution_result"),
        "answer": latest_answer,
        "pass": bool(newer_proposal and newer_lifecycle.get("execution_result") == "succeeded"
                     and newer_lifecycle.get("idempotency_result") == "already_executed"
                     and latest_status == 200 and latest["status"] == "completed"
                     and latest["dispatch_count"] == 1 and latest["attempt_count"] == 1
                     and newer_name in latest_answer and "200" in latest_answer
                     and name not in latest_answer and "150" not in latest_answer),
    }
    artifact["passed"] = sum(case["pass"] for case in artifact["cases"]) + int(artifact["draft"]["pass"])
    artifact["passed"] += int(artifact["readback"]["pass"])
    artifact["passed"] += int(artifact["ambiguous_plan_read"]["pass"])
    artifact["passed"] += int(artifact["latest_of_two_executions"]["pass"])
    artifact["passed"] += int(artifact["conversation"]["pass"])
    artifact["total"] = len(artifact["cases"]) + 5
    checkpoint()
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--only-case", choices=[case_id for case_id, _ in READ_SCENARIOS])
    parser.add_argument("--conversation-only", action="store_true")
    args = parser.parse_args()
    artifact = run_scenarios(
        base_url=args.base_url, output=args.output,
        only_case=args.only_case, conversation_only=args.conversation_only,
    )
    print(json.dumps({
        "passed": artifact["passed"], "total": artifact["total"],
        "output": str(args.output), "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }, sort_keys=True))
    if artifact["passed"] != artifact["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
