"""Owner-isolated weekly Smart DCA Paper fill and period-reservation probe."""

from __future__ import annotations

import json
import math
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from backend.scripts import probe_protected_score2_stale_paper as fixture


START_CASH_EUR = 1000.0
BASE_AMOUNT_EUR = 200.0


def _require_protected_run(namespace: str) -> int:
    if (os.getenv("FINN_QA_ALLOW_WEEKLY_SMART_DCA_FIXTURE") != "1"
            or os.getenv("FINN_QA_ALLOW_FIXTURE_ACTIONS") != "1"
            or os.getenv("FINN_QA_ALLOW_FIXTURE_EXECUTION") != "1"):
        raise RuntimeError("weekly_smart_dca_fixture_not_authorized")
    return fixture._require_protected_run(namespace)


def _source() -> int:
    from backend.engine.trading_bot_execution import _get_live_price

    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id FROM trading_markets
                   WHERE asset_symbol='BTC' AND quote_currency='USDT'
                     AND venue='BINANCE' AND is_active=TRUE"""
            )
            markets = cur.fetchall()
        if len(markets) != 1:
            raise RuntimeError("weekly_smart_dca_market_unavailable")
        market_id = int(markets[0][0])
        if not (_get_live_price(conn, "BTC", market_id=market_id, paper_execution=True) or 0) > 0:
            raise RuntimeError("weekly_smart_dca_paper_quote_unavailable")
        return market_id
    finally:
        conn.close()


def _configure(user_id: int, bot_id: int, market_id: int) -> None:
    from backend.domain.finn_dca_plan_contract import split_confirmed_dca_plan

    _, strategy = split_confirmed_dca_plan({
        "setup_type": "dca", "name": "QA weekly Smart DCA",
        "dca_frequency": "weekly", "dca_trigger_mode": "benchmark",
        "dca_amount_mode": "score_bands", "base_amount": BASE_AMOUNT_EUR,
        "score_source": "benchmark_score", "low_threshold": 26,
        "high_threshold": 76, "low_score_percent": 150,
        "mid_score_percent": 100, "high_score_percent": 50,
    })
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT b.strategy_id,s.setup_id,u.is_active,b.is_live
                   FROM bot_configs b JOIN strategies s ON s.id=b.strategy_id AND s.user_id=b.user_id
                   JOIN users u ON u.id=b.user_id
                   WHERE b.id=%s AND b.user_id=%s FOR UPDATE OF b""",
                (bot_id, user_id),
            )
            row = cur.fetchone()
            if not row or row[2] is not False or row[3] is not False:
                raise RuntimeError("weekly_smart_dca_fixture_owner_or_bot_unsafe")
            strategy_id, setup_id = int(row[0]), int(row[1])
            cur.execute(
                """UPDATE setups SET symbol='BTC',market_id=%s,dca_frequency='weekly',
                   dca_trigger_mode='benchmark',dca_day=NULL,dca_month_day=NULL,
                   min_benchmark_score=0,max_benchmark_score=100
                   WHERE id=%s AND user_id=%s AND setup_type='dca'""",
                (market_id, setup_id, user_id),
            )
            if cur.rowcount != 1:
                raise RuntimeError("weekly_smart_dca_setup_missing")
            cur.execute(
                """UPDATE strategies SET symbol='BTC',market_id=%s,
                   execution_mode='custom',base_amount=%s,decision_curve=%s::jsonb,
                   data=%s::jsonb WHERE id=%s AND user_id=%s AND setup_id=%s""",
                (market_id, strategy["base_amount"], json.dumps(strategy["decision_curve"]),
                 json.dumps({"dca_amount_semantics": "planned_exact"}),
                 strategy_id, user_id, setup_id),
            )
            if cur.rowcount != 1:
                raise RuntimeError("weekly_smart_dca_strategy_missing")
            cur.execute(
                """UPDATE bot_configs SET symbol='BTC',market_id=%s,cadence='weekly',
                   mode='auto',budget_total_eur=%s,budget_daily_limit_eur=300,
                   budget_min_order_eur=1,budget_max_order_eur=300,
                   max_asset_exposure_pct=100,paper_initial_cash_eur=%s
                   WHERE id=%s AND user_id=%s AND is_live=FALSE""",
                (market_id, START_CASH_EUR, START_CASH_EUR, bot_id, user_id),
            )
            if cur.rowcount != 1:
                raise RuntimeError("weekly_smart_dca_bot_missing")
            cur.execute(
                """UPDATE bot_portfolios SET symbol='BTC',cash_eur=%s
                   WHERE bot_id=%s AND user_id=%s AND position_qty=0""",
                (START_CASH_EUR, bot_id, user_id),
            )
            if cur.rowcount != 1:
                raise RuntimeError("weekly_smart_dca_portfolio_missing")
            for table in ("user_indicator_configs", "macro_data",
                          "technical_indicators", "market_data_indicators"):
                cur.execute(f"UPDATE {table} SET symbol='BTC' WHERE user_id=%s AND symbol='ETH'", (user_id,))
            cur.execute(
                """INSERT INTO user_indicator_configs
                   (user_id,indicator,category,symbol,asset_class,priority,enabled,
                    created_at,updated_at,market_id)
                   SELECT user_id,indicator,category,symbol,asset_class,priority,enabled,
                          created_at,updated_at,%s FROM user_indicator_configs
                   WHERE user_id=%s AND symbol='BTC' AND market_id IS NULL
                     AND category IN ('market','technical')""",
                (market_id, user_id),
            )
            for table, column in (("market_data_indicators", "name"),
                                  ("technical_indicators", "indicator")):
                cur.execute(
                    f"""INSERT INTO {table}
                       (user_id,symbol,{column},value,timestamp,source_observed_at,market_id)
                       SELECT user_id,symbol,{column},value,timestamp,source_observed_at,%s
                       FROM {table} WHERE user_id=%s AND symbol='BTC' AND market_id IS NULL""",
                    (market_id, user_id),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _next_same_week(today: date) -> date:
    if today.weekday() == 6:
        raise RuntimeError("weekly_smart_dca_date_boundary_unavailable")
    return today + timedelta(days=1)


def _copy_score_for_second_day(user_id: int, market_id: int, first: date, second: date) -> None:
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO daily_scores
                   (report_date,user_id,symbol,market_id,macro_score,technical_score,
                    market_score,setup_score,macro_interpretation,technical_interpretation,
                    market_interpretation,macro_top_contributors,technical_top_contributors,
                    market_top_contributors,calculated_at,indicator_evidence)
                   SELECT %s,user_id,symbol,market_id,macro_score,technical_score,
                          market_score,setup_score,macro_interpretation,technical_interpretation,
                          market_interpretation,macro_top_contributors,technical_top_contributors,
                          market_top_contributors,calculated_at,indicator_evidence
                   FROM daily_scores WHERE user_id=%s AND market_id=%s AND report_date=%s""",
                (second, user_id, market_id, first),
            )
            if cur.rowcount != 1:
                raise RuntimeError("weekly_smart_dca_second_score_copy_failed")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _verify(user_id: int, bot_id: int, market_id: int, first: date, second: date) -> dict:
    from backend.domain.finn_dca_plan_contract import benchmark_score

    if first == second or first.isocalendar()[:2] != second.isocalendar()[:2]:
        raise RuntimeError("weekly_smart_dca_period_probe_invalid")
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT d.decision_date,d.action,d.amount_eur,d.status,d.scores_json
                   FROM bot_decisions d WHERE d.user_id=%s AND d.bot_id=%s
                   ORDER BY d.id""", (user_id, bot_id),
            )
            decisions = cur.fetchall()
            cur.execute(
                """SELECT o.status,o.execution_environment,o.side,o.market_id,
                          o.quote_amount_eur,e.status,e.filled_qty
                   FROM bot_orders o JOIN bot_executions e
                     ON e.bot_order_id=o.id AND e.user_id=o.user_id
                   WHERE o.user_id=%s AND o.bot_id=%s""", (user_id, bot_id),
            )
            orders = cur.fetchall()
            cur.execute(
                """SELECT entry_type,cash_delta_eur,qty_delta FROM bot_ledger
                   WHERE user_id=%s AND bot_id=%s ORDER BY id""", (user_id, bot_id),
            )
            ledger = cur.fetchall()
            cur.execute(
                """SELECT p.cash_eur,p.position_qty,b.is_live,b.is_active,b.mode,
                          s.dca_frequency,s.dca_trigger_mode,s.dca_day,
                          st.base_amount,st.decision_curve
                   FROM bot_portfolios p JOIN bot_configs b
                     ON b.id=p.bot_id AND b.user_id=p.user_id
                   JOIN strategies st ON st.id=b.strategy_id AND st.user_id=b.user_id
                   JOIN setups s ON s.id=st.setup_id AND s.user_id=st.user_id
                   WHERE p.user_id=%s AND p.bot_id=%s""", (user_id, bot_id),
            )
            state = cur.fetchone()
            cur.execute("SELECT COUNT(*) FROM exchange_keys WHERE user_id=%s", (user_id,))
            keys = int(cur.fetchone()[0])
            cur.execute("SELECT is_active FROM users WHERE id=%s", (user_id,))
            owner = cur.fetchone()
            cur.execute(
                """SELECT market_score,macro_score,technical_score FROM daily_scores
                   WHERE user_id=%s AND market_id=%s AND report_date=%s""",
                (user_id, market_id, first),
            )
            components = cur.fetchone()
        if (len(decisions) != 1 or decisions[0][0] != first
                or decisions[0][1] != "buy" or decisions[0][3] != "executed"):
            raise RuntimeError("weekly_smart_dca_first_decision_not_executed")
        payload = decisions[0][4]
        policy = payload.get("dca_policy") if isinstance(payload, dict) else None
        if (not isinstance(policy, dict) or policy.get("score_source") != "benchmark_score"
                or policy.get("source_available") is not True or not components
                or any(score is None for score in components)):
            raise RuntimeError("weekly_smart_dca_benchmark_unverified")
        weights = policy.get("weights") or {}
        score = benchmark_score(
            dict(zip(("market_score", "macro_score", "technical_score"), components)),
            weights, {key: True for key in ("market_score", "macro_score", "technical_score")},
        )
        if score is None or not math.isclose(float(policy.get("source_score") or -1), score, abs_tol=0.05):
            raise RuntimeError("weekly_smart_dca_benchmark_mismatch")
        expected = BASE_AMOUNT_EUR * (1.5 if score < 26 else 1 if score < 76 else 0.5)
        if not math.isclose(float(decisions[0][2]), expected, abs_tol=0.01):
            raise RuntimeError("weekly_smart_dca_amount_mismatch")
        if (len(orders) != 1 or orders[0][:4] != ("filled", "paper", "buy", market_id)
                or orders[0][5] != "filled" or float(orders[0][6] or 0) <= 0):
            raise RuntimeError("weekly_smart_dca_order_not_paper_filled")
        spent = float(orders[0][4] or 0)
        if (spent <= 0 or spent > expected + 0.01 or len(ledger) != 1
                or ledger[0][0] != "execute"
                or not math.isclose(float(ledger[0][1]), -spent, abs_tol=0.01)
                or float(ledger[0][2] or 0) <= 0):
            raise RuntimeError("weekly_smart_dca_ledger_mismatch")
        if (not state or not math.isclose(float(state[0]), START_CASH_EUR - spent, abs_tol=0.01)
                or float(state[1] or 0) <= 0 or state[2] is not False
                or state[3] is not True or state[4] != "auto"
                or state[5:8] != ("weekly", "benchmark", None)
                or not math.isclose(float(state[8]), BASE_AMOUNT_EUR, abs_tol=0.01)
                or not isinstance(state[9], dict) or keys or owner != (False,)):
            raise RuntimeError("weekly_smart_dca_state_or_owner_mismatch")
        return {
            "result": "PASS", "pair": "BTC/USDT", "score_source": "benchmark_score",
            "score_components_complete": True, "source_score": score,
            "planned_amount_eur": expected, "paper_spent_eur": round(spent, 2),
            "first_decision": "buy_executed", "replay": "same_day_blocked",
            "second_day": "same_week_blocked",
            "decision_count": 1, "paper_order_count": 1,
            "filled_execution_count": 1, "ledger_entries": 1,
            "cash_after_eur": round(float(state[0]), 2),
            "exchange_keys": 0, "live_bot": False, "live_trading_calls": 0,
        }
    finally:
        conn.close()


