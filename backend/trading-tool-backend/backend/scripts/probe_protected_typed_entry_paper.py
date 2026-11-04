"""Isolated production QA probe for a saved typed entry rule and Paper execution.

The protected runner is the sole caller. Each case owns an inactive QA user and
an inactive catalog asset with a unique exact market. The market is active only
while the direct Paper assessment runs. No normal market row or exchange key is
modified, and no Live order is possible.
"""

from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timedelta, timezone

from backend.scripts import probe_protected_score2_stale_paper as fixture

MARKER = "finn_typed_entry_paper_qa_v1"
CASES = ("sma_cross", "sma_no_cross", "sma_missing_score", "trendline_cross")


def _strategy_target_sql(cur) -> tuple[str, object]:
    """Adapt the QA target to either historical strategy array schema.

    Older production installations can retain a numeric[] targets column;
    the newer action migration adds text[] only when the column is absent.
    Both represent the same single QA target, but PostgreSQL cannot assign a
    bound text[] directly to numeric[]. Keep the selected SQL cast whitelisted.
    """
    cur.execute("""SELECT udt_name FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'strategies'
          AND column_name = 'targets'""")
    row = cur.fetchone()
    target_type = row[0] if row else None
    if target_type == "_text":
        return "ARRAY[%s]::text[]", "120"
    if target_type == "_varchar":
        return "ARRAY[%s]::varchar[]", "120"
    if target_type == "_numeric":
        return "ARRAY[%s]::numeric[]", 120
    raise RuntimeError("typed_entry_strategy_targets_schema_unsupported")


def _require_run(namespace: str) -> int:
    if os.getenv("FINN_QA_ALLOW_TYPED_ENTRY_PAPER_FIXTURE") != "1":
        raise RuntimeError("typed_entry_fixture_not_authorized")
    if not fixture.NAMESPACE_PATTERN.fullmatch(namespace):
        raise RuntimeError("typed_entry_fixture_namespace_invalid")
    bound = os.getenv("FINN_QA_USER_ID", "")
    if not bound.isdecimal() or int(bound) <= 0:
        raise RuntimeError("typed_entry_fixture_binding_invalid")
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT role,is_active,ai_preferences FROM users WHERE id=%s", (int(bound),))
            row = cur.fetchone()
            cur.execute("SELECT COUNT(*) FROM exchange_keys WHERE user_id=%s", (int(bound),))
            keys = int(cur.fetchone()[0])
        if (not row or row[0] != "user" or row[1] is not True or
                (row[2] or {}).get("qa_fixture") != fixture.QA_OWNER_MARKER or keys):
            raise RuntimeError("typed_entry_fixture_binding_invalid")
    finally:
        conn.close()
    return int(bound)


