#!/usr/bin/env python3
"""Public-route regression for a newly created owner's first saved setup."""

from __future__ import annotations

import json

from sqlalchemy import text

from backend.scripts.run_finn_v2_full_action_matrix import (
    _create_local_user,
    _proposal_lifecycle,
    _runtime_record,
    _wait_for_runtime,
)
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.infrastructure.database import sync_engine
from backend.utils.auth_utils import create_access_token


def main() -> None:
    base_url = "http://127.0.0.1:8000"
    _wait_for_runtime(base_url)
    owner = _create_local_user()
    outsider = _create_local_user()
    with sync_engine.begin() as connection:
        connection.execute(
            text("UPDATE users SET ai_preferences = CAST(:preferences AS jsonb) WHERE id = :user_id"),
            {
                "user_id": owner["id"],
                "preferences": json.dumps({
                    "selected_asset": "BTC", "trader_type": "dca_investor",
                    "primary_timeframes": ["4h"], "asset_focus": ["bitcoin"],
                    "investment_goals": ["wealth_building"], "experience_level": "beginner",
                    "risk_profile": "conservative",
                }),
            },
        )
    token = create_access_token({"sub": str(owner["id"]), "role": "user"})
    other_token = create_access_token({"sub": str(outsider["id"]), "role": "user"})
    capability = run_gate(
        base_url=base_url, bearer_token=token,
        message="Gebaseerd op mijn profiel, waar kan je mij mee helpen?",
        timeout_seconds=75,
    )
    capability_state = _runtime_record(capability["run_id"])["runtime_state"]
    capability_answer = str((capability_state.get("terminal_response") or {}).get("content") or "")
    print(json.dumps({
        "capability_status": capability["status"],
        "capability_answer": capability_answer,
        "capability_tools": [
            item.get("name") for item in (capability_state.get("responses_exchange") or {}).get("tool_trace") or []
        ],
    }, ensure_ascii=False))
    assert capability["status"] == "completed", "fresh profile-only capability question failed"
    assert "conserv" in capability_answer.casefold(), "answer ignored the stored conservative profile"
    name = "Build Smoke BTC"
    started = run_gate(
        base_url=base_url, bearer_token=token,
        message=f"Maak een wekelijkse BTC DCA-setup van 100 euro met naam {name}.",
        timeout_seconds=75,
    )
    timeframe = run_gate(
        base_url=base_url, bearer_token=token,
        conversation_id=started["conversation_id"], message="4H", timeout_seconds=75,
    )
    created = run_gate(
        base_url=base_url, bearer_token=token,
        conversation_id=started["conversation_id"], message="Maandag", timeout_seconds=75,
    )
    assert timeframe["conversation_id"] == created["conversation_id"] == started["conversation_id"]
    for label, observed in (("started", started), ("timeframe", timeframe), ("completed_draft", created)):
        prior = _runtime_record(observed["run_id"])
        print(json.dumps({
            "phase": label, "status": observed["status"],
            "operation": observed.get("final_operation_id"),
            "supplied": prior["terminal_projection"].get("supplied_inputs"),
            "missing": prior["terminal_projection"].get("missing_inputs"),
            "proposal": bool(prior["proposal"]),
        }, ensure_ascii=False, default=str))
    proposal = _runtime_record(created["run_id"])["proposal"]
    assert proposal, "first setup did not produce a proposal"
    lifecycle = _proposal_lifecycle(base_url, token, other_token, proposal)
    assert lifecycle["execution_result"] == "succeeded", lifecycle
    readback = run_gate(
        base_url=base_url, bearer_token=token,
        conversation_id=created["conversation_id"],
        message="Welke setup heb ik net opgeslagen?", timeout_seconds=75,
    )
    record = _runtime_record(readback["run_id"])
    state = record["runtime_state"]
    exchange = state.get("responses_exchange") or {}
    print(json.dumps({
        "name": name,
        "created_status": created["status"],
        "lifecycle": lifecycle,
        "readback_status": readback["status"],
        "readback_operation": readback.get("final_operation_id"),
        "answer": (state.get("terminal_response") or {}).get("content"),
        "trace": exchange.get("tool_trace"),
        "terminal_error": record["terminal_projection"].get("error_code"),
    }, ensure_ascii=False, default=str))
    assert readback["status"] == "completed", readback
    assert name in str((state.get("terminal_response") or {}).get("content") or ""), "readback lost the exact saved setup name"
    setup_results = [
        item for call in exchange.get("tool_trace") or []
        for item in (call.get("result") or {}).get("results") or []
        if item.get("scope") == "read_active_setup" and item.get("status") == "completed"
    ]
    assert setup_results and setup_results[-1]["data"]["timeframe"] == "4H", "guided timeframe was lost"
    assert any(
        item.get("name") == "get_active_plan_and_strategy"
        for item in exchange.get("tool_trace") or []
    ), "setup readback did not read the persisted setup"


if __name__ == "__main__":
    main()
