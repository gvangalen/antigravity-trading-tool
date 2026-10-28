#!/usr/bin/env python3
"""Isolated worker probe: one exact ETH/EUR or ETH/USDT Paper fill.

Uses the local-finn PostgreSQL/Redis endpoints only. A base ETH price and
score deliberately coexist, so borrowing either is observable.
"""

import json
import math
import os

from backend.scripts.probe_local_score2_positive_paper import (
    QUEUE, _assert_local_only, _seed_fixture,
)
from backend.scripts.probe_protected_score2_exact_pair_paper import _verify as verify_protected_pair
from backend.utils.db import get_db_connection


def main() -> None:
    _assert_local_only()
    quote = os.getenv("FINN_LOCAL_PAIR_QUOTE", "USDT").upper()
    if quote not in {"EUR", "USDT"}:
        raise ValueError("unsupported_local_pair_quote")
    missing_technical = os.getenv("FINN_LOCAL_PAIR_MISSING_TECHNICAL") == "1"
    stale_fx = os.getenv("FINN_LOCAL_PAIR_STALE_FX") == "1"
    if stale_fx and quote != "USDT":
        raise ValueError("stale_fx_probe_requires_usdt")
    from backend.celery_task.celery_app import celery_app
    from backend.celery_task.store_daily_scores_task import (
        build_daily_scores_for_market, build_daily_scores_for_user,
    )

    user_id, bot_id, report_date = _seed_fixture()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            if stale_fx:
                cur.execute("""
                    UPDATE portfolio_fx_rates
                    SET observed_at=NOW()-INTERVAL '3 hours'
                    WHERE quote_currency='USDT'
                """)
            cur.execute("""
                INSERT INTO trading_markets
                  (asset_symbol,quote_currency,venue,provider,provider_symbol,
                   tradingview_symbol,source_verified_at,is_active)
                VALUES ('ETH',%s,'BINANCE','binance',%s,
                        %s,NOW(),TRUE)
                ON CONFLICT (asset_symbol,quote_currency,venue) DO UPDATE SET
                  source_verified_at=EXCLUDED.source_verified_at,
                  is_active=TRUE
                RETURNING id
            """, (quote, f"ETH{quote}", f"BINANCE:ETH{quote}"))
            market_id = int(cur.fetchone()[0])
            cur.execute("SELECT strategy_id FROM bot_configs WHERE id=%s AND user_id=%s",
                        (bot_id, user_id))
            strategy_id = int(cur.fetchone()[0])
            cur.execute("SELECT setup_id FROM strategies WHERE id=%s AND user_id=%s",
                        (strategy_id, user_id))
            setup_id = int(cur.fetchone()[0])
            for table, row_id in (("setups", setup_id), ("strategies", strategy_id),
                                  ("bot_configs", bot_id)):
                cur.execute(f"UPDATE {table} SET market_id=%s WHERE id=%s AND user_id=%s",
                            (market_id, row_id, user_id))
            cur.execute("""
                INSERT INTO user_indicator_configs
                  (user_id,indicator,category,symbol,asset_class,priority,enabled,
                   created_at,updated_at,market_id)
                SELECT user_id,indicator,category,symbol,asset_class,priority,enabled,
                       created_at,updated_at,%s
                FROM user_indicator_configs
                WHERE user_id=%s AND symbol='ETH' AND market_id IS NULL
                  AND category IN ('market','technical')
            """, (market_id, user_id))
            for table, name in (("technical_indicators", "indicator"),
                                ("market_data_indicators", "name")):
                if missing_technical and table == "technical_indicators":
                    continue
                value_sql = ("CASE WHEN name='price' THEN 25000 ELSE value END"
                             if table == "market_data_indicators" else "value")
                cur.execute(f"""
                    INSERT INTO {table}
                      (user_id,symbol,{name},value,timestamp,source_observed_at,market_id)
                    SELECT user_id,symbol,{name},{value_sql},timestamp,source_observed_at,%s
                    FROM {table} WHERE user_id=%s AND symbol='ETH' AND market_id IS NULL
                """, (market_id, user_id))
            cur.execute("""
                INSERT INTO market_data
                  (symbol,price,timestamp,source_observed_at,quote_currency,market_id)
                SELECT symbol,price / 2,timestamp,source_observed_at,%s,%s
                FROM market_data WHERE symbol='ETH' AND market_id IS NULL
                  AND source_observed_at IS NOT NULL
                ORDER BY source_observed_at DESC LIMIT 5
            """, (quote, market_id))
            for days_ago in range(1, 5):
                cur.execute("""
                    INSERT INTO market_data
                      (symbol,price,timestamp,source_observed_at,quote_currency,market_id)
                    VALUES ('ETH',%s,NOW()-(%s*INTERVAL '1 day')-INTERVAL '1 hour',
                            NOW()-(%s*INTERVAL '1 day')-INTERVAL '1 hour',%s,%s)
                """, (25000 - 125 * days_ago, days_ago, days_ago, quote, market_id))
            cur.execute("""
                INSERT INTO market_data
                  (symbol,price,timestamp,source_observed_at,quote_currency,market_id)
                VALUES ('ETH',25000,NOW()-INTERVAL '5 minutes',
                        NOW()-INTERVAL '5 minutes',%s,%s)
            """, (quote, market_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # Keep a competing base-asset score in the same owner's account.
    build_daily_scores_for_user(user_id, ["ETH"])
    pair_score = build_daily_scores_for_market(user_id, market_id)
    if not missing_technical and any(value is None for value in pair_score["scores"].values()):
        raise AssertionError(f"exact_pair_score_missing:{pair_score}")
    if missing_technical and pair_score["scores"].get("technical_score") is not None:
        raise AssertionError(f"exact_pair_borrowed_base_technical:{pair_score}")
    task = celery_app.send_task(
        "backend.celery_task.trading_bot_task.run_daily_trading_bot",
        args=[user_id, report_date], queue=QUEUE,
    )
    result = task.get(timeout=45)
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT action, amount_eur, market_id, scores_json
                FROM bot_decisions WHERE user_id=%s AND bot_id=%s
                  AND decision_date=%s
            """, (user_id, bot_id, report_date))
            decision = cur.fetchone()
            cur.execute("""
                SELECT status,market_id,quote_amount_eur
                FROM bot_orders WHERE user_id=%s AND bot_id=%s
            """, (user_id, bot_id))
            orders = cur.fetchall()
            cur.execute("""
                SELECT market_id,qty_delta,cash_delta_eur FROM bot_ledger
                WHERE user_id=%s AND bot_id=%s AND entry_type='execute'
            """, (user_id, bot_id))
            fills = cur.fetchall()
            cur.execute("""
                SELECT evidence_json FROM portfolio_value_snapshots_v2
                WHERE user_id=%s AND environment='paper'
            """, (user_id,))
            snapshots = [row[0] for row in cur.fetchall()]
        if missing_technical or stale_fx:
            if (not isinstance(result, dict) or not result.get("ok")
                    or not decision or decision[0] != "hold" or float(decision[1]) != 0
                    or decision[2] != market_id or orders or fills):
                raise AssertionError("exact_pair_safety_hold_failed:" + json.dumps({
                    "result": result, "decision": decision,
                    "orders": orders, "fills": fills,
                }, default=str))
            print(json.dumps({"result": "PASS", "market_id": market_id,
                              "pair": f"ETH/{quote}", "decision": "hold",
                              "reason": ("missing_pair_technical_score" if missing_technical
                                         else "stale_quote_fx"), "orders": 0}))
            return
        expected_qty = 50 / (25000 * (0.92 if quote == "USDT" else 1))
        if (not isinstance(result, dict) or not result.get("ok")
                or not decision or decision[0] != "buy" or float(decision[1]) != 50
                or decision[2] != market_id or not orders
                or orders[0] != ("filled", market_id, 50)
                or len(fills) != 1 or fills[0][0] != market_id
                or float(fills[0][2]) != -50
                or not math.isclose(float(fills[0][1]), expected_qty, abs_tol=1e-8)
                or not snapshots
                or not all(any(position.get("market_id") == market_id
                                   and position.get("quote_currency") == quote
                                   for position in snap["positions"])
                           for snap in snapshots)):
            raise AssertionError("exact_pair_paper_chain_failed:" + json.dumps({
                "result": result, "decision": decision, "orders": orders,
                "fills": fills, "snapshots": snapshots,
            }, default=str))
        # Exercise the protected verifier against this local worker-driven fill.
        verify_protected_pair(user_id, bot_id, report_date, market_id, quote,
                              25000 * (0.92 if quote == "USDT" else 1))
        print(json.dumps({"result": "PASS", "market_id": market_id,
                          "pair": f"ETH/{quote}", "decision": decision[0],
                          "amount_eur": float(decision[1]), "orders": len(orders),
                          "fills": len(fills), "snapshots": len(snapshots)}))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
