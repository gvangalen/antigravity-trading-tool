#!/usr/bin/env python3
"""Verify a fixed Friday DCA through the local public FINN runtime."""
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
        "127.0.0.1", os.getenv("FINN_LOCAL_POSTGRES_PORT", "55432"), "finn_local"
    ) or os.getenv("FINN_LOCAL_SAFE_ADAPTERS") != "1":
        raise RuntimeError("calendar_dca_probe_requires_safe_local_fixture")
    owner = _create_local_user()
    other = _create_local_user()
    token = create_access_token({"sub": str(owner["id"]), "role": "user"})
    other_token = create_access_token({"sub": str(other["id"]), "role": "user"})
    name = f"Kalender DCA Local {uuid.uuid4().hex[:8]}"
    base_url = "http://127.0.0.1:18000"
    result = run_gate(
        base_url=base_url, bearer_token=token, timeout_seconds=100,
        message=(f"Maak voor BTC/USDT een setup met de naam {name}, op 1D. "
                 "Koop elke week op vrijdag een vast bedrag van €50. Dit is gewone "
                 "kalender-DCA, niet scoregestuurd. Toon een voorstel en activeer geen bot of order."),
    )
    record = _runtime_record(result["run_id"])
    proposal = record["proposal"]
    assert result["status"] == "completed" and result["final_operation_id"] == "create_setup", result
    assert proposal and record["runtime_state"]["guided_state"]["missing_required_inputs"] == []
    with sync_engine.connect() as connection:
        payload = connection.execute(text(
            "SELECT payload_json FROM finn_v2_proposals WHERE id = :id"
        ), {"id": proposal["id"]}).scalar_one()
    fields = dict(dict(payload.get("change") or {}).get("setup_fields") or {})
    assert fields.get("symbol") == "BTC" and fields.get("quote_currency") == "USDT"
    assert fields.get("dca_frequency") == "weekly" and fields.get("dca_day") == "friday"
    assert fields.get("dca_amount_mode") == "fixed" and fields.get("base_amount") == 50
    assert fields.get("dca_trigger_mode") in (None, "calendar")
    assert not fields.get("score_source")
    lifecycle = _proposal_lifecycle(base_url, token, other_token, proposal)
    assert lifecycle["cross_user_rejected"]
    assert lifecycle["publish_status"] == lifecycle["confirmation_status"] == 200
    assert lifecycle["confirmed"] and lifecycle["execution_status"] == 200
    assert lifecycle["execution_result"] == "succeeded", lifecycle
    assert lifecycle["idempotency_replay_status"] == 200
    assert lifecycle["idempotency_result"] == "already_executed"
    with sync_engine.connect() as connection:
        saved = connection.execute(text(
            "SELECT id, dca_day, dca_frequency FROM setups "
            "WHERE user_id = :user_id AND name = :name"
        ), {"user_id": owner["id"], "name": name}).mappings().all()
        assert len(saved) == 1, saved
        assert saved[0]["dca_frequency"] == "weekly" and saved[0]["dca_day"] == "5"
        strategy_count = connection.execute(text(
            "SELECT count(*) FROM strategies WHERE user_id = :user_id AND setup_id = :setup_id"
        ), {"user_id": owner["id"], "setup_id": saved[0]["id"]}).scalar_one()
        bot_count = connection.execute(text(
            "SELECT count(*) FROM bot_configs WHERE user_id = :user_id"
        ), {"user_id": owner["id"]}).scalar_one()
    assert strategy_count == 1 and bot_count == 0
    print("calendar_dca_confirmed_runtime: fixed Friday proposal, save and replay passed")


if __name__ == "__main__":
    main()
