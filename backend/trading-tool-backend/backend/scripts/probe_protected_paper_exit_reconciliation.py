"""Protected, owner-scoped automatic Paper-exit reconciliation probe."""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone

from backend.scripts import probe_protected_score2_stale_paper as fixture
from backend.scripts.qa_trader_gate_invariants import check_paper_exit


@contextmanager
def _stage(name: str):
    try:
        yield
    except (RuntimeError, ValueError):
        raise
    except Exception:
        raise RuntimeError(f"paper_exit_{name}_failed") from None


@contextmanager
def _guard_live_exchange():
    from backend.engine import trading_bot_execution as execution

    original = execution._execute_on_exchange_sync
    attempts: list[bool] = []

    def blocked(*_args, **_kwargs):
        attempts.append(True)
        raise RuntimeError("paper_exit_live_execution_attempt")

    execution._execute_on_exchange_sync = blocked
    try:
        yield attempts
    finally:
        execution._execute_on_exchange_sync = original


def _target_array_expression(udt_name: str | None) -> str:
    if udt_name == "_text":
        return "ARRAY[%s::text]"
    if udt_name == "_varchar":
        return "ARRAY[%s::varchar]"
    if udt_name == "_numeric":
        return "ARRAY[%s::numeric]"
    raise RuntimeError("paper_exit_target_type_unavailable")


