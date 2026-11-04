"""Public-route typed-entry chat probe on a synthetic local account only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

from backend.scripts.run_finn_v2_full_action_matrix import _create_local_user, _proposal_lifecycle, _runtime_record
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.utils.auth_utils import create_access_token
from sqlalchemy import text
from backend.infrastructure.database import sync_engine


COMPLETE_REQUEST = (
    "Maak alleen een voorstelkaart, bevestig of sla niets op: nieuwe aparte "
    "BTC/EUR Paper trade-setup met naam QA BTC EUR SMA34 Concept 0411, "
    "analysetijdsframe 1D, totale benchmarkband 26–45, instapniveau €50.000, "
    "stop €45.000, doel €60.000, gebalanceerd risico en €10 per aankoop. "
    "Extra getypeerde instapregel: koop alleen bij opwaartse kruising van een "
    "afgesloten 1D BTC/EUR-slotkoers door SMA34 berekend uit afgesloten candles. "
    "Toon alle velden en vertel welke bevestiging nodig is."
)


def run(base_url: str) -> dict:
    if urlparse(base_url).hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("typed_entry_chat_probe_requires_loopback")
    user = _create_local_user()
    token = create_access_token({"sub": str(user["id"]), "role": "user"})
    observed = run_gate(
        base_url=base_url, bearer_token=token, message=COMPLETE_REQUEST,
        timeout_seconds=120, workspace_hints={"locale": "nl", "page": "/setup"},
    )
    record = _runtime_record(observed["run_id"])
    proposal = record["proposal"]
    complete = {
        "status": observed["status"],
        "operation": observed["final_operation_id"],
        "proposal": proposal is not None,
        "answer": str((record["runtime_state"].get("terminal_response") or {}).get("content") or ""),
    }
    if proposal is None or observed["final_operation_id"] != "create_setup":
        raise AssertionError(f"complete_sma_proposal_missing: {complete}")

    conversation_id = None
    guided = []
    for message in (
        "Maak een nieuw BTC/EUR Paper Trade-plan. Koop alleen wanneer de afgesloten "
        "dagkoers de SMA50 van onder naar boven kruist; toon eerst een voorstel.",
        "Noem het QA BTC EUR SMA50 Gesprek. Vaste uitvoering van €10, "
        "gebalanceerd risico, benchmarkscore 26–45.",
        "Kan deze SMA-kruising zonder vaste instapprijs draaien?",
        "Geen vaste instapkoers. De instapvoorwaarde is uitsluitend de SMA50-kruising. "
        "Als een vaste instapkoers verplicht is, leg uit waarom.",
        "Ik begrijp de beperking. Gebruik als extra vaste instap €50.000, "
        "stop €45.000 en doel €60.000. Toon nu het concept; sla niets op.",
    ):
        turn = run_gate(
            base_url=base_url, bearer_token=token, message=message,
            conversation_id=conversation_id, timeout_seconds=120,
            workspace_hints={"locale": "nl", "page": "/setup"},
        )
        conversation_id = turn["conversation_id"]
        state = _runtime_record(turn["run_id"])["runtime_state"]
        with sync_engine.connect() as conn:
            guided_state = conn.execute(text(
                "SELECT state_json->'guided_state' FROM finn_v2_runtime_contracts "
                "WHERE run_id=:run_id AND user_id=:user_id"
            ), {"run_id": turn["run_id"], "user_id": user["id"]}).scalar_one_or_none()
        guided.append({
            "status": turn["status"], "operation": turn["final_operation_id"],
            "answer": str((state.get("terminal_response") or {}).get("content") or ""),
            "missing_inputs": (turn.get("runtime_trace") or {}).get("missing_inputs"),
            "supplied_inputs": (turn.get("runtime_trace") or {}).get("supplied_inputs"),
            "guided_state": guided_state,
            "proposal": _runtime_record(turn["run_id"])["proposal"] is not None,
        })
    question = guided[2]
    if question["status"] != "completed" or question["proposal"] or (
        question["guided_state"] or {}
    ).get("status") != "collecting":
        raise AssertionError(f"guided_signal_capability_question_lost_draft: {guided}")
    explanation = guided[3]
    if explanation["status"] != "completed" or not all(
        term in explanation["answer"].casefold()
        for term in ("sma50", "instapkoers", "niet")
    ) or explanation["proposal"] or (explanation["guided_state"] or {}).get("status") != "collecting":
        raise AssertionError(f"guided_signal_contract_explanation_missing: {guided}")
    last = guided[-1]
    if last["status"] != "completed" or not last["proposal"]:
        raise AssertionError(f"guided_signal_proposal_missing: {guided}")
    with sync_engine.connect() as conn:
        payload = conn.execute(text(
            "SELECT payload_json FROM finn_v2_proposals WHERE id=:proposal_id"
        ), {"proposal_id": _runtime_record(turn["run_id"])["proposal"]["id"]}).scalar_one()
    fields = ((payload or {}).get("change") or {}).get("setup_fields") or {}
    expected = {
        "name": "QA BTC EUR SMA50 Gesprek", "symbol": "BTC", "quote_currency": "EUR",
        "timeframe": "1D", "setup_type": "trade", "plan_scope": "setup_and_strategy",
        "execution_mode": "fixed", "base_amount": 10.0, "entry": 50000.0,
        "stop_loss": 45000.0, "targets": [60000.0], "risk_profile": "balanced",
        "min_benchmark_score": 26, "max_benchmark_score": 45,
    }
    if any(fields.get(key) != value for key, value in expected.items()) or fields.get("entry_signal") != {
        "version": 1, "event": "close_crosses_reference", "direction": "above",
        "timeframe": "1D", "reference": {"kind": "sma", "period": 50},
    }:
        raise AssertionError(f"guided_signal_proposal_fields_invalid: {fields}")
    other = _create_local_user()
    other_token = create_access_token({"sub": str(other["id"]), "role": "user"})
    lifecycle = _proposal_lifecycle(
        base_url, token, other_token, _runtime_record(turn["run_id"])["proposal"],
    )
    if not (lifecycle["cross_user_rejected"] and lifecycle["confirmed"]
            and lifecycle["execution_status"] == 200
            and lifecycle["idempotency_replay_status"] == 200):
        raise AssertionError(f"guided_signal_confirmation_failed: {lifecycle}")
    with sync_engine.connect() as conn:
        saved = conn.execute(text(
            "SELECT s.id AS setup_id, s.market_id AS setup_market_id, "
            "st.market_id AS strategy_market_id, st.data->'entry_signal' AS entry_signal, "
            "st.base_amount AS base_amount "
            "FROM setups s JOIN strategies st ON st.setup_id=s.id AND st.user_id=s.user_id "
            "WHERE s.user_id=:user_id AND s.name=:name"
        ), {"user_id": user["id"], "name": expected["name"]}).mappings().one_or_none()
    if (not saved or saved["setup_market_id"] != saved["strategy_market_id"]
            or saved["entry_signal"] != fields["entry_signal"]
            or float(saved["base_amount"]) != 10.0):
        raise AssertionError(f"guided_signal_persistence_invalid: {saved}")
    return {"complete_request": complete, "guided_turns": guided,
            "confirmation": {"confirmed": True, "owner_isolated": True,
                             "idempotent": True, "same_market": True}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.base_url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"complete_proposal": result["complete_request"]["proposal"],
                      "guided_status": result["guided_turns"][-1]["status"],
                      "confirmation": result["confirmation"]}))
