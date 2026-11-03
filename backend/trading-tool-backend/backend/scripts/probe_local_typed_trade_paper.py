#!/usr/bin/env python3
"""Isolated exact-pair Score 2.0 → closed-candle entry → Paper probe.

Run only against the disposable local-finn stack and its dedicated worker.
No exchange credentials or production connections are used.
"""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

QUEUE = "local-finn-score2-positive-paper"
CASE = os.getenv("TYPED_TRADE_PAPER_CASE", "triggered")
if CASE not in {"triggered", "no_cross", "missing_score"}:
    raise ValueError("unsupported_typed_trade_paper_case")


def _assert_local_only():
    expected = {"APP_ENV": "local_finn", "DB_HOST": "127.0.0.1",
                "DB_PORT": "55432", "DB_NAME": "finn_local",
                "CELERY_BROKER_URL": "redis://127.0.0.1:56379/0"}
    for key, value in expected.items():
        if os.getenv(key) != value:
            raise RuntimeError(f"local_only_environment_required:{key}")


def _seed():
    from backend.utils.db import get_db_connection

    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    latest_close = (now.date() - timedelta(days=1))
    closed_at = datetime.combine(latest_close, datetime.min.time()).replace(hour=23, minute=59, second=59)
    fresh = now - timedelta(minutes=10)
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM trading_markets WHERE asset_symbol='BTC' AND quote_currency='EUR' AND venue='BINANCE' AND is_active=TRUE LIMIT 1")
            market_id = int(cur.fetchone()[0])
            cur.execute("INSERT INTO users (email,password_hash,ai_preferences) VALUES (%s,%s,'{}'::jsonb) RETURNING id",
                        (f"typed-paper-{uuid.uuid4().hex}@example.test", "local-fixture-no-login"))
            owner = int(cur.fetchone()[0])
            cur.execute("""INSERT INTO setups (user_id,name,symbol,timeframe,setup_type,
                        min_benchmark_score,max_benchmark_score,market_id,created_at,last_validated)
                        VALUES (%s,'Typed SMA50 Paper','BTC','1D','trade',0,100,%s,%s,%s) RETURNING id""",
                        (owner, market_id, now, now))
            setup_id = int(cur.fetchone()[0])
            signal = {"version": 1, "event": "close_crosses_reference", "direction": "above",
                      "timeframe": "1D", "reference": {"kind": "sma", "period": 50}}
            data = {"entry_signal": signal, "price_currency": "EUR", "price_currency_confirmed": True}
            cur.execute("""INSERT INTO strategies (user_id,setup_id,name,symbol,timeframe,setup_type,
                        execution_mode,base_amount,entry,stop_loss,targets,risk_profile,data,market_id,created_at)
                        VALUES (%s,%s,'Typed SMA50 Paper Strategy','BTC','1D','trade','fixed',10,
                                100,90,%s,'balanced',%s::jsonb,%s,%s) RETURNING id""",
                        (owner, setup_id, ['120'], json.dumps(data), market_id, now))
            strategy_id = int(cur.fetchone()[0])
            cur.execute("""INSERT INTO bot_configs (user_id,strategy_id,cadence,symbol,name,mode,is_live,is_active,
                        risk_profile,budget_total_eur,budget_daily_limit_eur,budget_min_order_eur,
                        budget_max_order_eur,max_asset_exposure_pct,base_currency,paper_initial_cash_eur,
                        market_id,created_at,updated_at)
                        VALUES (%s,%s,'daily','BTC','Typed SMA50 Paper Bot','auto',FALSE,TRUE,
                        'balanced',100,20,1,20,100,'EUR',100,%s,%s,%s) RETURNING id""",
                        (owner, strategy_id, market_id, now, now))
            bot_id = int(cur.fetchone()[0])
            cur.execute("""INSERT INTO bot_ledger (user_id,bot_id,entry_type,symbol,market_id,
                        cash_delta_eur,qty_delta,note,meta,ts)
                        VALUES (%s,%s,'paper_initial_funding','BTC',%s,100,0,
                        'Local typed Paper funding','{"source":"local_probe"}'::jsonb,NOW())""",
                        (owner, bot_id, market_id))
            cur.execute("""INSERT INTO bot_portfolios (bot_id,user_id,symbol,cash_eur,position_qty,
                        invested_eur,realized_pnl_eur) VALUES (%s,%s,'BTC',100,0,0,0)""",
                        (bot_id, owner))
            # 50 equal closes and one higher completed close give one exact SMA50
            # crossing. The current verified BTC/EUR price remains inside the
            # saved entry zone (100 through 101).
            for index in range(51):
                observed = closed_at - timedelta(days=50-index)
                price = 101 if index == 50 and CASE != "no_cross" else 100
                cur.execute("""INSERT INTO market_data (symbol,market_id,quote_currency,price,open,high,low,
                            is_final_candle,timestamp,source_observed_at,price_provider)
                            VALUES ('BTC',%s,'EUR',%s,%s,%s,%s,TRUE,%s,%s,'local_probe')""",
                            (market_id, price, price, price+1, price-1, observed, observed))
            cur.execute("""INSERT INTO market_data (symbol,market_id,quote_currency,price,
                        timestamp,source_observed_at,price_provider)
                        VALUES ('BTC',%s,'EUR',100.5,%s,%s,'local_probe')""",
                        (market_id, fresh, fresh))
            for category, indicator, value, table, name_column in (
                ("market", "price", 100.5, "market_data_indicators", "name"),
                ("technical", "rsi", 55, "technical_indicators", "indicator"),
                ("macro", "dxy", 102.2, "macro_data", "name"),
            ):
                if CASE == "missing_score" and category == "macro":
                    continue
                cur.execute("""INSERT INTO user_indicator_configs (user_id,indicator,category,symbol,
                            asset_class,market_id,priority,enabled,created_at,updated_at)
                            VALUES (%s,%s,%s,'BTC','crypto',%s,1,TRUE,%s,%s)""",
                            (owner, indicator, category, market_id if category != "macro" else None,
                             now-timedelta(hours=3), now-timedelta(hours=3)))
                columns = "market_id," if category != "macro" else ""
                values = "%s," if category != "macro" else ""
                params = ((owner, market_id, indicator, value, fresh, fresh) if category != "macro"
                          else (owner, indicator, value, fresh, fresh))
                cur.execute(f"INSERT INTO {table} (user_id,{columns}{name_column},value,timestamp,source_observed_at,symbol) "
                            f"VALUES (%s,{values}%s,%s,%s,%s,'BTC')", params)
            for days_ago in range(1, 5):
                observed = fresh-timedelta(days=days_ago)
                cur.execute("""INSERT INTO macro_data (user_id,symbol,name,value,timestamp,source_observed_at)
                            VALUES (%s,'BTC','dxy',%s,%s,%s)""",
                            (owner, 102.2-days_ago*0.1, observed, observed))
        conn.commit()
        return owner, bot_id, market_id, signal
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    _assert_local_only()
    from backend.celery_task.celery_app import celery_app
    from backend.celery_task.store_daily_scores_task import build_daily_scores_for_market
    from backend.engine.trading_bot_execution import _assess_saved_entry_signal, _get_daily_scores
    from backend.utils.db import get_db_connection

    owner, bot_id, market_id, signal = _seed()
    score_build = build_daily_scores_for_market(owner, market_id)
    conn = get_db_connection()
    try:
        signal_result = _assess_saved_entry_signal(conn, signal, market_id)
        scores = _get_daily_scores(conn, owner, datetime.now(timezone.utc).date(), 'BTC', market_id)
    finally:
        conn.close()
    expected_signal = 'not_triggered' if CASE == 'no_cross' else 'triggered'
    expected_macro_missing = CASE == 'missing_score'
    if (signal_result.get('status') != expected_signal
            or (scores.get('macro') is None) != expected_macro_missing
            or any(scores.get(key) is None for key in ('market', 'technical'))):
        raise AssertionError(f"source_fixture_invalid:{json.dumps({'signal': signal_result, 'scores': scores, 'build': score_build}, default=str)}")
    task = celery_app.send_task('backend.celery_task.trading_bot_task.run_daily_trading_bot',
                               args=[owner, datetime.now(timezone.utc).date().isoformat()], queue=QUEUE)
    result = task.get(timeout=40)
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT action,status,amount_eur,scores_json FROM bot_decisions WHERE user_id=%s AND bot_id=%s ORDER BY id DESC LIMIT 1", (owner,bot_id))
            decision = cur.fetchone()
            cur.execute("SELECT status,execution_environment,side,quote_amount_eur FROM bot_orders WHERE user_id=%s AND bot_id=%s", (owner,bot_id))
            orders = cur.fetchall()
            cur.execute("SELECT cash_eur,position_qty FROM bot_portfolios WHERE user_id=%s AND bot_id=%s", (owner,bot_id))
            portfolio = cur.fetchone()
    finally:
        conn.close()
    output = {'case': CASE, 'owner': owner, 'bot_id': bot_id, 'market_id': market_id,
              'signal': signal_result['status'], 'scores': {key: scores[key] for key in ('market','macro','technical')},
              'task': result, 'decision': decision[:3] if decision else None,
              'match': decision[3].get('setup_match',{}).get('status') if decision else None,
              'orders': orders, 'portfolio': portfolio}
    print(json.dumps(output, default=str, sort_keys=True))
    if CASE == 'triggered':
        if not (decision and decision[0] == 'buy' and decision[1] == 'executed'
                and decision[3].get('entry_signal',{}).get('status') == 'triggered'
                and orders and orders[0][:3] == ('filled','paper','buy')
                and float(portfolio[0]) < 100 and float(portfolio[1]) > 0):
            raise AssertionError('typed_trade_paper_not_executed')
    elif not (decision and decision[0] == 'hold' and not orders
              and float(portfolio[0]) == 100 and float(portfolio[1]) == 0):
        raise AssertionError(f'typed_trade_paper_should_hold:{CASE}')


if __name__ == '__main__':
    main()