def _preflight() -> tuple[int, dict]:
    from backend.engine.trading_bot_execution import (
        PAPER_AUTO_EXIT_CUTOVER, _get_trade_quote_fx_context,
    )

    if not PAPER_AUTO_EXIT_CUTOVER:
        raise RuntimeError("paper_exit_cutover_unavailable")
    connection = fixture._connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT id FROM trading_markets
                              WHERE asset_symbol='BTC' AND quote_currency='USDT'
                                AND venue='BINANCE' AND is_active=TRUE""")
            markets = cursor.fetchall()
        if len(markets) != 1:
            raise RuntimeError("paper_exit_exact_market_unavailable")
        market_id = int(markets[0][0])
        context = _get_trade_quote_fx_context(
            connection, "BTC", require_usd=False, market_id=market_id,
        )
        if context.get("reason") is not None or not context.get("market_price_eur"):
            raise RuntimeError("paper_exit_dated_quote_unavailable")
        return market_id, context
    finally:
        connection.close()


def _seed_trade(user_id: int, bot_id: int,
                market_id: int, context: dict) -> tuple[int, int]:
    source_price = float(context["market_price"])
    eur_price = float(context["market_price_eur"])
    entry, stop, target = source_price * 0.7, source_price * 0.6, source_price * 0.8
    qty = 0.001
    invested = round(eur_price * qty, 2)
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    connection = fixture._connection()
    phase = "lookup_bot"
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT strategy_id FROM bot_configs WHERE id=%s AND user_id=%s AND is_live=FALSE",
                           (bot_id, user_id))
            row = cursor.fetchone()
            if not row:
                raise RuntimeError("paper_exit_fixture_identity_invalid")
            strategy_id = int(row[0])
            phase = "lookup_setup"
            cursor.execute("SELECT setup_id FROM strategies WHERE id=%s AND user_id=%s",
                           (strategy_id, user_id))
            row = cursor.fetchone()
            if not row:
                raise RuntimeError("paper_exit_fixture_identity_invalid")
            setup_id = int(row[0])
            phase = "setup_update"
            cursor.execute("""UPDATE setups SET symbol='BTC',market_id=%s,setup_type='trade',
                              dca_frequency=NULL,last_validated=%s
                              WHERE id=%s AND user_id=%s""",
                           (market_id, now, setup_id, user_id))
            phase = "target_type"
            cursor.execute("""SELECT udt_name FROM information_schema.columns
                              WHERE table_schema='public' AND table_name='strategies'
                                AND column_name='targets'""")
            target_type = cursor.fetchone()
            target_expression = _target_array_expression(target_type[0] if target_type else None)
            phase = "strategy_update"
            cursor.execute(f"""UPDATE strategies SET symbol='BTC',market_id=%s,setup_type='trade',
                              entry=%s,stop_loss=%s,targets={target_expression},data=%s::jsonb
                              WHERE id=%s AND user_id=%s""",
                           (market_id, entry, stop, str(target),
                            json.dumps({"price_currency": "USDT", "price_currency_confirmed": True}),
                            strategy_id, user_id))
            phase = "bot_update"
            cursor.execute("""UPDATE bot_configs SET symbol='BTC',market_id=%s,mode='auto',
                              is_live=FALSE,is_active=TRUE,budget_total_eur=1000,
                              budget_daily_limit_eur=1000,budget_max_order_eur=1000,
                              paper_initial_cash_eur=1000
                              WHERE id=%s AND user_id=%s AND is_live=FALSE""",
                           (market_id, bot_id, user_id))
            if cursor.rowcount != 1:
                raise RuntimeError("paper_exit_fixture_identity_invalid")
            phase = "portfolio_update"
            cursor.execute("""UPDATE bot_portfolios SET symbol='BTC',cash_eur=%s,
                              position_qty=%s,invested_eur=%s,avg_entry=%s,realized_pnl_eur=0
                              WHERE bot_id=%s AND user_id=%s""",
                           (1000 - invested, qty, invested, eur_price, bot_id, user_id))
            if cursor.rowcount != 1:
                raise RuntimeError("paper_exit_fixture_identity_invalid")
            opening = {"trade_plan": {
                "source_price_currency": "USDT",
                "source_levels": {"entry": entry, "stop_loss": stop, "targets": [target]},
            }}
            phase = "decision_insert"
            cursor.execute("""INSERT INTO bot_decisions
                              (user_id,bot_id,strategy_id,setup_id,symbol,market_id,
                               decision_date,decision_ts,action,confidence,amount_eur,
                               scores_json,status,executed_by)
                              VALUES (%s,%s,%s,%s,'BTC',%s,CURRENT_DATE,%s,'buy','high',
                                      %s,%s::jsonb,'executed','auto') RETURNING id""",
                           (user_id, bot_id, strategy_id, setup_id, market_id,
                            now, invested, json.dumps(opening)))
            decision_id = int(cursor.fetchone()[0])
            phase = "order_insert"
            cursor.execute("""INSERT INTO bot_orders
                              (user_id,bot_id,decision_id,symbol,market_id,side,order_type,
                               quote_amount_eur,estimated_price_eur,estimated_qty,status,
                               execution_environment)
                              VALUES (%s,%s,%s,'BTC',%s,'buy','market',%s,%s,%s,
                                      'filled','paper') RETURNING id""",
                           (user_id, bot_id, decision_id, market_id, invested, eur_price, qty))
            order_id = int(cursor.fetchone()[0])
            phase = "ledger_insert"
            cursor.execute("""INSERT INTO bot_ledger
                              (user_id,bot_id,decision_id,order_id,entry_type,symbol,market_id,
                               cash_delta_eur,qty_delta,price_eur,note,meta,ts,valuation_version)
                              VALUES (%s,%s,%s,%s,'execute','BTC',%s,%s,%s,%s,
                                      'Protected QA Paper opening','{}'::jsonb,%s,2)""",
                           (user_id, bot_id, decision_id, order_id, market_id,
                            -invested, qty, eur_price, now))
        phase = "commit"
        connection.commit()
        return setup_id, strategy_id
    except Exception as error:
        connection.rollback()
        if isinstance(error, (RuntimeError, ValueError)):
            raise
        raise RuntimeError(f"paper_exit_open_{phase}_failed") from None
    finally:
        connection.close()


async def _history(user_id: int) -> list[dict]:
    from backend.infrastructure.database import async_session_factory, engine
    from backend.services.bot_service import BotService

    try:
        async with async_session_factory() as session:
            return await BotService(session).get_bot_history(user_id, 7)
    finally:
        await engine.dispose()


def _evidence(namespace: str, user_id: int, bot_id: int, market_id: int,
              initial_cash: float, initial_qty: float,
              live_calls: int) -> dict:
    connection = fixture._connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT d.id,d.scores_json,d.status,o.side,o.status,
                                     o.execution_environment,o.executed_qty,
                                     o.executed_price_eur,o.quote_amount_eur,o.id
                              FROM bot_decisions d JOIN bot_orders o
                                ON o.decision_id=d.id AND o.user_id=d.user_id
                              WHERE d.user_id=%s AND d.bot_id=%s
                                AND d.market_id=%s AND d.decision_kind='paper_exit'""",
                           (user_id, bot_id, market_id))
            rows = cursor.fetchall()
            cursor.execute("""SELECT cash_eur,position_qty FROM bot_portfolios
                              WHERE user_id=%s AND bot_id=%s AND symbol='BTC'""",
                           (user_id, bot_id))
            portfolio = cursor.fetchone()
            cursor.execute("""SELECT l.cash_delta_eur,l.qty_delta,l.price_eur,l.order_id
                              FROM bot_ledger l JOIN bot_decisions d
                                ON d.id=l.decision_id AND d.user_id=l.user_id
                              WHERE l.user_id=%s AND l.bot_id=%s
                                AND d.decision_kind='paper_exit'""",
                           (user_id, bot_id))
            ledger = cursor.fetchall()
            cursor.execute("""SELECT COUNT(*) FROM bot_executions e
                              JOIN bot_orders o ON o.id=e.bot_order_id AND o.user_id=e.user_id
                              JOIN bot_decisions d ON d.id=o.decision_id AND d.user_id=o.user_id
                              WHERE e.user_id=%s AND o.bot_id=%s
                                AND d.decision_kind='paper_exit' AND e.status='filled'""",
                           (user_id, bot_id))
            execution_count = cursor.fetchone()[0]
            cursor.execute("SELECT is_active,ai_preferences FROM users WHERE id=%s", (user_id,))
            owner = cursor.fetchone()
            cursor.execute("SELECT COUNT(*) FROM exchange_keys WHERE user_id=%s", (user_id,))
            exchange_keys = cursor.fetchone()[0]
            cursor.execute("SELECT is_live FROM bot_configs WHERE id=%s AND user_id=%s", (bot_id, user_id))
            live = cursor.fetchone()
            cursor.execute("""SELECT COUNT(*) FROM bot_orders
                              WHERE user_id=%s AND bot_id=%s
                                AND execution_environment='live'""", (user_id, bot_id))
            live_orders = cursor.fetchone()[0]
        history = asyncio.run(_history(user_id))
        if len(rows) != 1 or len(ledger) != 1 or portfolio is None or live is None:
            raise RuntimeError("paper_exit_persisted_effect_incomplete")
        decision_id, raw, decision_status, side, order_status, environment, qty, price, proceeds, order_id = rows[0]
        data = raw if isinstance(raw, dict) else json.loads(raw)
        projection = next((item.get("exit_evidence") for item in history
                           if item.get("decision_id") == decision_id), None)
        projection = projection if isinstance(projection, dict) else {}
        history_projection = {
            "execution_source_currency": projection.get("execution_source_price_currency"),
            "execution_source_at": projection.get("execution_source_price_at"),
            "execution_fx_at": projection.get("execution_fx_observed_at"),
            "quantity": projection.get("execution_qty"),
            "execution_eur_price": projection.get("execution_eur_price"),
            "proceeds_eur": projection.get("execution_proceeds_eur"),
        }
        return {
            "environment": environment, "is_live": live[0], "live_calls": live_calls,
            "broker_orders": live_orders,
            "owner_scoped": bool(owner and isinstance(owner[1], dict)
                                  and owner[1].get("qa_fixture") == fixture.FIXTURE_MARKER
                                  and owner[1].get("qa_namespace") == namespace),
            "owner_active": owner[0] if owner else None, "exchange_keys": exchange_keys,
            "order_count": len(rows), "execution_count": execution_count,
            "side": side, "status": order_status if decision_status == "executed" else decision_status,
            "execution_source_at": data.get("execution_source_price_at"),
            "execution_fx_at": data.get("execution_fx_observed_at"),
            "execution_source_currency": data.get("execution_source_price_currency"),
            "settlement_currency": "EUR",
            "execution_source_price": data.get("execution_source_price"),
            "execution_fx_eur_per_unit": data.get("execution_fx_eur_per_unit"),
            "execution_eur_price": data.get("execution_eur_price"),
            "quantity": data.get("execution_qty"),
            "order_quantity": qty, "ledger_qty_delta": ledger[0][1],
            "proceeds_eur": data.get("execution_proceeds_eur"),
            "order_amount_eur": proceeds,
            "cash_before_eur": initial_cash, "cash_after_eur": portfolio[0],
            "quantity_before": initial_qty, "quantity_after": portfolio[1],
            "order_price_eur": price, "ledger_price_eur": ledger[0][2],
            "ledger_cash_delta_eur": ledger[0][0],
            "order_id": order_id, "ledger_order_id": ledger[0][3],
            "history_projection": history_projection,
        }
    finally:
        connection.close()


