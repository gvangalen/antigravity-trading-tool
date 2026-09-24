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
    ("english", "Explain what my plan can safely conclude from the available evidence."),
    ("german", "Erkläre, welche Daten für meinen Plan noch fehlen."),
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


def run_scenarios(*, base_url: str, output: Path) -> dict:
    if urlparse(base_url).hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("responses_build_scenarios_require_loopback")
    owner = _create_local_user()
    outsider = _create_local_user()
    _seed_fixtures(int(owner["id"]))
    token = create_access_token({"sub": str(owner["id"]), "role": "user"})
    other_token = create_access_token({"sub": str(outsider["id"]), "role": "user"})
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    artifact: dict = {"version": 1, "local_synthetic_only": True, "cases": [], "draft": {}}
    conversation_id = None

    def checkpoint() -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        temporary.replace(output)

    for case_id, question in READ_SCENARIOS:
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
        typed_limitation = (
            case_id in TYPED_LIMITATION_CASES
            and observed["status"] == "unavailable"
            and error_code in TYPED_LIMITATION_CASES[case_id]
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
                     and ("week" in readback_answer.casefold() or "weekly" in readback_answer.casefold())),
    }
    artifact["passed"] = sum(case["pass"] for case in artifact["cases"]) + int(artifact["draft"]["pass"])
    artifact["passed"] += int(artifact["readback"]["pass"])
    artifact["total"] = len(artifact["cases"]) + 2
    checkpoint()
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    artifact = run_scenarios(base_url=args.base_url, output=args.output)
    print(json.dumps({
        "passed": artifact["passed"], "total": artifact["total"],
        "output": str(args.output), "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }, sort_keys=True))
    if artifact["passed"] != artifact["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
