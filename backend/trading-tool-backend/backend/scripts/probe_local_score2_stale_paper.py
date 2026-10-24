#!/usr/bin/env python3
"""Opt-in local Score 2.0 -> Smart DCA -> Celery -> Paper safety probe.

Requires the disposable local-finn PostgreSQL/Redis stack and a worker
consuming only ``local-finn-score2-paper``. Never connects to production.
"""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

QUEUE = "local-finn-score2-paper"


def _assert_local_only() -> None:
    expected = {
        "APP_ENV": "local_finn",
        "DB_HOST": "127.0.0.1",
        "DB_PORT": "55432",
        "DB_NAME": "finn_local",
        "CELERY_BROKER_URL": "redis://127.0.0.1:56379/0",
        "CELERY_RESULT_BACKEND": "redis://127.0.0.1:56379/1",
    }
    for key, value in expected.items():
        if os.getenv(key) != value:
            raise RuntimeError(f"local_only_environment_required:{key}")


def _seed_fixture() -> tuple[int, int, str]:
    from backend.domain.finn_dca_plan_contract import split_confirmed_dca_plan
    from backend.utils.db import get_db_connection

    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    fresh = now - timedelta(hours=1)
    stale = now - timedelta(days=30)
    email = f"score2-stale-paper-{uuid.uuid4().hex}@example.test"
    conn = get_db_connection()
    if conn is None:
        raise RuntimeError("local_database_unavailable")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT CURRENT_DATE")
            report_date = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO users (email,password_hash,ai_preferences) "
                "VALUES (%s,%s,%s::jsonb) RETURNING id",
                (email, "local-fixture-no-login", "{}"),
            )
            user_id = int(cur.fetchone()[0])
            cur.execute(
                """INSERT INTO setups (
                    user_id,name,symbol,timeframe,setup_type,dca_frequency,
                    min_benchmark_score,
                    min_macro_score,min_technical_score,min_market_score,
                    created_at,last_validated)
                   VALUES (%s,'Local stale Smart DCA','ETH','1D','dca','daily',
                           0,0,0,0,%s,%s) RETURNING id""",
                (user_id, now, now),
            )
            setup_id = int(cur.fetchone()[0])
            _, strategy = split_confirmed_dca_plan({
                "setup_type": "dca", "name": "Local stale Smart DCA",
                "base_amount": 10, "dca_amount_mode": "score_bands",
                "score_source": "benchmark_score", "low_threshold": 40,
                "high_threshold": 70, "low_score_percent": 50,
                "mid_score_percent": 100, "high_score_percent": 150,
            })
            cur.execute(
                """INSERT INTO strategies (
                    user_id,setup_id,name,symbol,timeframe,setup_type,
                    execution_mode,base_amount,decision_curve,data,created_at)
                   VALUES (%s,%s,%s,'ETH','1D','dca','custom',%s,
                           %s::jsonb,%s::jsonb,%s) RETURNING id""",
                (user_id, setup_id, strategy["name"], strategy["base_amount"],
                 json.dumps(strategy["decision_curve"]),
                 json.dumps({"dca_amount_semantics": "planned_exact"}), now),
            )
            strategy_id = int(cur.fetchone()[0])
            cur.execute(
                """INSERT INTO bot_configs (
                    user_id,strategy_id,cadence,symbol,name,mode,is_live,is_active,
                    risk_profile,budget_total_eur,budget_daily_limit_eur,
                    budget_min_order_eur,budget_max_order_eur,
                    max_asset_exposure_pct,base_currency,paper_initial_cash_eur,
                    created_at,updated_at)
                   VALUES (%s,%s,'daily','ETH','Local stale Smart Paper',
                           'auto',FALSE,TRUE,'balanced',100,100,1,20,100,
                           'EUR',100,%s,%s) RETURNING id""",
                (user_id, strategy_id, now, now),
            )
            bot_id = int(cur.fetchone()[0])
            cur.execute(
                """INSERT INTO bot_portfolios (
                    bot_id,user_id,symbol,cash_eur,position_qty,
                    invested_eur,realized_pnl_eur)
                   VALUES (%s,%s,'ETH',100,0,0,0)""",
                (bot_id, user_id),
            )
            for category, name, value, observed_at, table, name_column in (
                ("macro", "dxy", 102.2, fresh, "macro_data", "name"),
                ("technical", "rsi", 55, stale, "technical_indicators", "indicator"),
                ("market", "price", 2040, fresh, "market_data_indicators", "name"),
            ):
                cur.execute(
                    """INSERT INTO user_indicator_configs (
                        user_id,indicator,category,symbol,asset_class,
                        priority,enabled,created_at,updated_at)
                       VALUES (%s,%s,%s,'ETH','crypto',1,TRUE,%s,%s)""",
                    (user_id, name, category,
                     now - timedelta(hours=3), now - timedelta(hours=3)),
                )
                cur.execute(
                    f"INSERT INTO {table} "
                    f"(user_id,symbol,{name_column},value,timestamp,source_observed_at) "
                    "VALUES (%s,'ETH',%s,%s,%s,%s)",
                    (user_id, name, value, observed_at, observed_at),
                )
            for days_ago, dxy, price in (
                (4, 101.5, 2000), (3, 101.7, 2010),
                (2, 101.9, 2020), (1, 102.1, 2030), (0, 102.2, 2040),
            ):
                observed = fresh - timedelta(days=days_ago)
                if days_ago:
                    cur.execute(
                        """INSERT INTO macro_data
                           (user_id,symbol,name,value,timestamp,source_observed_at)
                           VALUES (%s,'ETH','dxy',%s,%s,%s)""",
                        (user_id, dxy, observed, observed),
                    )
                cur.execute(
                    """INSERT INTO market_data
                       (symbol,price,timestamp,source_observed_at)
                       VALUES ('ETH',%s,%s,%s)""",
                    (price, observed, observed),
                )
        conn.commit()
        return user_id, bot_id, report_date.isoformat()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _verify(user_id: int, bot_id: int, report_date: str) -> dict:
    from backend.utils.db import get_db_connection

    conn = get_db_connection()
    if conn is None:
        raise RuntimeError("local_database_unavailable")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT macro_score,technical_score,market_score
                   FROM daily_scores WHERE user_id=%s AND symbol='ETH'
                     AND report_date=%s""",
                (user_id, report_date),
            )
            score_row = cur.fetchone()
            cur.execute(
                """SELECT action,amount_eur,scores_json
                   FROM bot_decisions WHERE user_id=%s AND bot_id=%s
                     AND decision_date=%s""",
                (user_id, bot_id, report_date),
            )
            decision = cur.fetchone()
            cur.execute(
                "SELECT count(*) FROM bot_orders WHERE user_id=%s AND bot_id=%s",
                (user_id, bot_id),
            )
            orders = cur.fetchone()[0]
            cur.execute(
                "SELECT count(*) FROM bot_ledger WHERE user_id=%s AND bot_id=%s",
                (user_id, bot_id),
            )
            ledger = cur.fetchone()[0]
            cur.execute(
                """SELECT p.cash_eur,b.is_active,b.is_live
                   FROM bot_portfolios p JOIN bot_configs b ON b.id=p.bot_id
                   WHERE p.user_id=%s AND p.bot_id=%s AND p.symbol='ETH'""",
                (user_id, bot_id),
            )
            cash, active, live = cur.fetchone()
            cur.execute(
                """SELECT bucket FROM bot_portfolio_snapshots
                   WHERE user_id=%s AND bot_id=%s""",
                (user_id, bot_id),
            )
            buckets = {row[0] for row in cur.fetchall()}
        if not score_row or score_row[0] is None or score_row[1] is not None or score_row[2] is None:
            raise AssertionError(f"unexpected_score_components:{score_row}")
        if not decision:
            raise AssertionError("paper_decision_missing")
        action, amount, scores = decision
        if not (action == "hold" and float(amount) == 0
                and scores["setup_match"]["status"] == "insufficient_data"
                and scores["dca_policy"]["source_available"] is False
                and scores["dca_policy"]["source_score"] is None
                and orders == 0 and ledger == 0 and float(cash) == 100
                and active is True and live is False
                and buckets == {"1h", "1d"}):
            raise AssertionError("stale_paper_contract_failed")
        return {
            "result": "PASS", "scope": "isolated_local_postgresql_celery",
            "fresh_components": ["macro", "market"],
            "stale_component": "technical",
            "setup_match": "insufficient_data", "decision": action,
            "amount_eur": float(amount), "orders": orders,
            "ledger_entries": ledger, "paper_cash_eur": float(cash),
            "bot_active": active, "bot_live": live,
            "snapshot_buckets": sorted(buckets),
        }
    finally:
        conn.close()


def main() -> None:
    _assert_local_only()
    from backend.celery_task.celery_app import celery_app
    from backend.celery_task.store_daily_scores_task import build_daily_scores_for_user

    user_id, bot_id, report_date = _seed_fixture()
    build_daily_scores_for_user(user_id, ["ETH"])
    task = celery_app.send_task(
        "backend.celery_task.trading_bot_task.run_daily_trading_bot",
        args=[user_id, report_date], queue=QUEUE,
    )
    result = task.get(timeout=30)
    if not isinstance(result, dict) or not result.get("ok") or result.get("decisions") != 1:
        raise AssertionError(f"celery_paper_task_failed:{result}")
    output = _verify(user_id, bot_id, report_date)
    output["task_id"] = task.id
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
