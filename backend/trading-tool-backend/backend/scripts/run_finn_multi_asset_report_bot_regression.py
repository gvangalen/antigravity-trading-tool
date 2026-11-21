#!/usr/bin/env python3
"""Synthetic local HTTP/Celery regression for dated multi-asset Paper evidence."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import text

from backend.infrastructure.database import sync_engine
from backend.scripts.run_finn_v2_full_action_matrix import (
    _create_local_user, _insert_bot, _insert_setup, _insert_strategy, _runtime_record,
)
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.utils.auth_utils import create_access_token


QUESTION = (
    "Vergelijk voor AAPL en BTC de botstatus in het dagrapport van 21 november "
    "met de laatst opgeslagen Paper-botchecks. Houd BTC/EUR zonder gekoppelde "
    "bot apart van de BTC-bot; verzin geen besluit. Geef per bron datum en tijd. Lees alleen."
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if urlparse(args.base_url).hostname not in {"localhost", "127.0.0.1"}:
        raise SystemExit("local_loopback_required")
    if (os.getenv("APP_ENV") != "local_finn" or os.getenv("DB_NAME") != "finn_parity"
            or os.getenv("FINN_LOCAL_SAFE_ADAPTERS") != "1"):
        raise SystemExit("local_parity_fixture_environment_required")
    user = _create_local_user()
    with sync_engine.begin() as connection:
        connection.execute(text("""
            UPDATE users SET ai_preferences = CAST(:preferences AS jsonb) WHERE id = :user_id
        """), {"user_id": user["id"], "preferences": json.dumps({
            "selected_asset": "AAPL", "locale": "nl",
        })})
        bot_ids = {}
        for symbol in ("AAPL", "BTC"):
            setup_id = _insert_setup(connection, user["id"], f"Local {symbol} Setup", symbol=symbol)
            strategy_id = _insert_strategy(connection, user["id"], setup_id, f"Local {symbol} Strategy")
            bot_id = _insert_bot(connection, user["id"], strategy_id, f"Local {symbol} Paper Bot")
            bot_ids[symbol] = bot_id
            connection.execute(text("""
                UPDATE bot_configs SET symbol=:symbol WHERE id=:bot_id AND user_id=:user_id
            """), {"symbol": symbol, "bot_id": bot_id, "user_id": user["id"]})
            connection.execute(text("""
                INSERT INTO bot_decisions
                    (user_id, bot_id, strategy_id, setup_id, symbol, decision_date,
                     decision_ts, action, status, reason_json, scores_json)
                VALUES (:user_id, :bot_id, :strategy_id, :setup_id, :symbol,
                        '2026-11-21', CAST(:decision_ts AS timestamptz), 'hold', 'skipped',
                        CAST(:reasons AS jsonb), CAST(:scores AS jsonb))
            """), {
                "user_id": user["id"], "bot_id": bot_id, "strategy_id": strategy_id,
                "setup_id": setup_id, "symbol": symbol,
                "decision_ts": "2026-11-21T09:15:17+00:00" if symbol == "AAPL"
                else "2026-11-21T09:16:00+00:00",
                "reasons": json.dumps(["Latere gecontroleerde Paper-check"]),
                "scores": json.dumps({"guardrail_reason": "market_price_stale"}
                                     if symbol == "AAPL" else {}),
            })
        connection.execute(text("""
            ALTER TABLE daily_reports ADD COLUMN IF NOT EXISTS generated_at TIMESTAMPTZ
        """))
        snapshot = {"assets": [{"symbol": "AAPL"}, {"symbol": "BTC"}],
                    "report_v2": {"automation": {"bots": [
                        {"bot_id": bot_ids["AAPL"], "symbol": "AAPL", "is_live": False,
                         "latest_decision": {"at": "2026-11-21T04:30:32+00:00",
                                             "block_code": "market_price_stale",
                                             "reason": "De marktprijs is te oud voor een Paper-order."}},
                        {"bot_id": bot_ids["BTC"], "symbol": "BTC", "is_live": False,
                         "trading_pair": "BTC/USDT",
                         "latest_decision": {"at": "2026-11-21T04:30:00+00:00",
                                             "reason": "Score buiten band."}},
                    ]}}}
        connection.execute(text("""
            INSERT INTO daily_reports
                (user_id, report_date, status, created_at, generated_at, score_source_snapshot)
            VALUES (:user_id, '2026-11-21', 'completed',
                    '2026-11-21T04:39:26+00:00', '2026-11-21T04:39:26+00:00',
                    CAST(:snapshot AS jsonb))
        """), {"user_id": user["id"], "snapshot": json.dumps(snapshot)})
    observed = run_gate(
        base_url=args.base_url,
        bearer_token=create_access_token({"sub": str(user["id"]), "role": "user"}),
        message=QUESTION, timeout_seconds=90,
        workspace_hints={"page": "/asset", "symbol": "AAPL"},
    )
    record = _runtime_record(observed["run_id"])
    answer = str((record["runtime_state"].get("terminal_response") or {}).get("content") or "")
    checks = {
        "completed": observed["status"] == "completed",
        "read_only": record["proposal"] is None,
        "polling_sse": bool(observed["polling_sse_contract_projection"]),
        "report_reason": "Geen recente marktprijs beschikbaar voor deze beoordeling" in answer,
        "separate_checks": "05:30" in answer and "10:15" in answer,
        "pair_boundary": "BTC/USDT" in answer and "BTC/EUR" in answer
        and "geen gekoppelde Paper-bot" in answer,
        "not_generic": "bronmomenten in dit antwoord niet verifiëren" not in answer,
    }
    artifact = {"synthetic_local_only": True, "run_id": observed["run_id"],
                "status": observed["status"], "answer": answer, "checks": checks,
                "complete": all(checks.values())}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"complete": artifact["complete"], "checks": checks}))
    if not artifact["complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
