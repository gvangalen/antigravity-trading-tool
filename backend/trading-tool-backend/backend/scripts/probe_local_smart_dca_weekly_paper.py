#!/usr/bin/env python3
"""Isolated worker proof of a weekly benchmark Smart DCA Paper purchase."""

import json
from datetime import date, timedelta

from backend.scripts.probe_local_score2_positive_paper import (
    QUEUE, _assert_local_only, _seed_fixture, _verify,
)


def main() -> None:
    _assert_local_only()
    from backend.celery_task.celery_app import celery_app
    from backend.celery_task.store_daily_scores_task import build_daily_scores_for_user
    from backend.domain.finn_dca_plan_contract import dca_execution_period
    from backend.utils.db import get_db_connection

    user_id, bot_id, report_date_text = _seed_fixture(
        frequency="weekly", trigger_mode="benchmark",
    )
    report_date = date.fromisoformat(report_date_text)
    next_date = report_date + timedelta(days=1)
    first_period = dca_execution_period({"dca_frequency": "weekly"}, report_date)
    if not first_period[0] <= next_date < first_period[1]:
        raise AssertionError("local_probe_requires_two_dates_in_same_week")

    build_daily_scores_for_user(user_id, ["ETH"])
    first = celery_app.send_task(
        "backend.celery_task.trading_bot_task.run_daily_trading_bot",
        args=[user_id, report_date_text], queue=QUEUE,
    ).get(timeout=30)
    if not first.get("ok") or first.get("decisions") != 1:
        raise AssertionError(f"first_weekly_assessment_failed:{first}")
    first_evidence = _verify(user_id, bot_id, report_date_text)

    # A second daily assessment in the same week has a fresh score row, so
    # the period guard rather than missing score data must prevent another buy.
    conn = get_db_connection()
    if conn is None:
        raise RuntimeError("local_database_unavailable")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE daily_scores SET report_date=%s
                   WHERE user_id=%s AND symbol='ETH' AND report_date=%s
                   RETURNING id""",
                (next_date, user_id, report_date),
            )
            if not cur.fetchone():
                raise AssertionError("next_day_score_unavailable")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    second = celery_app.send_task(
        "backend.celery_task.trading_bot_task.run_daily_trading_bot",
        args=[user_id, next_date.isoformat()], queue=QUEUE,
    ).get(timeout=30)
    if not second.get("ok") or second.get("decisions") != 0:
        raise AssertionError(f"second_weekly_assessment_not_blocked:{second}")

    conn = get_db_connection()
    if conn is None:
        raise RuntimeError("local_database_unavailable")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM bot_orders WHERE user_id=%s AND bot_id=%s", (user_id, bot_id))
            order_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM bot_decisions WHERE user_id=%s AND bot_id=%s AND action='buy'", (user_id, bot_id))
            buy_count = cur.fetchone()[0]
            cur.execute("SELECT cash_eur,position_qty FROM bot_portfolios WHERE user_id=%s AND bot_id=%s", (user_id, bot_id))
            cash, qty = cur.fetchone()
            cur.execute("SELECT COUNT(*) FROM bot_ledger WHERE user_id=%s AND bot_id=%s AND entry_type='execute'", (user_id, bot_id))
            execution_count = cur.fetchone()[0]
        if not (order_count == buy_count == execution_count == 1
                and float(cash) == first_evidence["paper_cash_eur"]
                and float(qty) == first_evidence["position_qty"]):
            raise AssertionError("weekly_paper_state_changed_after_second_assessment")
        print(json.dumps({
            "result": "PASS", "scope": "isolated_local_postgresql_celery",
            "trigger_mode": "benchmark", "frequency": "weekly",
            "first_assessment": first_evidence["decision"],
            "second_assessment_decisions": second["decisions"],
            "orders": order_count, "executions": execution_count,
            "paper_cash_eur": float(cash), "position_qty": float(qty),
            "bot_live": first_evidence["bot_live"],
            "exchange_keys": first_evidence["exchange_keys"],
        }, sort_keys=True))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