def run(namespace: str) -> dict:
    bound_qa_owner = _require_protected_run(namespace)
    market_id = _source()
    user_id = bot_id = None
    output = None
    try:
        user_id, bot_id, report_date = fixture._seed(namespace, bound_qa_owner)
        _configure(user_id, bot_id, market_id)
        from backend.celery_task.store_daily_scores_task import build_daily_scores_for_market
        from backend.engine.trading_bot_execution import run_trading_bot_execution

        first = date.fromisoformat(report_date)
        local_today = datetime.now(ZoneInfo("Europe/Amsterdam")).date()
        if first != local_today:
            raise RuntimeError("weekly_smart_dca_date_boundary_unavailable")
        second = _next_same_week(first)
        result = build_daily_scores_for_market(user_id, market_id)
        if any(score is None for score in result["scores"].values()):
            raise RuntimeError("weekly_smart_dca_scores_incomplete")
        first_result = run_trading_bot_execution(
            user_id, report_date=first, bot_id=bot_id, paper_only=True,
        )
        if not first_result.get("ok") or len(first_result.get("decisions") or []) != 1:
            raise RuntimeError("weekly_smart_dca_first_assessment_failed")
        replay = run_trading_bot_execution(
            user_id, report_date=first, bot_id=bot_id, paper_only=True,
        )
        if (not replay.get("ok") or replay.get("decisions")
                or (replay.get("skip_reasons") or {}).get(bot_id) != "already_pending_or_executed"):
            raise RuntimeError("weekly_smart_dca_replay_not_blocked")
        _copy_score_for_second_day(user_id, market_id, first, second)
        second_result = run_trading_bot_execution(
            user_id, report_date=second, bot_id=bot_id, paper_only=True,
        )
        if (not second_result.get("ok") or second_result.get("decisions")
                or (second_result.get("skip_reasons") or {}).get(bot_id) != "already_pending_or_executed"):
            raise RuntimeError("weekly_smart_dca_second_assessment_not_blocked")
        output = _verify(user_id, bot_id, market_id, first, second)
    finally:
        if user_id is not None and bot_id is not None:
            fixture._quarantine(namespace, user_id, bot_id)
            fixture._cleanup(namespace, user_id, bot_id, require_safe_review_cleanup=True)
    return {**output, "cleanup_verified": True}