def run(namespace: str) -> dict:
    if os.getenv("FINN_QA_ALLOW_PAPER_EXIT_FIXTURE") != "1":
        raise RuntimeError("paper_exit_fixture_not_authorized")
    if not fixture.NAMESPACE_PATTERN.fullmatch(namespace):
        raise RuntimeError("paper_exit_namespace_invalid")
    bound = os.getenv("FINN_QA_USER_ID", "")
    if not bound.isdecimal() or int(bound) <= 0:
        raise RuntimeError("fixture_binding_invalid")
    with _stage("preflight"):
        market_id, context = _preflight()
    user_id = bot_id = None
    passed = False
    try:
        with _stage("seed"):
            user_id, bot_id, _ = fixture._seed(namespace, int(bound))
        with _stage("paper_open"):
            _seed_trade(user_id, bot_id, market_id, context)
        with _stage("baseline"):
            connection = fixture._connection()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT cash_eur,position_qty FROM bot_portfolios WHERE user_id=%s AND bot_id=%s",
                                   (user_id, bot_id))
                    initial_cash, initial_qty = cursor.fetchone()
            finally:
                connection.close()
        from backend.engine.trading_bot_execution import run_trading_bot_execution

        with _stage("engine"):
            with _guard_live_exchange() as live_attempts:
                first = run_trading_bot_execution(user_id, bot_id=bot_id, paper_only=True)
                second = run_trading_bot_execution(user_id, bot_id=bot_id, paper_only=True)
        live_calls = len(live_attempts)
        if not first.get("ok") or not second.get("ok"):
            raise RuntimeError("paper_exit_engine_unavailable")
        with _stage("evidence"):
            evidence = _evidence(namespace, user_id, bot_id, market_id,
                                 float(initial_cash), float(initial_qty), live_calls)
        result = check_paper_exit(evidence)
        if result["result"] != "PASS":
            return {**result, "rendered_ui_checked": False,
                    "gate_status": "FAIL", "engine_calls": 2,
                    "live_calls": live_calls}
        passed = True
        return {**result, "exit_decisions": 1, "replay_duplicate_sells": 0,
                "engine_calls": 2, "live_calls": live_calls,
                "rendered_ui_checked": False,
                "gate_status": "PARTIAL"}
    finally:
        if user_id is not None and bot_id is not None:
            if passed:
                fixture._cleanup(namespace, user_id, bot_id)
            else:
                fixture._quarantine(namespace, user_id, bot_id)
