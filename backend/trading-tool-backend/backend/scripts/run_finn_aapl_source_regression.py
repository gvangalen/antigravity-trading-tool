#!/usr/bin/env python3
"""Local public-route regression for owner-scoped bot reasons and dated reports."""

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


QUESTIONS = (
    "Waarom plaatste mijn AAPL Paper-bot bij de laatste beoordeling geen order? "
    "Noem het tijdstip en de concrete reden. Wijzig niets.",
    "Wat was de exacte reden?",
    "Vergelijk mijn AAPL-botcheck rond 10:00 CET op 19 november 2026 met "
    "het dagrapport van 05:21 CET. Welke botreden is per bron opgeslagen? Wijzig niets.",
    "Beoordeel mijn AAPL-setup, score, bot, rapport, koers en Paper-kas met hun "
    "eigen bronmomenten. Wat doe ik bij de volgende beursopening? Wijzig niets.",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if urlparse(args.base_url).hostname not in {"localhost", "127.0.0.1"}:
        raise SystemExit("local_loopback_required")
    if (os.getenv("APP_ENV") != "local_finn"
            or os.getenv("DB_HOST") not in {"localhost", "127.0.0.1"}
            or os.getenv("DB_NAME") != "finn_local"
            or os.getenv("FINN_LOCAL_SAFE_ADAPTERS") != "1"):
        raise SystemExit("local_finn_fixture_environment_required")
    user = _create_local_user()
    with sync_engine.begin() as connection:
        connection.execute(text("""
            UPDATE users SET ai_preferences = CAST(:preferences AS jsonb) WHERE id = :user_id
        """), {"user_id": user["id"], "preferences": json.dumps({
            "selected_asset": "AAPL", "locale": "nl",
        })})
        setup_id = _insert_setup(connection, user["id"], "Local AAPL Coach", symbol="AAPL")
        connection.execute(text("""
            UPDATE setups SET min_benchmark_score = 61, max_benchmark_score = 75
            WHERE id = :setup_id AND user_id = :user_id
        """), {"setup_id": setup_id, "user_id": user["id"]})
        strategy_id = _insert_strategy(connection, user["id"], setup_id, "Local AAPL Strategy")
        bot_id = _insert_bot(connection, user["id"], strategy_id, "Local AAPL Paper Bot")
        connection.execute(text("""
            UPDATE bot_configs SET symbol = 'AAPL' WHERE id = :bot_id AND user_id = :user_id
        """), {"bot_id": bot_id, "user_id": user["id"]})
        connection.execute(text("""
            INSERT INTO bot_decisions
              (user_id, bot_id, strategy_id, setup_id, symbol, decision_date,
               decision_ts, action, status, reason_json, scores_json)
            VALUES
              (:user_id, :bot_id, :strategy_id, :setup_id, 'AAPL', '2026-11-19',
               '2026-11-19 20:30:17', 'hold', 'skipped', CAST(:reasons AS jsonb), '{}'::jsonb)
        """), {"user_id": user["id"], "bot_id": bot_id, "strategy_id": strategy_id,
               "setup_id": setup_id, "reasons": json.dumps([
                   "Reguliere sessie gesloten; actuele koers ontbreekt",
               ])})
        # The disposable local bootstrap predates this production report column.
        connection.execute(text("""
            ALTER TABLE daily_reports ADD COLUMN IF NOT EXISTS generated_at TIMESTAMPTZ
        """))
        connection.execute(text("""
            INSERT INTO daily_reports
              (user_id, report_date, status, created_at, generated_at, score_source_snapshot)
            VALUES
              (:user_id, '2026-11-19', 'completed', '2026-11-19 19:08:00',
               '2026-11-19 19:08:00+00', CAST(:snapshot AS jsonb))
        """), {"user_id": user["id"], "snapshot": json.dumps({
            "assets": [{"symbol": "AAPL"}], "report_v2": {"automation": {"bots": []}},
        })})
        connection.execute(text("""
            INSERT INTO market_data
              (symbol, quote_currency, price, timestamp, source_observed_at, price_provider)
            VALUES ('AAPL', 'USD', 349.34, '2026-11-19 20:29:00',
                    '2026-11-19 20:29:00', 'local_fixture')
        """))
    token = create_access_token({"sub": str(user["id"]), "role": "user"})
    conversation_id = None
    turns = []
    for index, question in enumerate(QUESTIONS):
        if index == 3:
            # The broad question must read the newest saved decision, even
            # after the conversation discussed an older historical check.
            with sync_engine.begin() as connection:
                connection.execute(text("""
                    INSERT INTO bot_decisions
                      (user_id, bot_id, strategy_id, setup_id, symbol, decision_date,
                       decision_ts, action, status, reason_json, scores_json)
                    VALUES (:user_id, :bot_id, :strategy_id, :setup_id, 'AAPL',
                            '2026-11-20', '2026-11-20 17:45:31', 'hold', 'skipped',
                            CAST(:reasons AS jsonb), '{}'::jsonb)
                """), {"user_id": user["id"], "bot_id": bot_id,
                       "strategy_id": strategy_id, "setup_id": setup_id,
                       "reasons": json.dumps([
                           "Opgeslagen setupvoorwaarden passen niet bij de actuele benchmark.",
                       ])})
        observed = run_gate(base_url=args.base_url, bearer_token=token,
                            message=question, conversation_id=conversation_id,
                            timeout_seconds=90,
                            workspace_hints={"page": "/asset", "symbol": "AAPL"})
        conversation_id = observed["conversation_id"]
        record = _runtime_record(observed["run_id"])
        answer = str((record["runtime_state"].get("terminal_response") or {}).get("content") or "")
        checks = {"completed": observed["status"] == "completed",
                  "read_only": record["proposal"] is None,
                  "polling_sse": bool(observed["polling_sse_contract_projection"])}
        if index in {0, 1}:
            checks["saved_reason"] = "Reguliere sessie gesloten" in answer
            checks["missing_quote"] = "actuele koers ontbreekt" in answer
        if index == 2:
            checks["report_clock"] = "05:21" in answer
            checks["no_later_report_substitution"] = "20:08" not in answer
        if index == 3:
            checks["not_generic"] = "Ik kan de bronmomenten in dit antwoord niet verifiëren" not in answer
            normalized = answer.casefold()
            checks["bot_reason"] = (
                "setupvoorwaarden" in normalized
                and "passen" in normalized
                and "actuele benchmark" in normalized
            )
        turns.append({"question": question, "run_id": observed["run_id"],
                      "status": observed["status"], "answer": answer,
                      "checks": checks, "pass": all(checks.values())})
    artifact = {"synthetic_local_only": True, "turns": turns,
                "complete": all(turn["pass"] for turn in turns)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"complete": artifact["complete"],
                      "passes": [turn["pass"] for turn in turns]}))
    if not artifact["complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
