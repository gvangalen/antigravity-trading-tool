"""One-shot protected QA probe for an automatic Paper fill and trade history.

The fixture owner is inactive and has no exchange keys. Only the protected
production QA workflow may invoke this module. No fixture identifiers or row
contents leave the protected host.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import secrets
from datetime import datetime, timezone

FIXTURE_MARKER = "finn_auto_paper_history_qa_v1"
QA_OWNER_MARKER = "finn_production_qa_v1"
NAMESPACE_PATTERN = re.compile(r"qa-[0-9]+-[0-9]+-[0-9a-f]{8}-[0-9a-f]{8}\Z")
SYMBOL = "BTC"
START_CASH_EUR = 100
ORDER_EUR = 50
PRICE_EUR = 50000
ORDER_QTY = 0.001


def _connection():
    from backend.utils.db import get_db_connection

    connection = get_db_connection()
    if connection is None:
        raise RuntimeError("qa_database_unavailable")
    return connection


def _require_protected_run(namespace: str) -> int:
    if os.getenv("FINN_QA_ALLOW_AUTO_PAPER_HISTORY_FIXTURE") != "1":
        raise RuntimeError("auto_paper_fixture_not_authorized")
    if not NAMESPACE_PATTERN.fullmatch(namespace):
        raise RuntimeError("auto_paper_fixture_namespace_invalid")
    bound = os.getenv("FINN_QA_USER_ID", "")
    if not bound.isdecimal() or int(bound) <= 0:
        raise RuntimeError("fixture_binding_invalid")
    return int(bound)


def _seed(namespace: str, bound_qa_owner: int) -> tuple[int, int, int]:
    from backend.utils.auth_utils import hash_password

    connection = _connection()
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT role,is_active,ai_preferences FROM users WHERE id=%s", (bound_qa_owner,))
            qa = cursor.fetchone()
            if not qa or qa[0] != "user" or qa[1] is not True or (qa[2] or {}).get("qa_fixture") != QA_OWNER_MARKER:
                raise RuntimeError("fixture_binding_invalid")
            cursor.execute("SELECT COUNT(*) FROM exchange_keys WHERE user_id=%s", (bound_qa_owner,))
            if cursor.fetchone()[0]:
                raise RuntimeError("fixture_has_exchange_keys")
            cursor.execute(
                """INSERT INTO users (email,password_hash,role,is_active,ai_preferences)
                   VALUES (%s,%s,'user',FALSE,%s::jsonb) RETURNING id""",
                (f"auto-paper-{namespace}@tradamind.example", hash_password(secrets.token_urlsafe(48)),
                 json.dumps({"qa_fixture": FIXTURE_MARKER, "qa_namespace": namespace})),
            )
            user_id = int(cursor.fetchone()[0])
            cursor.execute(
                """INSERT INTO setups
                   (user_id,name,symbol,timeframe,setup_type,dca_frequency,created_at,last_validated)
                   VALUES (%s,%s,'BTC','1D','dca','daily',%s,%s) RETURNING id""",
                (user_id, namespace, now, now),
            )
            setup_id = int(cursor.fetchone()[0])
            cursor.execute(
                """INSERT INTO strategies
                   (user_id,setup_id,name,symbol,timeframe,setup_type,execution_mode,
                    base_amount,decision_curve,data,created_at)
                   VALUES (%s,%s,%s,'BTC','1D','dca','fixed',50,'{}'::jsonb,'{}'::jsonb,%s)
                   RETURNING id""",
                (user_id, setup_id, namespace, now),
            )
            strategy_id = int(cursor.fetchone()[0])
            cursor.execute(
                """INSERT INTO bot_configs
                   (user_id,strategy_id,cadence,symbol,name,mode,is_live,is_active,
                    risk_profile,budget_total_eur,budget_daily_limit_eur,
                    budget_min_order_eur,budget_max_order_eur,max_asset_exposure_pct,
                    base_currency,created_at,updated_at)
                   VALUES (%s,%s,'daily','BTC',%s,'auto',FALSE,TRUE,'balanced',
                           100,50,1,50,100,'EUR',%s,%s) RETURNING id""",
                (user_id, strategy_id, namespace, now, now),
            )
            bot_id = int(cursor.fetchone()[0])
            cursor.execute(
                """INSERT INTO bot_ledger
                   (user_id,bot_id,entry_type,symbol,cash_delta_eur,qty_delta,note,meta,ts)
                   VALUES (%s,%s,'paper_initial_funding','BTC',100,0,
                           'Protected QA Paper funding','{"source":"protected_qa"}'::jsonb,NOW())""",
                (user_id, bot_id),
            )
            cursor.execute(
                """INSERT INTO bot_portfolios
                   (bot_id,user_id,symbol,cash_eur,position_qty,invested_eur,avg_entry,realized_pnl_eur)
                   VALUES (%s,%s,'BTC',100,0,0,0,0)""",
                (bot_id, user_id),
            )
            cursor.execute(
                """INSERT INTO bot_decisions
                   (user_id,bot_id,strategy_id,setup_id,symbol,decision_date,
                    action,confidence,amount_eur,status,scores_json)
                   VALUES (%s,%s,%s,%s,'BTC',CURRENT_DATE,'buy','high',50,'planned',%s::jsonb)
                   RETURNING id""",
                (user_id, bot_id, strategy_id, setup_id,
                 json.dumps({"setup_revision": now.isoformat()})),
            )
            decision_id = int(cursor.fetchone()[0])
        connection.commit()
        return user_id, bot_id, decision_id
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _execute(user_id: int, bot_id: int, decision_id: int) -> None:
    from backend.engine.trading_bot_execution import _auto_execute_decision, _persist_bot_order

    order = {"symbol": SYMBOL, "side": "buy", "quote_amount_eur": ORDER_EUR,
             "estimated_price": PRICE_EUR, "estimated_qty": ORDER_QTY}
    connection = _connection()
    try:
        _persist_bot_order(conn=connection, user_id=user_id, bot_id=bot_id,
                           decision_id=decision_id, order=order, is_live=False)
        if _auto_execute_decision(conn=connection, user_id=user_id, bot_id=bot_id,
                                  decision_id=decision_id, order=order,
                                  is_live=False, mode="auto") != "filled":
            raise RuntimeError("auto_paper_execution_not_filled")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


async def _history(user_id: int) -> dict:
    from backend.infrastructure.database import async_session_factory, engine
    from backend.services.bot_service import BotService

    try:
        async with async_session_factory() as session:
            return await BotService(session).get_account_bot_trades(user_id, 10, 0)
    finally:
        await engine.dispose()


def _verify(user_id: int, bot_id: int, decision_id: int) -> dict:
    connection = _connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT o.status,o.execution_environment,o.side,o.quote_amount_eur,
                          e.status,e.filled_qty,e.avg_fill_price,d.status,d.executed_by
                   FROM bot_orders o
                   JOIN bot_executions e ON e.bot_order_id=o.id AND e.user_id=o.user_id
                   JOIN bot_decisions d ON d.id=o.decision_id AND d.user_id=o.user_id
                   WHERE o.user_id=%s AND o.bot_id=%s AND o.decision_id=%s""",
                (user_id, bot_id, decision_id),
            )
            rows = cursor.fetchall()
            cursor.execute(
                """SELECT cash_eur,position_qty FROM bot_portfolios
                   WHERE user_id=%s AND bot_id=%s AND symbol='BTC'""",
                (user_id, bot_id),
            )
            portfolio = cursor.fetchone()
            cursor.execute(
                """SELECT entry_type,cash_delta_eur,qty_delta FROM bot_ledger
                   WHERE user_id=%s AND bot_id=%s ORDER BY id""",
                (user_id, bot_id),
            )
            ledger = cursor.fetchall()
            cursor.execute("SELECT COUNT(*) FROM exchange_keys WHERE user_id=%s", (user_id,))
            keys = cursor.fetchone()[0]
            cursor.execute("SELECT is_active FROM users WHERE id=%s", (user_id,))
            owner_active = cursor.fetchone()[0]
        history = asyncio.run(_history(user_id))
        items = history.get("items") or []
        spent = _assert_auto_paper_contract(
            rows=rows, portfolio=portfolio, ledger=ledger, keys=keys,
            owner_active=owner_active, items=items, bot_id=bot_id,
        )
        return {"result": "PASS", "order_status": "filled", "environment": "paper",
                "execution_mode": "auto", "trade_history_status": "filled",
                "amount_eur": spent, "cash_eur": round(START_CASH_EUR - spent, 2),
                "execution_ledger_entries": 1,
                "exchange_keys": 0, "live_trading_calls": 0}
    finally:
        connection.close()


