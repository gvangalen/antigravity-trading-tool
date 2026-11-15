#!/usr/bin/env python3
"""Local HTTP/Celery/Responses check for Paper cash and coach followups."""

from __future__ import annotations

import argparse
import json
import re
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
    parser.add_argument("--followup")
    parser.add_argument("--blocked-decision", action="store_true")
    parser.add_argument("--unlinked-concept", action="store_true")
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
        for quote in ("EUR", "USDT"):
            connection.execute(text("""
                INSERT INTO trading_markets
                    (asset_symbol, quote_currency, venue, provider, provider_symbol,
                     tradingview_symbol, source_verified_at, is_active)
                VALUES ('BTC', :quote, 'BINANCE', 'binance', :provider_symbol,
                        :tradingview_symbol, NOW(), TRUE)
                ON CONFLICT (asset_symbol, quote_currency, venue) DO UPDATE SET
                    source_verified_at = EXCLUDED.source_verified_at, is_active = TRUE
            """), {"quote": quote, "provider_symbol": f"BTC{quote}",
                   "tradingview_symbol": f"BINANCE:BTC{quote}"})
        for symbol, cash in (("BTC", 9599.97), ("AAPL", 405.48)):
            setup_id = _insert_setup(connection, user["id"], f"{symbol} Paper Scope")
            connection.execute(text("""
                UPDATE setups SET symbol = :symbol WHERE id = :setup_id AND user_id = :user_id
            """), {"symbol": symbol, "setup_id": setup_id, "user_id": user["id"]})
            concept_id = (
                _insert_setup(connection, user["id"], "BTC/EUR-conceptsetup")
                if args.unlinked_concept and symbol == "BTC" else setup_id
            )
            if args.question and symbol == "BTC":
                connection.execute(text("""
                    UPDATE setups SET
                        market_id = (SELECT id FROM trading_markets
                                     WHERE asset_symbol = :symbol AND quote_currency = 'EUR'
                                     ORDER BY id LIMIT 1),
                        min_benchmark_score = 61, max_benchmark_score = 75
                    WHERE id = :setup_id AND user_id = :user_id
                """), {"symbol": symbol, "setup_id": concept_id, "user_id": user["id"]})
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
            if args.blocked_decision and symbol == "BTC":
                connection.execute(text("""
                    INSERT INTO bot_decisions
                        (user_id, bot_id, strategy_id, setup_id, symbol,
                         decision_date, decision_ts, action, confidence, amount_eur, status,
                         scores_json)
                    VALUES (:user_id, :bot_id, :strategy_id, :setup_id, :symbol,
                            CURRENT_DATE, CURRENT_TIMESTAMP, 'hold', 'low', 0, 'planned',
                            CAST(:scores AS jsonb))
                """), {
                    "user_id": user["id"], "bot_id": bot_id,
                    "strategy_id": strategy_id, "setup_id": setup_id,
                    "symbol": symbol, "scores": json.dumps({
                        "guardrails_result": {
                            "allowed": False,
                            "blocked_by": "strategy_price_conversion_unavailable",
                            "reason": "Een recente USD/EUR-omrekening ontbreekt.",
                        },
                    }),
                })

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
    followup_observed = None
    followup_record = None
    if args.followup:
        followup_observed = run_gate(
            base_url=args.base_url, bearer_token=token, message=args.followup,
            conversation_id=observed["conversation_id"], timeout_seconds=120,
        )
        followup_record = _runtime_record(followup_observed["run_id"])
    portfolio_reads = [
        item["data"]
        for call in trace for item in (call.get("result") or {}).get("results") or []
        if isinstance(item, dict) and item.get("scope") == "read_portfolio"
        and isinstance(item.get("data"), dict)
    ]
    decision_rows = [
        row for call in trace for item in (call.get("result") or {}).get("results") or []
        if isinstance(item, dict) and item.get("scope") == "read_review_history"
        and isinstance(item.get("data"), dict)
        for row in item["data"].get("latest_bot_decisions") or []
        if isinstance(row, dict)
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
        requested_pairs = set(re.findall(r"\bBTC/(?:EUR|USDT)\b", question, re.I))
        checks["requested_pairs_answered"] = all(pair.upper() in answer.upper() for pair in requested_pairs)
    if args.blocked_decision:
        checks["blocked_decision_read"] = any(
            row.get("safety_state") in {"blocked", "error"}
            and "omrekening" in str(row.get("safety_reason") or "").lower()
            and row.get("decision_at") for row in decision_rows
        )
        checks["blocked_decision_answer"] = (
            "geblokkeerd" in answer.lower() and "omrekening" in answer.lower()
        )
    followup_trace = (
        (followup_record["runtime_state"].get("responses_exchange") or {}).get("tool_trace") or []
        if followup_record else []
    )
    followup_answer = str(
        (followup_record["runtime_state"].get("terminal_response") or {}).get("content") or ""
    ) if followup_record else ""
    if args.followup:
        checks.update({
            "followup_completed": followup_observed["status"] == "completed",
            "followup_single_dispatch": followup_observed["dispatch_count"]
                == followup_observed["attempt_count"] == 1,
            "followup_evaluated_plan": any(
                call.get("name") == "evaluate_plan" for call in followup_trace
            ),
            "followup_no_proposal": followup_record["proposal"] is None,
            "followup_saved_score_band": "61–75" in followup_answer
                or "61-75" in followup_answer,
            "followup_scoped_pair": "BTC/EUR" in followup_answer,
        })
        if args.blocked_decision:
            followup_decisions = [
                row for call in followup_trace
                for item in (call.get("result") or {}).get("results") or []
                if isinstance(item, dict) and item.get("scope") == "read_review_history"
                and isinstance(item.get("data"), dict)
                for row in item["data"].get("latest_bot_decisions") or []
                if isinstance(row, dict)
            ]
            checks["followup_blocked_decision_read"] = any(
                row.get("safety_state") in {"blocked", "error"}
                and "omrekening" in str(row.get("safety_reason") or "").lower()
                and row.get("decision_at") for row in followup_decisions
            )
            checks["followup_blocked_decision_answer"] = (
                "geblokkeerd" in followup_answer.lower()
                and "omrekening" in followup_answer.lower()
            )
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
        "followup": ({
            "question": args.followup,
            "run_id": followup_observed["run_id"],
            "status": followup_observed["status"],
            "tool_names": [call.get("name") for call in followup_trace],
            "answer": followup_answer,
        } if followup_observed and followup_record else None),
    }
    Path(args.output).write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    if not artifact["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