def _seed(namespace: str, case: str) -> tuple[int, int, int, str, dict]:
    from backend.utils.auth_utils import hash_password

    if case not in CASES:
        raise ValueError("typed_entry_case_invalid")
    suffix = secrets.token_hex(5).upper()
    symbol = f"FQA{suffix}"
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    # The latest completed UTC day is necessary for a real closed-candle test.
    last_day = now.date() - timedelta(days=1)
    latest_close = datetime.combine(last_day, datetime.min.time()).replace(
        hour=23, minute=59, second=59,
    )
    fresh = now - timedelta(minutes=5)
    conn = fixture._connection()
    stage = "asset_catalog"
    try:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO asset_catalog
                (symbol,display_name,asset_class,provider,is_active,metadata)
                VALUES (%s,'Protected Paper fixture','crypto','qa',FALSE,%s::json)""",
                (symbol, json.dumps({"qa_namespace": namespace, "qa_fixture": MARKER})))
            stage = "trading_markets"
            cur.execute("""INSERT INTO trading_markets
                (asset_symbol,quote_currency,venue,provider,provider_symbol,
                 tradingview_symbol,source_verified_at,is_active)
                VALUES (%s,'EUR','BINANCE','QA',%s,%s,%s,TRUE) RETURNING id""",
                (symbol, f"{symbol}EUR", f"BINANCE:{symbol}EUR", now))
            market_id = int(cur.fetchone()[0])
            stage = "users"
            cur.execute("""INSERT INTO users (email,password_hash,role,is_active,ai_preferences)
                VALUES (%s,%s,'user',FALSE,%s::jsonb) RETURNING id""",
                (f"typed-entry-{case}-{namespace}@tradamind.example",
                 hash_password(secrets.token_urlsafe(48)),
                 json.dumps({"qa_fixture": MARKER, "qa_namespace": namespace})))
            owner = int(cur.fetchone()[0])
            stage = "setups"
            cur.execute("""INSERT INTO setups
                (user_id,name,symbol,timeframe,setup_type,min_benchmark_score,
                 max_benchmark_score,market_id,created_at,last_validated)
                VALUES (%s,%s,%s,'1D','trade',0,100,%s,%s,%s) RETURNING id""",
                (owner, f"Typed entry {case}", symbol, market_id, now, now))
            setup_id = int(cur.fetchone()[0])
            signal = {
                "version": 1, "event": "close_crosses_reference", "direction": "above",
                "timeframe": "1D", "reference": {"kind": "sma", "period": 50},
            }
            if case == "trendline_cross":
                signal["reference"] = {
                    "kind": "trendline", "anchors": [
                        {"at": (latest_close - timedelta(days=2)).isoformat() + "Z", "price": 100.5},
                        {"at": (latest_close - timedelta(days=1)).isoformat() + "Z", "price": 100.5},
                    ],
                }
            strategy_data = {"entry_signal": signal, "price_currency": "EUR",
                             "price_currency_confirmed": True}
            stage = "strategies"
            target_sql, target_value = _strategy_target_sql(cur)
            cur.execute(f"""INSERT INTO strategies
                (user_id,setup_id,name,symbol,timeframe,setup_type,execution_mode,
                 base_amount,entry,stop_loss,targets,risk_profile,data,market_id,created_at)
                VALUES (%s,%s,%s,%s,'1D','trade','fixed',10,100,90,{target_sql},
                        'balanced',%s::jsonb,%s,%s) RETURNING id""",
                (owner, setup_id, f"Typed entry {case}", symbol, target_value,
                 json.dumps(strategy_data), market_id, now))
            strategy_id = int(cur.fetchone()[0])
            stage = "bot_configs"
            cur.execute("""INSERT INTO bot_configs
                (user_id,strategy_id,cadence,symbol,name,mode,is_live,is_active,
                 risk_profile,budget_total_eur,budget_daily_limit_eur,
                 budget_min_order_eur,budget_max_order_eur,max_asset_exposure_pct,
                 base_currency,paper_initial_cash_eur,market_id,created_at,updated_at)
                VALUES (%s,%s,'daily',%s,%s,'auto',FALSE,TRUE,'balanced',100,20,
                        1,20,100,'EUR',100,%s,%s,%s) RETURNING id""",
                (owner, strategy_id, symbol, f"Typed entry {case}", market_id, now, now))
            bot_id = int(cur.fetchone()[0])
            stage = "bot_ledger"
            cur.execute("""INSERT INTO bot_ledger
                (user_id,bot_id,entry_type,symbol,market_id,cash_delta_eur,
                 qty_delta,note,meta,ts)
                VALUES (%s,%s,'paper_initial_funding',%s,%s,100,0,
                        'Protected Paper funding',%s::jsonb,NOW())""",
                (owner, bot_id, symbol, market_id, json.dumps({"qa_fixture": MARKER})))
            stage = "bot_portfolios"
            cur.execute("""INSERT INTO bot_portfolios
                (bot_id,user_id,symbol,cash_eur,position_qty,invested_eur,realized_pnl_eur)
                VALUES (%s,%s,%s,100,0,0,0)""", (bot_id, owner, symbol))
            for index in range(51):
                stage = "market_data"
                observed = latest_close - timedelta(days=50-index)
                close = 100 if case == "sma_no_cross" or index < 50 else 101
                cur.execute("""INSERT INTO market_data
                    (symbol,market_id,quote_currency,price,open,high,low,is_final_candle,
                     timestamp,source_observed_at,price_provider)
                    VALUES (%s,%s,'EUR',%s,%s,%s,%s,TRUE,%s,%s,'protected_qa')""",
                    (symbol, market_id, close, close, close + 1, close - 1, observed, observed))
            cur.execute("""INSERT INTO market_data
                (symbol,market_id,quote_currency,price,timestamp,source_observed_at,price_provider)
                VALUES (%s,%s,'EUR',100.5,%s,%s,'protected_qa')""",
                (symbol, market_id, fresh, fresh))
            for category, indicator, value, table, name_column in (
                    ("market", "price", 100.5, "market_data_indicators", "name"),
                    ("technical", "rsi", 55, "technical_indicators", "indicator"),
                    ("macro", "dxy", 102.2, "macro_data", "name")):
                if case == "sma_missing_score" and category == "macro":
                    continue
                scoped_market = market_id if category != "macro" else None
                stage = "user_indicator_configs"
                cur.execute("""INSERT INTO user_indicator_configs
                    (user_id,indicator,category,symbol,asset_class,market_id,
                     priority,enabled,created_at,updated_at)
                    VALUES (%s,%s,%s,%s,'crypto',%s,1,TRUE,%s,%s)""",
                    (owner, indicator, category, symbol, scoped_market,
                     now - timedelta(hours=3), now - timedelta(hours=3)))
                if scoped_market is None:
                    stage = "macro_data"
                    cur.execute("""INSERT INTO macro_data
                        (user_id,name,value,timestamp,source_observed_at,symbol)
                        VALUES (%s,%s,%s,%s,%s,%s)""",
                        (owner, indicator, value, fresh, fresh, symbol))
                else:
                    stage = table
                    cur.execute(f"""INSERT INTO {table}
                        (user_id,market_id,{name_column},value,timestamp,source_observed_at,symbol)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                        (owner, market_id, indicator, value, fresh, fresh, symbol))
            if case != "sma_missing_score":
                for days_ago in range(1, 5):
                    stage = "macro_data"
                    observed = fresh - timedelta(days=days_ago)
                    cur.execute("""INSERT INTO macro_data
                        (user_id,symbol,name,value,timestamp,source_observed_at)
                        VALUES (%s,%s,'dxy',%s,%s,%s)""",
                        (owner, symbol, 102.2 - days_ago * 0.1, observed, observed))
        conn.commit()
        return owner, bot_id, market_id, symbol, signal
    except Exception as exc:
        conn.rollback()
        if type(exc).__name__ == "DatatypeMismatch":
            raise RuntimeError(f"typed_entry_seed_{stage}_datatype_mismatch") from exc
        raise
    finally:
        conn.close()


