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
    guided_name = f"BTC Smart DCA Guided {uuid.uuid4().hex[:8]}"
    guided_first = run_gate(
        base_url=base_url, bearer_token=token, timeout_seconds=100,
        message=("Ik wil voor BTC/USDT een Smart DCA maken: maximaal één aankoop per week, "
                 "€200 als basisbedrag. Laat het bedrag meebewegen met de gezamenlijke "
                 "Markt-, Macro- en Technisch-score. Welke drie staffels stel je voor? "
                 "Toon eerst een bewerkbaar concept; start geen bot en plaats geen order."),
    )
    assert guided_first["status"] == "clarification_required"
    guided_first_state = _runtime_record(guided_first["run_id"])["runtime_state"]["guided_state"]
    assert guided_first_state["collected_inputs"]["dca_frequency"] == "weekly"
    assert guided_first_state["collected_inputs"]["dca_trigger_mode"] == "benchmark"
    assert guided_first_state["next_missing_input"] == "timeframe"
    guided_second = run_gate(
        base_url=base_url, bearer_token=token, timeout_seconds=100,
        conversation_id=guided_first["conversation_id"],
        message="1D. De aankoopfrequentie had ik al genoemd: maximaal één keer per week.",
    )
    assert guided_second["status"] == "clarification_required"
    assert _runtime_record(guided_second["run_id"])["runtime_state"]["guided_state"]["next_missing_input"] == "name"
    guided_third = run_gate(
        base_url=base_url, bearer_token=token, timeout_seconds=100,
        conversation_id=guided_first["conversation_id"], message=guided_name,
    )
    guided_record = _runtime_record(guided_third["run_id"])
    assert guided_third["status"] == "completed" and guided_third["final_operation_id"] == "create_setup"
    assert guided_record["proposal"]
    with sync_engine.connect() as connection:
        guided_payload = connection.execute(text(
            "SELECT payload_json FROM finn_v2_proposals WHERE id = :id"
        ), {"id": guided_record["proposal"]["id"]}).scalar_one()
    guided_fields = dict(dict(guided_payload.get("change") or {}).get("setup_fields") or {})
    assert guided_fields["name"] == guided_name
    assert guided_fields["dca_frequency"] == "weekly"
    assert guided_fields["dca_trigger_mode"] == "benchmark" and guided_fields.get("dca_day") is None
    assert tuple(guided_fields[key] for key in (
        "low_threshold", "high_threshold", "low_score_percent",
        "mid_score_percent", "high_score_percent",
    )) == (26, 76, 150, 100, 50)
    no_buy = run_gate(
        base_url=base_url, bearer_token=token, timeout_seconds=100,
        message=("Maak een nieuwe BTC/USDT Smart DCA. Noem hem BTC Smart DCA Vrijdag Local. "
                 "De grafiek is 1D. Koop wekelijks op vrijdag maximaal één keer voor "
                 "€200 basisbedrag. Gebruik Markt, Macro en Technisch samen: onder score "
                 "26 150%, 26 tot 76 100%, vanaf 76 50%. Toon eerst het voorstel; koop niets."),
    )
    no_buy_record = _runtime_record(no_buy["run_id"])
    assert no_buy["status"] == "completed" and no_buy["final_operation_id"] == "create_setup"
    assert no_buy_record["proposal"]
    with sync_engine.connect() as connection:
        no_buy_payload = connection.execute(text(
            "SELECT payload_json FROM finn_v2_proposals WHERE id = :id"
        ), {"id": no_buy_record["proposal"]["id"]}).scalar_one()
    no_buy_fields = dict(dict(no_buy_payload.get("change") or {}).get("setup_fields") or {})
    assert no_buy_fields["dca_trigger_mode"] == "calendar" and no_buy_fields["dca_day"] == "friday"
    named = run_gate(
        base_url=base_url, bearer_token=token, timeout_seconds=100,
        message=("Maak een nieuwe BTC/USDT Smart DCA-setup met de naam "
                 "BTC Smart DCA Default Local op timeframe 1D. Basisbedrag €200, "
                 "maximaal één aankoop per week. Gebruik de volledige gewogen benchmark "
                 "van Markt, Macro en Technisch. Score onder 26: 150%; van 26 tot onder "
                 "76: 100%; vanaf 76: 50%. Toon eerst de conceptkaart; geen bot en geen order."),
    )
    named_record = _runtime_record(named["run_id"])
    assert named["status"] == "completed" and named["final_operation_id"] == "create_setup"
    assert named_record["proposal"]
    with sync_engine.connect() as connection:
        named_payload = connection.execute(text(
            "SELECT payload_json FROM finn_v2_proposals WHERE id = :id"
        ), {"id": named_record["proposal"]["id"]}).scalar_one()
    named_fields = dict(dict(named_payload.get("change") or {}).get("setup_fields") or {})
    assert named_fields["name"] == "BTC Smart DCA Default Local"
    assert named_fields["timeframe"] == "1D"
    print("smart_dca_confirmed_runtime: proposal, confirmation, save and replay passed")


if __name__ == "__main__":
    main()
