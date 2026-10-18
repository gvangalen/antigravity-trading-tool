#!/usr/bin/env python3
"""Local Score 2.0 outside-condition Paper probe; never calls a broker."""

import json

from backend.scripts.probe_local_score2_positive_paper import (
    QUEUE, _assert_local_only, _seed_fixture,
)
from backend.utils.db import get_db_connection


def main() -> None:
    _assert_local_only()
    from backend.celery_task.celery_app import celery_app
    from backend.celery_task.store_daily_scores_task import build_daily_scores_for_user

    user_id, bot_id, report_date = _seed_fixture()
    conn = get_db_connection()
    if conn is None:
        raise RuntimeError("local_database_unavailable")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE setups AS s SET min_benchmark_score=0,max_benchmark_score=10
                   FROM strategies AS st,bot_configs AS b
                   WHERE b.id=%s AND b.user_id=%s AND st.id=b.strategy_id
                     AND s.id=st.setup_id AND s.user_id=%s""",
                (bot_id, user_id, user_id),
            )
            if cur.rowcount != 1:
                raise RuntimeError("local_setup_missing")
        conn.commit()
    finally:
        conn.close()

    build_daily_scores_for_user(user_id, ["ETH"])
    task = celery_app.send_task(
        "backend.celery_task.trading_bot_task.run_daily_trading_bot",
        args=[user_id, report_date], queue=QUEUE,
    )
    result = task.get(timeout=30)
    if not isinstance(result, dict) or not result.get("ok") or result.get("decisions") != 1:
        raise RuntimeError("outside_paper_task_failed")

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT market_score,macro_score,technical_score
                   FROM daily_scores WHERE user_id=%s AND symbol='ETH'
                     AND report_date=%s""",
                (user_id, report_date),
            )
            components = cur.fetchone()
            cur.execute(
                """SELECT d.action,d.amount_eur,d.scores_json->'setup_match'
                   FROM bot_decisions d WHERE d.user_id=%s AND d.bot_id=%s
                     AND d.decision_date=%s""",
                (user_id, bot_id, report_date),
            )
            decision = cur.fetchone()
            cur.execute("SELECT count(*) FROM bot_orders WHERE user_id=%s AND bot_id=%s", (user_id, bot_id))
            orders = cur.fetchone()[0]
            cur.execute(
                """SELECT p.cash_eur,p.position_qty,b.is_active,b.is_live
                   FROM bot_portfolios p JOIN bot_configs b ON b.id=p.bot_id
                   WHERE p.user_id=%s AND p.bot_id=%s AND p.symbol='ETH'""",
                (user_id, bot_id),
            )
            portfolio = cur.fetchone()
            cur.execute(
                """SELECT entry_type FROM bot_ledger
                   WHERE user_id=%s AND bot_id=%s ORDER BY id""",
                (user_id, bot_id),
            )
            ledger = cur.fetchall()
            cur.execute("SELECT count(*) FROM exchange_keys WHERE user_id=%s", (user_id,))
            keys = cur.fetchone()[0]
        if (not components or any(score is None for score in components)
                or not decision or decision[0] != "hold" or float(decision[1]) != 0
                or (decision[2] or {}).get("status") != "outside_conditions"
                or orders != 0 or portfolio is None or float(portfolio[0]) != 100
                or float(portfolio[1]) != 0 or portfolio[2] is not True
                or portfolio[3] is not False or ledger != [("paper_initial_funding",)]
                or keys != 0):
            raise RuntimeError("outside_paper_contract_failed")
        print(json.dumps({
            "result": "PASS", "setup_match": "outside_conditions",
            "fresh_components": ["market", "macro", "technical"],
            "decision": "hold", "amount_eur": 0, "orders": 0,
            "paper_cash_eur": 100, "bot_active": True, "bot_live": False,
        }, sort_keys=True))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
