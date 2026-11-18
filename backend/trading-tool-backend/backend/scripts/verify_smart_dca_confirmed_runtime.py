#!/usr/bin/env python3
"""Exercise the exact guided Smart DCA proposal through local public routes.

Uses synthetic local owners and never creates a bot or order. The separate
migration probe tests the preexisting production schedule constraint.
"""
from __future__ import annotations

import os
import uuid

from sqlalchemy import text

from backend.infrastructure.database import sync_engine
from backend.scripts.run_finn_v2_full_action_matrix import (
    _create_local_user, _proposal_lifecycle, _runtime_record,
)
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.utils.auth_utils import create_access_token


def main() -> None:
    if (os.getenv("DB_HOST"), os.getenv("DB_PORT"), os.getenv("DB_NAME")) != (
        "127.0.0.1", "55432", "finn_local"
    ) or os.getenv("FINN_LOCAL_SAFE_ADAPTERS") != "1":
        raise RuntimeError("smart_dca_runtime_probe_requires_safe_local_fixture")
    owner = _create_local_user()
    other = _create_local_user()
    token = create_access_token({"sub": str(owner["id"]), "role": "user"})
    other_token = create_access_token({"sub": str(other["id"]), "role": "user"})
    name = f"Smart DCA Local {uuid.uuid4().hex[:8]}"
    base_url = "http://127.0.0.1:18000"
    first = run_gate(
        base_url=base_url, bearer_token=token, timeout_seconds=100,
        message=(f"Maak voor BTC/USDT een setup met de naam {name}, op 1D. "
                 "Ik wil wekelijks maximaal een keer €200 basisbedrag inzetten. "
                 "Gebruik de volledige benchmarkscore van Markt, Macro en Technisch: "
                 "bij lage scores 150%, bij middenscores 100% en bij hoge scores 50%. "
                 "Toon eerst een voorstel; activeer geen bot en plaats geen order."),
    )
    first_record = _runtime_record(first["run_id"])
    assert first["status"] == "clarification_required"
    assert first_record["runtime_state"]["guided_state"]["missing_required_inputs"] == [
        "low_threshold", "high_threshold",
    ]
    first_inputs = first_record["runtime_state"]["guided_state"]["collected_inputs"]
    assert first_inputs["dca_trigger_mode"] == "benchmark" and not first_inputs.get("dca_day")
    second = run_gate(
        base_url=base_url, bearer_token=token, timeout_seconds=100,
        conversation_id=first["conversation_id"],
        message=("Gebruik onder 26 voor laag: 150% van €200. Van 26 tot onder 76 is midden: "
                 "100%. Vanaf 76 is hoog: 50%. BTC/USDT, wekelijks, "
                 "volledige benchmark. Maak de bevestigbare setupkaart en gekoppelde strategie; "
                 "geen bot of order."),
    )
    record = _runtime_record(second["run_id"])
    proposal = record["proposal"]
    assert second["status"] == "completed" and second["final_operation_id"] == "create_setup"
    assert proposal and record["runtime_state"]["guided_state"]["missing_required_inputs"] == []
    with sync_engine.connect() as connection:
        payload = connection.execute(text(
            "SELECT payload_json FROM finn_v2_proposals WHERE id = :id"
        ), {"id": proposal["id"]}).scalar_one()
    fields = dict(dict(payload.get("change") or {}).get("setup_fields") or {})
    assert fields.get("symbol") == "BTC" and fields.get("quote_currency") == "USDT"
    assert fields.get("dca_trigger_mode") == "benchmark"
    assert fields.get("dca_amount_mode") == "score_bands" and fields.get("dca_day") is None
    assert (fields.get("low_threshold"), fields.get("high_threshold")) == (26, 76)
    assert tuple(fields.get(key) for key in (
        "low_score_percent", "mid_score_percent", "high_score_percent"
    )) == (150, 100, 50)
    result = _proposal_lifecycle(base_url, token, other_token, proposal)
    assert result["cross_user_rejected"]
    assert result["publish_status"] == result["confirmation_status"] == 200
    assert result["confirmed"] and result["execution_status"] == 200
    assert result["execution_result"] == "succeeded", result
    assert result["idempotency_replay_status"] == 200
    assert result["idempotency_result"] == "already_executed"
    with sync_engine.connect() as connection:
        saved = connection.execute(text(
            "SELECT id, dca_trigger_mode, dca_day, dca_frequency FROM setups "
            "WHERE user_id = :user_id AND name = :name"
        ), {"user_id": owner["id"], "name": name}).mappings().all()
        assert len(saved) == 1, saved
        assert saved[0]["dca_trigger_mode"] == "benchmark"
        assert saved[0]["dca_day"] is None and saved[0]["dca_frequency"] == "weekly"
        strategy_count = connection.execute(text(
            "SELECT count(*) FROM strategies WHERE user_id = :user_id AND setup_id = :setup_id"
        ), {"user_id": owner["id"], "setup_id": saved[0]["id"]}).scalar_one()
        bot_count = connection.execute(text(
            "SELECT count(*) FROM bot_configs WHERE user_id = :user_id"
        ), {"user_id": owner["id"]}).scalar_one()
    assert strategy_count == 1 and bot_count == 0
    print("smart_dca_confirmed_runtime: proposal, confirmation, save and replay passed")


if __name__ == "__main__":
    main()
