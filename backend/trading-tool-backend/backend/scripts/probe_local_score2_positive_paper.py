#!/usr/bin/env python3
"""Opt-in local positive Score 2.0 -> Smart DCA -> Celery -> Paper probe.

Requires the disposable local-finn PostgreSQL/Redis stack and a worker
consuming only ``local-finn-score2-positive-paper``. Never connects to production.
"""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

QUEUE = "local-finn-score2-positive-paper"


def _assert_local_only() -> None:
    expected = {
        "APP_ENV": "local_finn",
        "DB_HOST": "127.0.0.1",
        "DB_NAME": "finn_local",
    }
    for key, value in expected.items():
        if os.getenv(key) != value:
            raise RuntimeError(f"local_only_environment_required:{key}")
    local_endpoints = {
        ("55432", "redis://127.0.0.1:56379/0", "redis://127.0.0.1:56379/1", "18000"),
        ("55440", "redis://127.0.0.1:56390/0", "redis://127.0.0.1:56390/1", "18002"),
    }
    actual = (os.getenv("DB_PORT"), os.getenv("CELERY_BROKER_URL"),
              os.getenv("CELERY_RESULT_BACKEND"), os.getenv("FINN_LOCAL_PROBE_API_PORT", "18000"))
    if actual not in local_endpoints:
        raise RuntimeError("local_only_environment_required:isolated_endpoints")