def _verify(owner: int, bot_id: int, market_id: int, case: str) -> dict:
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT action,status,amount_eur,scores_json,market_id
                FROM bot_decisions WHERE user_id=%s AND bot_id=%s ORDER BY id DESC LIMIT 1""",
                (owner, bot_id))
            decision = cur.fetchone()
            cur.execute("""SELECT status,execution_environment,side,market_id
                FROM bot_orders WHERE user_id=%s AND bot_id=%s""", (owner, bot_id))
            orders = cur.fetchall()
            cur.execute("""SELECT cash_eur,position_qty FROM bot_portfolios
                WHERE user_id=%s AND bot_id=%s""", (owner, bot_id))
            portfolio = cur.fetchone()
            cur.execute("SELECT COUNT(*) FROM exchange_keys WHERE user_id=%s", (owner,))
            keys = int(cur.fetchone()[0])
            cur.execute("SELECT is_active,is_live FROM bot_configs WHERE id=%s AND user_id=%s",
                        (bot_id, owner))
            bot_state = cur.fetchone()
        if not decision or not isinstance(decision[3], dict) or decision[4] != market_id:
            raise RuntimeError("typed_entry_decision_missing")
        if keys or bot_state != (True, False) or not portfolio:
            raise RuntimeError("typed_entry_fixture_safety_breach")
        signal_status = (decision[3].get("entry_signal") or {}).get("status")
        if case in {"sma_cross", "trendline_cross"}:
            if (decision[0:2] != ("buy", "executed") or signal_status != "triggered"
                    or len(orders) != 1 or orders[0] != ("filled", "paper", "buy", market_id)
                    or not 0 < float(portfolio[0]) < 100 or float(portfolio[1]) <= 0):
                raise RuntimeError("typed_entry_paper_fill_failed")
            return {"case": case, "result": "PASS", "signal": "triggered",
                    "decision": "buy", "order": "paper_filled", "live_bot": False}
        if (decision[0] != "hold" or orders or float(portfolio[0]) != 100
                or float(portfolio[1]) != 0):
            raise RuntimeError("typed_entry_paper_hold_failed")
        expected = "not_triggered" if case == "sma_no_cross" else "triggered"
        if signal_status != expected:
            raise RuntimeError("typed_entry_signal_status_wrong")
        return {"case": case, "result": "PASS", "signal": signal_status,
                "decision": "hold", "orders": 0, "live_bot": False}
    finally:
        conn.close()


def _finalize(namespace: str, owner: int, bot_id: int, market_id: int,
              symbol: str, *, passed: bool) -> None:
    conn = fixture._connection()
    stage = "owner_lock"
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT ai_preferences FROM users WHERE id=%s FOR UPDATE", (owner,))
            row = cur.fetchone()
            if (not row or (row[0] or {}).get("qa_fixture") != MARKER or
                    (row[0] or {}).get("qa_namespace") != namespace):
                raise RuntimeError("typed_entry_cleanup_owner_mismatch")
            stage = "bot_deactivate"
            cur.execute("UPDATE bot_configs SET is_active=FALSE WHERE id=%s AND user_id=%s AND is_live=FALSE",
                        (bot_id, owner))
            if cur.rowcount != 1:
                raise RuntimeError("typed_entry_cleanup_bot_mismatch")
            stage = "market_deactivate"
            cur.execute("UPDATE trading_markets SET is_active=FALSE WHERE id=%s AND asset_symbol=%s",
                        (market_id, symbol))
            if cur.rowcount != 1:
                raise RuntimeError("typed_entry_cleanup_market_mismatch")
            if passed:
                for table in (
                    "bot_trade_plans", "bot_executions", "bot_ledger", "bot_orders",
                    "bot_decisions", "portfolio_value_snapshots_v2",
                    "bot_portfolio_snapshots", "portfolio_balance_snapshots",
                    "bot_portfolios", "bot_configs", "strategies", "setups", "daily_scores",
                    "macro_data", "technical_indicators", "market_data_indicators",
                    "user_indicator_configs",
                ):
                    stage = "delete_" + table
                    cur.execute("SELECT to_regclass(%s)", (f"public.{table}",))
                    if cur.fetchone()[0] is not None:
                        cur.execute(f"DELETE FROM {table} WHERE user_id=%s", (owner,))
                stage = "delete_users"
                cur.execute("DELETE FROM users WHERE id=%s", (owner,))
                stage = "delete_market_data"
                cur.execute("DELETE FROM market_data WHERE market_id=%s", (market_id,))
                stage = "delete_trading_markets"
                cur.execute("DELETE FROM trading_markets WHERE id=%s AND asset_symbol=%s AND is_active=FALSE",
                            (market_id, symbol))
                stage = "delete_asset_catalog"
                cur.execute("DELETE FROM asset_catalog WHERE symbol=%s AND is_active=FALSE",
                            (symbol,))
        conn.commit()
    except Exception as exc:
        conn.rollback()
        # The failed fixture must never remain capable of executing.
        with conn.cursor() as cur:
            cur.execute("UPDATE bot_configs SET is_active=FALSE WHERE id=%s AND user_id=%s AND is_live=FALSE",
                        (bot_id, owner))
            cur.execute("UPDATE trading_markets SET is_active=FALSE WHERE id=%s AND asset_symbol=%s",
                        (market_id, symbol))
        conn.commit()
        if type(exc).__name__ == "DatatypeMismatch":
            raise RuntimeError(f"typed_entry_finalize_{stage}_datatype_mismatch") from exc
        raise
    finally:
        conn.close()


def _run_case(namespace: str, case: str, execution_attempts: list[str]) -> dict:
    from backend.celery_task.store_daily_scores_task import build_daily_scores_for_market
    from backend.engine.trading_bot_execution import _assess_saved_entry_signal, run_trading_bot_execution

    owner = bot_id = market_id = None
    symbol = ""
    passed = False
    stage = "seed"
    try:
        owner, bot_id, market_id, symbol, signal = _seed(namespace, case)
        stage = "score"
        score = build_daily_scores_for_market(owner, market_id)
        if case == "sma_missing_score":
            if score["scores"].get("macro") is not None:
                raise RuntimeError("typed_entry_missing_score_control_invalid")
        elif any(value is None for value in score["scores"].values()):
            raise RuntimeError("typed_entry_complete_score_control_invalid")
        conn = fixture._connection()
        try:
            stage = "signal"
            signal_result = _assess_saved_entry_signal(conn, signal, market_id)
        finally:
            conn.close()
        expected = "not_triggered" if case == "sma_no_cross" else "triggered"
        if signal_result.get("status") != expected:
            raise RuntimeError("typed_entry_candle_control_invalid")
        execution_attempts.append(case)
        stage = "execution"
        result = run_trading_bot_execution(
            owner, report_date=datetime.now(timezone.utc).date(), bot_id=bot_id,
            paper_only=True,
        )
        if not result.get("ok") or len(result.get("decisions") or []) != 1:
            raise RuntimeError("typed_entry_assessment_failed")
        stage = "verify"
        output = _verify(owner, bot_id, market_id, case)
        passed = True
        return output
    except Exception as exc:
        if type(exc).__name__ == "DatatypeMismatch":
            raise RuntimeError(f"typed_entry_{stage}_datatype_mismatch") from exc
        raise
    finally:
        if owner is not None and bot_id is not None and market_id is not None:
            _finalize(namespace, owner, bot_id, market_id, symbol, passed=passed)


def run(namespace: str) -> dict:
    _require_run(namespace)
    results = []
    execution_attempts: list[str] = []
    for case in CASES:
        # Continue all four cases, retaining only safe error classes in output.
        try:
            results.append(_run_case(namespace, case, execution_attempts))
        except Exception as exc:
            known_code = str(exc) if isinstance(exc, (RuntimeError, ValueError)) else ""
            if not known_code.startswith("typed_entry_"):
                known_code = type(exc).__name__
            results.append({"case": case, "result": "FAIL", "error_code": known_code})
    return {"result": "PASS" if all(item["result"] == "PASS" for item in results) else "FAIL",
            "cases": results, "case_count": len(results),
            "execution_calls": len(execution_attempts)}
