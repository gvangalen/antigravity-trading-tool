"""Protected, owner-isolated Score 2.0 match and Paper decision probes.

The QA workflow alone enables this module. It never creates exchange keys or
changes shared market data, and all public results omit fixture identifiers.
"""

from __future__ import annotations

import os
from datetime import date

from backend.scripts import probe_protected_score2_stale_paper as fixture


def _set_case(user_id: int, bot_id: int, *, outside: bool) -> None:
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE setups AS s
                   SET min_benchmark_score=0,max_benchmark_score=%s
                   FROM strategies AS st, bot_configs AS b
                   WHERE b.id=%s AND b.user_id=%s AND st.id=b.strategy_id
                     AND s.id=st.setup_id AND s.user_id=%s""",
                (10 if outside else 100, bot_id, user_id, user_id),
            )
            if cur.rowcount != 1:
                raise RuntimeError("score2_match_fixture_setup_missing")
            cur.execute(
                """UPDATE bot_configs SET mode=%s
                   WHERE id=%s AND user_id=%s AND is_live=FALSE""",
                ("auto", bot_id, user_id),
            )
            if cur.rowcount != 1:
                raise RuntimeError("score2_match_fixture_bot_missing")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _verify(user_id: int, bot_id: int, report_date: str, *, outside: bool) -> dict:
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT market_score,macro_score,technical_score
                   FROM daily_scores WHERE user_id=%s AND symbol='ETH' AND report_date=%s""",
                (user_id, report_date),
            )
            components = cur.fetchone()
            cur.execute(
                """SELECT action,amount_eur,status,scores_json
                   FROM bot_decisions WHERE user_id=%s AND bot_id=%s AND decision_date=%s""",
                (user_id, bot_id, report_date),
            )
            decision = cur.fetchone()
            cur.execute(
                """SELECT status,execution_environment FROM bot_orders
                   WHERE user_id=%s AND bot_id=%s""", (user_id, bot_id),
            )
            orders = cur.fetchall()
            cur.execute(
                """SELECT entry_type,cash_delta_eur FROM bot_ledger
                   WHERE user_id=%s AND bot_id=%s ORDER BY id""", (user_id, bot_id),
            )
            ledger = cur.fetchall()
            cur.execute(
                """SELECT p.cash_eur,p.position_qty,b.is_active,b.is_live,b.mode
                   FROM bot_portfolios p JOIN bot_configs b ON b.id=p.bot_id
                   WHERE p.user_id=%s AND p.bot_id=%s AND p.symbol='ETH'""",
                (user_id, bot_id),
            )
            state = cur.fetchone()
            cur.execute("SELECT COUNT(*) FROM exchange_keys WHERE user_id=%s", (user_id,))
            keys = cur.fetchone()[0]
        if not components or any(value is None for value in components):
            raise RuntimeError("score2_match_components_missing")
        if not decision or not isinstance(decision[3], dict):
            raise RuntimeError("score2_match_decision_missing")
        match = (decision[3].get("setup_match") or {}).get("status")
        if keys or not state or state[3] is not False:
            raise RuntimeError("score2_match_fixture_safety_breach")
        if outside:
            if match != "outside_conditions":
                raise RuntimeError("score2_outside_match_wrong")
            if (decision[0] != "hold" or float(decision[1] or 0) != 0
                    or orders or ledger or float(state[0]) != 100
                    or float(state[1]) != 0 or state[2] is not True or state[4] != "auto"):
                raise RuntimeError("score2_outside_paper_side_effect")
            return {"result": "PASS", "setup_match": "outside_conditions",
                    "decision": "hold", "orders": 0, "paper_cash_unchanged": True,
                    "bot_active": True, "live_bot": False}
        if match != "matches":
            raise RuntimeError("score2_positive_match_wrong")
        if decision[0] != "buy" or decision[2] != "executed":
            raise RuntimeError("score2_positive_decision_not_executed")
        if len(orders) != 1 or orders[0] != ("filled", "paper"):
            raise RuntimeError("score2_positive_order_not_paper_filled")
        if (len(ledger) != 1 or ledger[0][0] != "execute"
                or float(ledger[0][1]) >= 0 or not 0 < float(state[0]) < 100
                or float(state[1]) <= 0 or state[4] != "auto"):
            raise RuntimeError("score2_positive_portfolio_not_reconciled")
        return {"result": "PASS", "setup_match": "matches", "decision": "buy",
                "order_status": "filled", "environment": "paper",
                "execution_ledger_entries": 1, "live_bot": False}
    finally:
        conn.close()


def run(namespace: str, *, outside: bool) -> dict:
    if os.getenv("FINN_QA_ALLOW_SCORE2_MATCH_FIXTURE") != "1":
        raise RuntimeError("score2_match_fixture_not_authorized")
    bound = fixture._require_protected_run(namespace)
    user_id = bot_id = None
    passed = False
    try:
        user_id, bot_id, report_date = fixture._seed(namespace, bound)
        _set_case(user_id, bot_id, outside=outside)
        from backend.celery_task.store_daily_scores_task import build_daily_scores_for_user
        from backend.engine.trading_bot_execution import run_trading_bot_execution

        build_daily_scores_for_user(user_id, ["ETH"])
        result = run_trading_bot_execution(
            user_id, report_date=date.fromisoformat(report_date),
            bot_id=bot_id, paper_only=True,
        )
        if not result.get("ok") or len(result.get("decisions") or []) != 1:
            raise RuntimeError("score2_match_paper_assessment_failed")
        output = _verify(user_id, bot_id, report_date, outside=outside)
        passed = True
        return output
    finally:
        if user_id is not None and bot_id is not None:
            if passed:
                fixture._cleanup(namespace, user_id, bot_id)
            else:
                fixture._quarantine(namespace, user_id, bot_id)