def _assert_auto_paper_contract(*, rows, portfolio, ledger, keys,
                                owner_active, items, bot_id: int) -> float:
    """Check the actual EUR fill, without assuming the planning price held.

    Production Paper execution reprices at the current validated EUR quote and
    rounds quantity down. The approved EUR spend remains an upper bound.
    Failure codes reveal only the broken invariant, not fixture row contents.
    """
    if len(rows) != 1 or rows[0][:3] != ("filled", "paper", "buy") or rows[0][4] != "filled":
        raise RuntimeError("auto_paper_order_or_execution_not_filled")
    row = rows[0]
    if row[7:] != ("executed", "auto"):
        raise RuntimeError("auto_paper_decision_not_executed_auto")
    try:
        qty, price, spent = float(row[5]), float(row[6]), float(row[3])
    except (TypeError, ValueError, OverflowError):
        raise RuntimeError("auto_paper_fill_invalid") from None
    if not all(math.isfinite(value) and value > 0 for value in (qty, price, spent)):
        raise RuntimeError("auto_paper_fill_invalid")
    if spent > ORDER_EUR or round(qty * price, 2) != spent or qty > ORDER_EUR / price + 1e-8:
        raise RuntimeError("auto_paper_approved_spend_exceeded")
    if not portfolio or round(float(portfolio[0]), 2) != round(START_CASH_EUR - spent, 2) or not math.isclose(float(portfolio[1]), qty, abs_tol=1e-8):
        raise RuntimeError("auto_paper_portfolio_not_reconciled")
    if (len(ledger) != 2 or ledger[0][0] != "paper_initial_funding"
            or float(ledger[0][1]) != START_CASH_EUR
            or ledger[1][0] != "execute" or float(ledger[1][1]) != -spent
            or not math.isclose(float(ledger[1][2]), qty, abs_tol=1e-8)):
        raise RuntimeError("auto_paper_ledger_not_reconciled")
    if keys != 0 or owner_active is not False:
        raise RuntimeError("auto_paper_fixture_safety_breach")
    if (len(items) != 1 or items[0]["bot_id"] != bot_id
            or items[0]["environment"] != "paper"
            or items[0]["execution_mode"] != "auto"
            or items[0]["status"] != "filled"
            or items[0]["side"] != "buy"
            or not math.isclose(float(items[0]["qty"]), qty, abs_tol=1e-8)
            or not math.isclose(float(items[0]["price"]), price, rel_tol=1e-9)
            or float(items[0]["amount_eur"]) != spent):
        raise RuntimeError("auto_paper_history_not_reconciled")
    return spent


