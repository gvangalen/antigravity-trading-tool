#!/usr/bin/env python3
"""Local HTTP/Celery/Responses check for an account-wide Paper cash question."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import text

from backend.infrastructure.database import sync_engine
from backend.scripts.run_finn_v2_full_action_matrix import (
    _create_local_user, _insert_bot, _insert_setup, _insert_strategy, _runtime_record,
)
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.utils.auth_utils import create_access_token


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--output", required=True)
    parser.add_argument("--question")
    args = parser.parse_args()
    if not args.base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise SystemExit("This regression is local-only")

    user = _create_local_user()
    with sync_engine.begin() as connection:
        connection.execute(text("""
            UPDATE users SET ai_preferences = CAST(:preferences AS jsonb)
            WHERE id = :user_id
        """), {"user_id": user["id"],
               "preferences": json.dumps({"selected_asset": "BTC"})})
        for symbol, cash in (("BTC", 9599.97), ("AAPL", 405.48)):
            setup_id = _insert_setup(connection, user["id"], f"{symbol} Paper Scope")
            connection.execute(text("""
                UPDATE setups SET symbol = :symbol WHERE id = :setup_id AND user_id = :user_id
            """), {"symbol": symbol, "setup_id": setup_id, "user_id": user["id"]})
            if args.question and symbol == "BTC":
                connection.execute(text("""
                    UPDATE setups SET
                        market_id = (SELECT id FROM trading_markets
                                     WHERE asset_symbol = :symbol AND quote_currency = 'EUR'
                                     ORDER BY id LIMIT 1),
                        min_benchmark_score = 61, max_benchmark_score = 75
                    WHERE id = :setup_id AND user_id = :user_id
                """), {"symbol": symbol, "setup_id": setup_id, "user_id": user["id"]})
            strategy_id = _insert_strategy(connection, user["id"], setup_id,
                                           f"{symbol} Paper Scope Strategy")
            bot_id = _insert_bot(connection, user["id"], strategy_id,
                                 f"{symbol} Paper Scope Bot")
            connection.execute(text("""
                UPDATE bot_configs SET symbol = :symbol
                WHERE id = :bot_id AND user_id = :user_id
            """), {"symbol": symbol, "bot_id": bot_id, "user_id": user["id"]})
            connection.execute(text("""
                INSERT INTO bot_portfolios
                    (bot_id, user_id, symbol, cash_eur, position_qty,
                     invested_eur, avg_entry, realized_pnl_eur)
                VALUES (:bot_id, :user_id, :symbol, :cash, 0, 0, 0, 0)
            """), {"bot_id": bot_id, "user_id": user["id"],
                   "symbol": symbol, "cash": cash})

    token = create_access_token({"sub": str(user["id"]), "role": "user"})
    question = args.question or (
        "Ik bespreek mijn BTC-plan en bot. Wat is de gezamenlijke Paper-kas "
        "van al mijn bots en welke bots zijn daarin opgenomen? "
        "Vergelijk dit met alleen de BTC-bot. Wijzig niets."
    )
    observed = run_gate(
        base_url=args.base_url, bearer_token=token, message=question,
        timeout_seconds=120,
    )
    record = _runtime_record(observed["run_id"])
    state = record["runtime_state"]
    trace = (state.get("responses_exchange") or {}).get("tool_trace") or []
    answer = str((state.get("terminal_response") or {}).get("content") or "")
    portfolio_reads = [
        item["data"]
        for call in trace for item in (call.get("result") or {}).get("results") or []
        if isinstance(item, dict) and item.get("scope") == "read_portfolio"
        and isinstance(item.get("data"), dict)
    ]
    checks = {
        "completed": observed["status"] == "completed",
        "single_dispatch": observed["dispatch_count"] == observed["attempt_count"] == 1,
        "no_proposal": record["proposal"] is None,
        "full_cash_read": any(
            isinstance((row.get("global") or {}).get("cash_balance"), (int, float))
            and abs(row["global"]["cash_balance"] - 10005.45) < 0.005
            for row in portfolio_reads
        ),
        "both_bots_read": any(
            {bot.get("symbol") for bot in row.get("bots") or []} == {"BTC", "AAPL"}
            for row in portfolio_reads
        ),
        "combined_cash_answer": "10.005,45" in answer or "10005.45" in answer,
        "distinguishes_bot_cash": "9.599,97" in answer or "9599.97" in answer,
    }
    if args.question:
        checks["saved_score_band_answer"] = "61–75" in answer or "61-75" in answer
        checks["both_pairs_answered"] = "BTC/EUR" in answer and "BTC/USDT" in answer
    artifact = {
        "synthetic_local_only": True, "question": question,
        "run_id": observed["run_id"], "status": observed["status"],
        "tool_names": [call.get("name") for call in trace],
        "read_scopes": [
            {"tool": call.get("name"), "scope": item.get("scope"),
             "status": item.get("status"), "reason": item.get("reason")}
            for call in trace for item in (call.get("result") or {}).get("results") or []
            if isinstance(item, dict)
        ],
        "answer": answer, "checks": checks, "pass": all(checks.values()),
    }
    Path(args.output).write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    if not artifact["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
