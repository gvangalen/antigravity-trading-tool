#!/usr/bin/env python3
"""Local-only Paper position exit probe; never touches a live exchange."""

import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone


def main() -> None:
    scenario = os.getenv("PAPER_EXIT_PROBE_SCENARIO", "target")
    if scenario not in {"target", "stop", "stale", "changed_levels", "execution_failure",
                        "usdt_target", "usdt_stop"}:
        raise RuntimeError("unknown_probe_scenario")
    symbol = "BTC" if scenario.startswith("usdt_") else "AAPL"
    quote_currency = "USDT" if symbol == "BTC" else "USD"
    required = {
        "APP_ENV": "local_finn", "DB_HOST": "127.0.0.1",
        "DB_PORT": "55432", "DB_NAME": "finn_local",
    }
    if any(os.getenv(key) != value for key, value in required.items()):
        raise RuntimeError("local_only_environment_required")
    from backend.utils.db import get_db_connection
    from backend.engine import trading_bot_execution as engine

    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    conn = get_db_connection()
    if conn is None:
        raise RuntimeError("local_database_unavailable")
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO users (email,password_hash,ai_preferences) VALUES (%s,'local-only','{}'::jsonb) RETURNING id",
                        (f"paper-exit-{uuid.uuid4().hex}@example.test",))
            user_id = int(cur.fetchone()[0])
            cur.execute("""INSERT INTO setups (user_id,name,symbol,timeframe,setup_type,created_at,last_validated)
                           VALUES (%s,'Local Paper exit',%s,'1D','trade',%s,%s) RETURNING id""",
                        (user_id, symbol, now, now))
            setup_id = int(cur.fetchone()[0])
            cur.execute("""INSERT INTO strategies
                           (user_id,setup_id,name,symbol,timeframe,setup_type,entry,stop_loss,targets,data,created_at)
                           VALUES (%s,%s,'Local Paper strategy',%s,'1D','trade',347.14,342,
                                   ARRAY['357.42','370.00'],
                                   '{"price_currency":"USD","price_currency_confirmed":true}'::jsonb,%s)
                           RETURNING id""", (user_id, setup_id, symbol, now))
            strategy_id = int(cur.fetchone()[0])
            cur.execute("""INSERT INTO bot_configs
                           (user_id,strategy_id,cadence,symbol,name,mode,is_live,is_active,risk_profile,
                            budget_total_eur,budget_daily_limit_eur,budget_min_order_eur,
                            budget_max_order_eur,max_asset_exposure_pct,base_currency,paper_initial_cash_eur,
                            created_at,updated_at)
                           VALUES (%s,%s,'daily',%s,'Local Paper bot','auto',FALSE,TRUE,'balanced',
                                   1000,1000,1,1000,100,'EUR',1000,%s,%s) RETURNING id""",
                        (user_id, strategy_id, symbol, now, now))
            bot_id = int(cur.fetchone()[0])
            cur.execute("""INSERT INTO portfolio_fx_rates
                           (quote_currency,eur_per_unit,provider,provider_pair,source_price,observed_at)
                           VALUES ('USD',0.92,'local_probe','EURUSD',1.0869565217,%s)
                           ON CONFLICT (quote_currency) DO UPDATE SET eur_per_unit=EXCLUDED.eur_per_unit,
                             observed_at=EXCLUDED.observed_at""", (now,))
            if quote_currency == "USDT":
                cur.execute("""INSERT INTO portfolio_fx_rates
                               (quote_currency,eur_per_unit,provider,provider_pair,source_price,observed_at)
                               VALUES ('USDT',0.90,'local_probe','EURUSDT',1.1111111111,%s)
                               ON CONFLICT (quote_currency) DO UPDATE SET eur_per_unit=EXCLUDED.eur_per_unit,
                                 observed_at=EXCLUDED.observed_at""", (now,))
            price = 340 if scenario in {"stop", "usdt_stop"} else (
                370 if scenario == "usdt_target" else 358)
            observed_at = now - timedelta(days=3) if scenario == "stale" else now
            if scenario == "stale":
                # Market rows are global in this disposable database.
                cur.execute("""UPDATE market_data SET source_observed_at=%s,timestamp=%s
                               WHERE symbol=%s""", (observed_at, observed_at, symbol))
            cur.execute("""INSERT INTO market_data (symbol,price,timestamp,source_observed_at,quote_currency)
                           VALUES (%s,%s,%s,%s,%s)""", (symbol, price, observed_at, observed_at, quote_currency))
            evidence = {"trade_plan": {
                "source_price_currency": "USD",
                "source_levels": {"entry": 347.14, "stop_loss": 342,
                                  "targets": [357.42, 370]},
            }}
            cur.execute("""INSERT INTO bot_decisions
                           (user_id,bot_id,strategy_id,setup_id,symbol,decision_date,decision_ts,
                            action,confidence,amount_eur,scores_json,status,executed_by)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,'buy','high',400,%s::jsonb,'executed','auto')
                           RETURNING id""",
                        (user_id, bot_id, strategy_id, setup_id, symbol, date.today(), now,
                         json.dumps(evidence)))
            buy_id = int(cur.fetchone()[0])
            cur.execute("""INSERT INTO bot_orders
                           (user_id,bot_id,decision_id,symbol,side,order_type,quote_amount_eur,
                            estimated_price_eur,estimated_qty,status,execution_environment)
                           VALUES (%s,%s,%s,%s,'buy','market',400,333.33,1.2,'filled','paper') RETURNING id""",
                        (user_id, bot_id, buy_id, symbol))
            order_id = int(cur.fetchone()[0])
            cur.execute("""INSERT INTO bot_ledger
                           (user_id,bot_id,decision_id,order_id,entry_type,symbol,cash_delta_eur,
                            qty_delta,price_eur,note,meta,ts,valuation_version)
                           VALUES (%s,%s,%s,%s,'execute',%s,-400,1.2,333.33,
                                   'Local opening Paper buy','{}'::jsonb,%s,2)""",
                        (user_id, bot_id, buy_id, order_id, symbol, now - timedelta(minutes=1)))
            cur.execute("""INSERT INTO bot_portfolios
                           (bot_id,user_id,symbol,cash_eur,position_qty,invested_eur,avg_entry,realized_pnl_eur)
                           VALUES (%s,%s,%s,600,1.2,400,333.33,0)""", (bot_id, user_id, symbol))
            if scenario == "changed_levels":
                cur.execute("UPDATE strategies SET stop_loss=341 WHERE id=%s AND user_id=%s",
                            (strategy_id, user_id))
        conn.commit()
    finally:
        conn.close()

    original_execute = engine._auto_execute_decision
    if scenario == "execution_failure":
        def fail_before_fill(**_kwargs):
            raise RuntimeError("local synthetic execution failure")
        engine._auto_execute_decision = fail_before_fill
    try:
        first = engine.run_trading_bot_execution(user_id, bot_id=bot_id, paper_only=True)
    finally:
        engine._auto_execute_decision = original_execute
    second = engine.run_trading_bot_execution(user_id, bot_id=bot_id, paper_only=True)
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT decision_kind,action,status FROM bot_decisions
                           WHERE user_id=%s AND bot_id=%s ORDER BY id""", (user_id, bot_id))
            decisions = cur.fetchall()
            cur.execute("""SELECT side,status FROM bot_orders
                           WHERE user_id=%s AND bot_id=%s ORDER BY id""", (user_id, bot_id))
            orders = cur.fetchall()
            cur.execute("""SELECT cash_eur,position_qty,realized_pnl_eur FROM bot_portfolios
                           WHERE user_id=%s AND bot_id=%s""", (user_id, bot_id))
            portfolio = cur.fetchone()
    finally:
        conn.close()
    result = {"scenario": scenario, "first": first, "second": second, "decisions": decisions,
              "orders": orders, "portfolio": portfolio}
    print(json.dumps(result, default=str))
    assert first["ok"] and second["ok"], result
    if scenario in {"target", "stop"}:
        assert decisions == [("assessment", "buy", "executed"),
                             ("paper_exit", "sell", "executed")], result
        assert orders == [("buy", "filled"), ("sell", "filled")], result
        assert first["decisions"][0]["trigger"] == (
            "first_target" if scenario in {"target", "usdt_target"} else "stop_loss"), result
        assert float(portfolio[1]) == 0, result
    else:
        expected_decisions = [("assessment", "buy", "executed")]
        if scenario == "execution_failure":
            expected_decisions.append(("paper_exit", "sell", "failed_execution"))
        assert decisions == expected_decisions, result
        assert orders == [("buy", "filled")], result
        assert float(portfolio[1]) == 1.2, result
        if scenario == "execution_failure":
            assert first["decisions"][0]["execution_status"] == "failed_execution", result
            assert second["decisions"][0]["action"] == "hold", result
        elif scenario in {"usdt_target", "usdt_stop"}:
            assert first["decisions"][0]["execution_status"] == "exit_trading_pair_unconfirmed", result
            assert second["decisions"][0]["execution_status"] == "exit_trading_pair_unconfirmed", result
        else:
            assert first["decisions"][0]["action"] == "hold", result


if __name__ == "__main__":
    main()