def _seed_fixture() -> tuple[int, int, str]:
    _assert_local_only()
    from backend.domain.finn_dca_plan_contract import split_confirmed_dca_plan
    from backend.utils.db import get_db_connection

    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    fresh = now - timedelta(hours=1)
    email = f"score2-positive-paper-{uuid.uuid4().hex}@example.test"
    conn = get_db_connection()
    if conn is None:
        raise RuntimeError("local_database_unavailable")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT CURRENT_DATE")
            report_date = cur.fetchone()[0]
            # ETH is USDT-quoted in the catalog. The isolated worker needs a
            # dated conversion to create a verified EUR Paper valuation.
            cur.execute(
                """INSERT INTO portfolio_fx_rates
                   (quote_currency,eur_per_unit,provider,provider_pair,source_price,observed_at)
                   VALUES ('USDT',0.92,'local_probe','EURUSDT',1.0869565217,NOW())
                   ON CONFLICT (quote_currency) DO UPDATE SET
                     eur_per_unit=EXCLUDED.eur_per_unit,provider=EXCLUDED.provider,
                     provider_pair=EXCLUDED.provider_pair,source_price=EXCLUDED.source_price,
                     observed_at=EXCLUDED.observed_at"""
            )
            cur.execute(
                "INSERT INTO users (email,password_hash,ai_preferences) "
                "VALUES (%s,%s,%s::jsonb) RETURNING id",
                (email, "local-fixture-no-login", "{}"),
            )
            user_id = int(cur.fetchone()[0])
            cur.execute(
                """INSERT INTO setups (
                    user_id,name,symbol,timeframe,setup_type,dca_frequency,
                    min_benchmark_score,max_benchmark_score,
                    created_at,last_validated)
                   VALUES (%s,'Local positive Smart DCA','ETH','1D','dca','daily',
                           0,100,%s,%s) RETURNING id""",
                (user_id, now, now),
            )
            setup_id = int(cur.fetchone()[0])
            _, strategy = split_confirmed_dca_plan({
                "setup_type": "dca", "name": "Local positive Smart DCA",
                "base_amount": 50, "dca_amount_mode": "score_bands",
                "score_source": "benchmark_score", "low_threshold": 40,
                "high_threshold": 70, "low_score_percent": 100,
                "mid_score_percent": 100, "high_score_percent": 100,
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
                   VALUES (%s,%s,'daily','ETH','Local positive Smart Paper',
                           'auto',FALSE,TRUE,'balanced',100,50,1,50,100,
                           'EUR',100,%s,%s) RETURNING id""",
                (user_id, strategy_id, now, now),
            )
            bot_id = int(cur.fetchone()[0])
            cur.execute(
                """INSERT INTO bot_ledger
                   (user_id,bot_id,entry_type,symbol,cash_delta_eur,qty_delta,note,meta,ts)
                   VALUES (%s,%s,'paper_initial_funding','ETH',100,0,
                           'Local positive Paper funding','{"source":"local_probe"}'::jsonb,NOW())""",
                (user_id, bot_id),
            )
            cur.execute(
                """INSERT INTO bot_portfolios (
                    bot_id,user_id,symbol,cash_eur,position_qty,
                    invested_eur,realized_pnl_eur)
                   VALUES (%s,%s,'ETH',100,0,0,0)""",
                (bot_id, user_id),
            )
            for category, name, value, observed_at, table, name_column in (
                ("macro", "dxy", 102.2, fresh, "macro_data", "name"),
                ("technical", "rsi", 55, fresh, "technical_indicators", "indicator"),
                ("market", "price", 50000, fresh, "market_data_indicators", "name"),
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
                (4, 101.5, 49000), (3, 101.7, 49250),
                (2, 101.9, 49500), (1, 102.1, 49750), (0, 102.2, 50000),
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
    import asyncio
    from urllib.request import Request, urlopen

    from backend.infrastructure.database import async_session_factory, engine
    from backend.services.bot_service import BotService
    from backend.utils.auth_utils import create_access_token
    from backend.utils.db import get_db_connection

    async def account_history() -> dict:
        try:
            async with async_session_factory() as session:
                return await BotService(session).get_account_bot_trades(user_id, 10, 0)
        finally:
            await engine.dispose()

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
                """SELECT o.status,o.execution_environment,o.side,o.quote_amount_eur,
                          e.status,e.filled_qty,e.avg_fill_price
                   FROM bot_orders o JOIN bot_executions e
                     ON e.bot_order_id=o.id AND e.user_id=o.user_id
                   WHERE o.user_id=%s AND o.bot_id=%s""",
                (user_id, bot_id),
            )
            orders = cur.fetchall()
            cur.execute(
                """SELECT entry_type,cash_delta_eur,qty_delta FROM bot_ledger
                   WHERE user_id=%s AND bot_id=%s ORDER BY id""",
                (user_id, bot_id),
            )
            ledger = cur.fetchall()
            cur.execute(
                "SELECT count(*) FROM bot_trade_plans WHERE user_id=%s AND bot_id=%s",
                (user_id, bot_id),
            )
            plans = cur.fetchone()[0]
            cur.execute(
                """SELECT p.cash_eur,p.position_qty,b.is_active,b.is_live
                   FROM bot_portfolios p JOIN bot_configs b ON b.id=p.bot_id
                   WHERE p.user_id=%s AND p.bot_id=%s AND p.symbol='ETH'""",
                (user_id, bot_id),
            )
            cash, qty, active, live = cur.fetchone()
            cur.execute(
                """SELECT bucket,equity_eur,cash_eur,position_value_eur
                   FROM portfolio_value_snapshots_v2
                   WHERE user_id=%s AND environment='paper'""",
                (user_id,),
            )
            snapshots = cur.fetchall()
            buckets = {row[0] for row in snapshots}
            cur.execute("SELECT COUNT(*) FROM exchange_keys WHERE user_id=%s", (user_id,))
            exchange_keys = cur.fetchone()[0]
        history = asyncio.run(account_history())
        items = history.get("items") or []
        token = create_access_token({"sub": str(user_id), "role": "user"})
        def read_api(path: str) -> tuple[int, dict]:
            request = Request(
                f"http://127.0.0.1:{os.getenv('FINN_LOCAL_PROBE_API_PORT', '18000')}{path}",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urlopen(request, timeout=5) as response:
                return response.status, json.load(response)

        http_status, http_history = read_api("/api/bot/trades/all?limit=10&offset=0")
        today_status, today = read_api("/api/bot/today")
        history_status, decision_history = read_api("/api/bot/history?days=30")
        if not score_row or any(component is None for component in score_row):
            raise AssertionError(f"unexpected_score_components:{score_row}")
        if not decision:
            raise AssertionError("paper_decision_missing")
        action, amount, scores = decision
        if not (action == "buy" and float(amount) == 50
                and scores["setup_match"]["status"] == "matches"
                and plans == 1
                and len(orders) == 1
                and orders[0][:5] == ("filled", "paper", "buy", 50, "filled")
                and round(float(orders[0][5]) * float(orders[0][6]), 2) == 50
                and len(ledger) == 2
                and ledger[0][0] == "paper_initial_funding"
                and ledger[1][0] == "execute" and float(ledger[1][1]) == -50
                and float(ledger[1][2]) == float(orders[0][5])
                and float(cash) == 50 and float(qty) == float(orders[0][5])
                and active is True and live is False and exchange_keys == 0
                and buckets == {"1h", "1d"}
                and all(round(float(row[1]), 2) == 100 and float(row[2]) == 50
                        for row in snapshots)
                and len(items) == 1 and items[0]["bot_id"] == bot_id
                and items[0]["environment"] == "paper"
                and items[0]["execution_mode"] == "auto"
                and items[0]["status"] == "filled"
                and items[0]["amount_eur"] == 50
                and http_status == 200 and http_history == history
                and today_status == 200 and history_status == 200
                and len(today.get("decisions") or []) == 1
                and today["decisions"][0]["bot_id"] == bot_id
                and today["decisions"][0]["status"] == "executed"
                and today["decisions"][0]["safety_check"]["state"] == "executed"
                and len(decision_history) == 1):
            raise AssertionError(
                f"positive_paper_contract_failed:{json.dumps({'decision': decision, 'plans': plans, 'orders': orders, 'ledger': ledger, 'portfolio': [cash, qty, active, live], 'history': history, 'snapshots': snapshots}, default=str)}"
            )
        return {
            "result": "PASS", "scope": "isolated_local_postgresql_celery",
            "fresh_components": ["macro", "technical", "market"],
            "setup_match": scores["setup_match"]["status"], "decision": action,
            "amount_eur": float(amount), "orders": len(orders),
            "trade_plans": plans, "ledger_entries": len(ledger),
            "history_items": len(items), "paper_cash_eur": float(cash),
            "history_http_status": http_status,
            "today_http_status": today_status,
            "decision_history_http_status": history_status,
            "position_qty": float(qty), "exchange_keys": exchange_keys,
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