def _finish(namespace: str, user_id: int, bot_id: int, *, passed: bool) -> None:
    connection = _connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT ai_preferences FROM users WHERE id=%s FOR UPDATE", (user_id,))
            row = cursor.fetchone()
            if not row or (row[0] or {}).get("qa_fixture") != FIXTURE_MARKER or (row[0] or {}).get("qa_namespace") != namespace:
                raise RuntimeError("fixture_cleanup_owner_mismatch")
            cursor.execute("UPDATE users SET is_active=FALSE WHERE id=%s", (user_id,))
            cursor.execute("SELECT is_live FROM bot_configs WHERE id=%s AND user_id=%s FOR UPDATE", (bot_id, user_id))
            bot = cursor.fetchone()
            if not bot:
                raise RuntimeError("fixture_cleanup_bot_mismatch")
            cursor.execute(
                "UPDATE bot_configs SET is_active=FALSE WHERE id=%s AND user_id=%s",
                (bot_id, user_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("fixture_cleanup_bot_mismatch")
        connection.commit()
        if bot[0] is not False:
            raise RuntimeError("fixture_bot_became_live")
        if passed:
            with connection.cursor() as cursor:
                for table in ("bot_trade_plans", "bot_executions", "bot_ledger", "bot_orders",
                              "bot_decisions", "bot_portfolio_snapshots", "portfolio_balance_snapshots",
                              "bot_portfolios", "bot_configs", "strategies", "setups"):
                    cursor.execute("SELECT to_regclass(%s)", (f"public.{table}",))
                    if cursor.fetchone()[0] is not None:
                        cursor.execute(f"DELETE FROM {table} WHERE user_id=%s", (user_id,))
                cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))
                if cursor.rowcount != 1:
                    raise RuntimeError("fixture_cleanup_user_missing")
            connection.commit()
    except Exception:
        connection.rollback()
        raise RuntimeError("fixture_cleanup_failed") from None
    finally:
        connection.close()


def run(namespace: str) -> dict:
    bound = _require_protected_run(namespace)
    user_id = bot_id = None
    passed = False
    try:
        user_id, bot_id, decision_id = _seed(namespace, bound)
        _execute(user_id, bot_id, decision_id)
        result = _verify(user_id, bot_id, decision_id)
        passed = True
        return result
    finally:
        if user_id is not None and bot_id is not None:
            _finish(namespace, user_id, bot_id, passed=passed)
