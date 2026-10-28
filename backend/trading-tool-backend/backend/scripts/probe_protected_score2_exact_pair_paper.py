"""Protected exact-pair Score 2.0 to Paper fill probe.

The fixture is an inactive, uncredentialed owner. It reads existing Binance
pair prices and FX, writes only owner-scoped evidence, and never sends Live
orders or changes shared market sources.
"""

from __future__ import annotations

from datetime import date
from math import isclose
import os

from backend.scripts import probe_protected_score2_stale_paper as fixture


def _source(quote: str) -> tuple[int, float]:
    from backend.engine.trading_bot_execution import _get_live_price

    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id FROM trading_markets
                   WHERE asset_symbol='ETH' AND quote_currency=%s
                     AND venue='BINANCE' AND is_active=TRUE""",
                (quote,),
            )
            rows = cur.fetchall()
        if len(rows) != 1:
            raise RuntimeError("exact_pair_market_unavailable")
        market_id = int(rows[0][0])
        eur_price = _get_live_price(conn, "ETH", market_id=market_id,
                                    paper_execution=True)
        if eur_price is None or float(eur_price) <= 0:
            raise RuntimeError("exact_pair_verified_price_unavailable")
        return market_id, float(eur_price)
    finally:
        conn.close()


def _bind_pair(user_id: int, bot_id: int, market_id: int) -> None:
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT strategy_id FROM bot_configs WHERE id=%s AND user_id=%s AND is_live=FALSE",
                        (bot_id, user_id))
            row = cur.fetchone()
            if not row:
                raise RuntimeError("exact_pair_fixture_bot_missing")
            strategy_id = int(row[0])
            cur.execute("SELECT setup_id FROM strategies WHERE id=%s AND user_id=%s",
                        (strategy_id, user_id))
            row = cur.fetchone()
            if not row:
                raise RuntimeError("exact_pair_fixture_strategy_missing")
            setup_id = int(row[0])
            for table, row_id in (("setups", setup_id), ("strategies", strategy_id),
                                  ("bot_configs", bot_id)):
                cur.execute(f"UPDATE {table} SET market_id=%s WHERE id=%s AND user_id=%s",
                            (market_id, row_id, user_id))
                if cur.rowcount != 1:
                    raise RuntimeError("exact_pair_fixture_bind_failed")
            cur.execute("""UPDATE bot_configs SET mode='auto'
                           WHERE id=%s AND user_id=%s AND is_live=FALSE""",
                        (bot_id, user_id))
            cur.execute("""INSERT INTO user_indicator_configs
                (user_id,indicator,category,symbol,asset_class,priority,enabled,
                 created_at,updated_at,market_id)
                SELECT user_id,indicator,category,symbol,asset_class,priority,enabled,
                       created_at,updated_at,%s
                FROM user_indicator_configs
                WHERE user_id=%s AND symbol='ETH' AND market_id IS NULL
                  AND category IN ('market','technical')""", (market_id, user_id))
            for table, name_column in (("market_data_indicators", "name"),
                                       ("technical_indicators", "indicator")):
                # Deliberately distinguish pair evidence from the base ETH row.
                value = "-10" if table == "market_data_indicators" else "value"
                cur.execute(f"""INSERT INTO {table}
                    (user_id,symbol,{name_column},value,timestamp,source_observed_at,market_id)
                    SELECT user_id,symbol,{name_column},{value},timestamp,
                           source_observed_at,%s
                    FROM {table}
                    WHERE user_id=%s AND symbol='ETH' AND market_id IS NULL""",
                            (market_id, user_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _verify(user_id: int, bot_id: int, report_date: str,
            market_id: int, quote: str, eur_price: float) -> dict:
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT market_score,macro_score,technical_score
                           FROM daily_scores WHERE user_id=%s AND symbol='ETH'
                             AND market_id=%s AND report_date=%s""",
                        (user_id, market_id, report_date))
            scores = cur.fetchone()
            cur.execute("""SELECT action,amount_eur,market_id,scores_json,status
                           FROM bot_decisions WHERE user_id=%s AND bot_id=%s
                             AND decision_date=%s""", (user_id, bot_id, report_date))
            decision = cur.fetchone()
            cur.execute("""SELECT status,execution_environment,market_id,
                                  executed_price_eur,executed_qty,quote_amount_eur
                           FROM bot_orders WHERE user_id=%s AND bot_id=%s""",
                        (user_id, bot_id))
            orders = cur.fetchall()
            cur.execute("""SELECT market_id,cash_delta_eur,qty_delta FROM bot_ledger
                           WHERE user_id=%s AND bot_id=%s AND entry_type='execute'""",
                        (user_id, bot_id))
            fills = cur.fetchall()
            cur.execute("""SELECT p.cash_eur,p.position_qty,b.is_live,b.is_active
                           FROM bot_portfolios p JOIN bot_configs b ON b.id=p.bot_id
                           WHERE p.user_id=%s AND p.bot_id=%s""", (user_id, bot_id))
            portfolio = cur.fetchone()
            cur.execute("SELECT COUNT(*) FROM exchange_keys WHERE user_id=%s", (user_id,))
            keys = int(cur.fetchone()[0])
        if not scores or any(score is None for score in scores):
            raise RuntimeError("exact_pair_score_incomplete")
        if (not decision or decision[0] != "buy" or decision[2] != market_id
                or decision[4] != "executed" or not isinstance(decision[3], dict)
                or (decision[3].get("setup_match") or {}).get("status") != "matches"):
            raise RuntimeError("exact_pair_decision_not_matched_buy")
        amount = float(decision[1])
        if len(orders) != 1:
            raise RuntimeError("exact_pair_paper_order_count_mismatch")
        order_status, environment, order_market_id, price, qty, spent = orders[0]
        if order_status != "filled" or environment != "paper":
            raise RuntimeError("exact_pair_paper_order_state_mismatch")
        if order_market_id != market_id:
            raise RuntimeError("exact_pair_paper_order_market_mismatch")
        if price is None or qty is None or spent is None:
            raise RuntimeError("exact_pair_paper_fill_missing")
        execution_price, execution_qty, actual_spend = float(price), float(qty), float(spent)
        # Paper execution rechecks the pair quote and may reprice after the
        # preflight. The approved EUR spend stays bounded while quantity is
        # rounded down to eight decimals. A modest source move is valid.
        if execution_price <= 0:
            raise RuntimeError("exact_pair_paper_fill_price_invalid")
        if not isclose(execution_price, eur_price, rel_tol=0.03):
            # The execution quote is re-read. A large move makes this one
            # fixture window inconclusive; it is not evidence of a bot bug.
            raise RuntimeError("exact_pair_probe_price_window_unstable")
        if (execution_qty <= 0 or actual_spend <= 0 or actual_spend > amount + 0.001
                or amount - actual_spend > 0.02
                or not isclose(execution_qty * execution_price, actual_spend, abs_tol=0.011)):
            raise RuntimeError("exact_pair_paper_fill_amount_mismatch")
        if len(fills) != 1 or fills[0][0] != market_id:
            raise RuntimeError("exact_pair_paper_ledger_count_or_market_mismatch")
        if (not isclose(float(fills[0][1]), -actual_spend, abs_tol=0.001)
                or not isclose(float(fills[0][2]), execution_qty, abs_tol=1e-8)):
            raise RuntimeError("exact_pair_paper_ledger_amount_mismatch")
        if (not portfolio or not isclose(float(portfolio[0]), 100 - actual_spend, abs_tol=0.01)
                or not isclose(float(portfolio[1]), execution_qty, abs_tol=1e-8)
                or portfolio[2] is not False or portfolio[3] is not True or keys):
            raise RuntimeError("exact_pair_paper_portfolio_or_safety_mismatch")
        return {"result": "PASS", "pair": f"ETH/{quote}",
                "score_components": "complete_synthetic_pair_fixture",
                "execution_path": "direct_paper_engine",
                "market_price_source": "existing_dated_pair_quote",
                "setup_match": "matches",
                "decision": "buy", "order_status": "filled", "environment": "paper",
                "execution_ledger_entries": 1, "live_bot": False}
    finally:
        conn.close()


def run(namespace: str, *, quote: str) -> dict:
    if os.getenv("FINN_QA_ALLOW_EXACT_PAIR_FIXTURE") != "1":
        raise RuntimeError("exact_pair_fixture_not_authorized")
    if quote not in {"EUR", "USDT"}:
        raise RuntimeError("exact_pair_quote_unsupported")
    bound = fixture._require_protected_run(namespace)
    market_id, eur_price = _source(quote)  # Read-only preflight before fixture writes.
    user_id = bot_id = None
    passed = False
    try:
        user_id, bot_id, report_date = fixture._seed(namespace, bound)
        _bind_pair(user_id, bot_id, market_id)
        from backend.celery_task.store_daily_scores_task import build_daily_scores_for_market
        from backend.engine.trading_bot_execution import run_trading_bot_execution

        score = build_daily_scores_for_market(user_id, market_id)
        if any(value is None for value in score["scores"].values()):
            raise RuntimeError("exact_pair_fixture_score_incomplete")
        result = run_trading_bot_execution(
            user_id, report_date=date.fromisoformat(report_date),
            bot_id=bot_id, paper_only=True,
        )
        if not result.get("ok") or len(result.get("decisions") or []) != 1:
            raise RuntimeError("exact_pair_paper_assessment_failed")
        output = _verify(user_id, bot_id, report_date, market_id, quote, eur_price)
        passed = True
        return output
    finally:
        if user_id is not None and bot_id is not None:
            if passed:
                fixture._cleanup(namespace, user_id, bot_id)
            else:
                fixture._quarantine(namespace, user_id, bot_id)
