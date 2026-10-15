"""Protected, one-shot Paper portfolio valuation and replay probe.

The inactive synthetic owner has no login token or exchange keys. The probe
reads existing dated market and FX sources; it never changes shared sources.
Only the protected production QA workflow may enable this module.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import secrets
from datetime import datetime, timezone

FIXTURE_MARKER = "finn_portfolio_paper_fx_qa_v1"
QA_OWNER_MARKER = "finn_production_qa_v1"
NAMESPACE_PATTERN = re.compile(r"qa-[0-9]+-[0-9]+-[0-9a-f]{8}-[0-9a-f]{8}\Z")
SYMBOL = "BTC"
START_CASH_EUR = 100.0
TARGET_ORDER_EUR = 50.0
FORGED_ESTIMATE_EUR = 1.0


def _connection():
    from backend.utils.db import get_db_connection

    connection = get_db_connection()
    if connection is None:
        raise RuntimeError("qa_database_unavailable")
    return connection


def _require_protected_run(namespace: str) -> int:
    if os.getenv("FINN_QA_ALLOW_PORTFOLIO_PAPER_FX_FIXTURE") != "1":
        raise RuntimeError("portfolio_paper_fx_fixture_not_authorized")
    if not NAMESPACE_PATTERN.fullmatch(namespace):
        raise RuntimeError("portfolio_paper_fx_namespace_invalid")
    bound = os.getenv("FINN_QA_USER_ID", "")
    if not bound.isdecimal() or int(bound) <= 0:
        raise RuntimeError("fixture_binding_invalid")
    return int(bound)


def _verified_source_price_eur() -> dict:
    """Require an existing non-EUR price and conversion before any write."""
    from backend.services.portfolio_fx_service import price_in_eur

    connection = _connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT m.price, m.source_observed_at, a.quote_currency
                   FROM market_data m
                   JOIN asset_catalog a ON a.symbol=m.symbol
                   WHERE m.symbol=%s AND m.price IS NOT NULL
                   ORDER BY m.timestamp DESC LIMIT 1""",
                (SYMBOL,),
            )
            market = cursor.fetchone()
            if not market or str(market[2] or "").upper() not in {"USD", "USDT"}:
                raise RuntimeError("portfolio_paper_fx_market_unavailable")
            quote = str(market[2]).upper()
            cursor.execute(
                """SELECT m.price, m.source_observed_at, a.quote_currency
                   FROM market_data m
                   JOIN asset_catalog a ON a.symbol=m.symbol
                   WHERE m.symbol=%s AND m.price IS NOT NULL AND m.price>0
                     AND m.source_observed_at IS NOT NULL
                   ORDER BY m.source_observed_at DESC, m.timestamp DESC LIMIT 1""",
                (SYMBOL,),
            )
            projected_market = cursor.fetchone()
            if (not projected_market or projected_market[0] != market[0]
                    or projected_market[1] != market[1]
                    or str(projected_market[2] or "").upper() != quote):
                raise RuntimeError("portfolio_paper_fx_price_source_mismatch")
            cursor.execute(
                """SELECT eur_per_unit, observed_at FROM portfolio_fx_rates
                   WHERE quote_currency=%s""",
                (quote,),
            )
            rate = cursor.fetchone()
        price, _source_at, factor, _fx_at = price_in_eur(
            price=market[0], price_at=market[1], quote_currency=quote,
            fx={"eur_per_unit": rate[0], "observed_at": rate[1]} if rate else None,
        )
        if price is None or factor is None or price <= FORGED_ESTIMATE_EUR:
            raise RuntimeError("portfolio_paper_fx_source_unavailable")
        return {
            "eur_price": float(price), "quote": quote,
            "raw_price": float(market[0]), "source_at": market[1],
            "fx_factor": float(factor), "fx_at": rate[1],
        }
    finally:
        connection.close()


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
                (f"portfolio-fx-{namespace}@tradamind.example",
                 hash_password(secrets.token_urlsafe(48)),
                 json.dumps({"qa_fixture": FIXTURE_MARKER, "qa_namespace": namespace})),
            )
            user_id = int(cursor.fetchone()[0])
            cursor.execute(
                """INSERT INTO setups
                   (user_id,name,symbol,timeframe,setup_type,dca_frequency,created_at,last_validated)
                   VALUES (%s,%s,%s,'1D','dca','daily',%s,%s) RETURNING id""",
                (user_id, namespace, SYMBOL, now, now),
            )
            setup_id = int(cursor.fetchone()[0])
            cursor.execute(
                """INSERT INTO strategies
                   (user_id,setup_id,name,symbol,timeframe,setup_type,execution_mode,
                    base_amount,decision_curve,data,created_at)
                   VALUES (%s,%s,%s,%s,'1D','dca','fixed',50,'{}'::jsonb,'{}'::jsonb,%s)
                   RETURNING id""",
                (user_id, setup_id, namespace, SYMBOL, now),
            )
            strategy_id = int(cursor.fetchone()[0])
            cursor.execute(
                """INSERT INTO bot_configs
                   (user_id,strategy_id,cadence,symbol,name,mode,is_live,is_active,
                    risk_profile,budget_total_eur,budget_daily_limit_eur,
                    budget_min_order_eur,budget_max_order_eur,max_asset_exposure_pct,
                    base_currency,created_at,updated_at)
                   VALUES (%s,%s,'daily',%s,%s,'auto',FALSE,TRUE,'balanced',
                           100,100,1,100,100,'EUR',%s,%s) RETURNING id""",
                (user_id, strategy_id, SYMBOL, namespace, now, now),
            )
            bot_id = int(cursor.fetchone()[0])
            cursor.execute(
                """INSERT INTO bot_ledger
                   (user_id,bot_id,entry_type,symbol,cash_delta_eur,qty_delta,note,meta,ts)
                   VALUES (%s,%s,'paper_initial_funding',%s,100,0,
                           'Protected QA Paper funding','{"source":"protected_qa"}'::jsonb,NOW())""",
                (user_id, bot_id, SYMBOL),
            )
            cursor.execute(
                """INSERT INTO bot_portfolios
                   (bot_id,user_id,symbol,cash_eur,position_qty,invested_eur,avg_entry,realized_pnl_eur)
                   VALUES (%s,%s,%s,100,0,0,0,0)""",
                (bot_id, user_id, SYMBOL),
            )
            cursor.execute(
                """INSERT INTO bot_decisions
                   (user_id,bot_id,strategy_id,setup_id,symbol,decision_date,
                    action,confidence,amount_eur,status,scores_json)
                   VALUES (%s,%s,%s,%s,%s,CURRENT_DATE,'buy','high',50,'planned',%s::jsonb)
                   RETURNING id""",
                (user_id, bot_id, strategy_id, setup_id, SYMBOL,
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


def _execute_and_replay(user_id: int, bot_id: int, decision_id: int, source_price: float) -> str:
    from backend.ai_agents.trading_bot_agent import _auto_execute_decision, _persist_bot_order

    quantity = round(TARGET_ORDER_EUR / source_price, 8)
    if quantity <= 0 or not math.isfinite(quantity):
        raise RuntimeError("portfolio_paper_fx_quantity_invalid")
    order = {
        "symbol": SYMBOL, "side": "buy", "quote_amount_eur": TARGET_ORDER_EUR,
        "estimated_price": FORGED_ESTIMATE_EUR, "estimated_qty": quantity,
    }
    connection = _connection()
    try:
        _persist_bot_order(conn=connection, user_id=user_id, bot_id=bot_id,
                           decision_id=decision_id, order=order, is_live=False)
        if _auto_execute_decision(conn=connection, user_id=user_id, bot_id=bot_id,
                                  decision_id=decision_id, order=order,
                                  is_live=False, mode="auto") != "filled":
            raise RuntimeError("portfolio_paper_fx_execution_not_filled")
        connection.commit()
        replay_rejected = False
        try:
            _auto_execute_decision(conn=connection, user_id=user_id, bot_id=bot_id,
                                   decision_id=decision_id, order=order,
                                   is_live=False, mode="auto")
        except RuntimeError as exc:
            replay_rejected = str(exc) == "Decision already processing or executed"
            connection.rollback()
        if not replay_rejected:
            raise RuntimeError("portfolio_paper_fx_replay_not_rejected")
        return "rejected_without_second_fill"
    finally:
        connection.close()


async def _projection(user_id: int):
    from backend.infrastructure.database import async_session_factory, engine
    from backend.services.finn_v2_tool_adapters.portfolio_tool_adapter import PortfolioToolAdapter

    try:
        async with async_session_factory() as session:
            return await PortfolioToolAdapter(session).execute(user_id=user_id, environment="paper")
    finally:
        await engine.dispose()


def _verify(user_id: int, bot_id: int, decision_id: int, source: dict) -> dict:
    connection = _connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT o.status,o.execution_environment,o.executed_price_eur,o.executed_qty,
                          e.status,d.status,d.executed_by
                   FROM bot_orders o
                   JOIN bot_executions e ON e.bot_order_id=o.id AND e.user_id=o.user_id
                   JOIN bot_decisions d ON d.id=o.decision_id AND d.user_id=o.user_id
                   WHERE o.user_id=%s AND o.bot_id=%s AND o.decision_id=%s""",
                (user_id, bot_id, decision_id),
            )
            orders = cursor.fetchall()
            cursor.execute(
                """SELECT cash_eur,position_qty FROM bot_portfolios
                   WHERE user_id=%s AND bot_id=%s AND symbol=%s""",
                (user_id, bot_id, SYMBOL),
            )
            portfolio = cursor.fetchone()
            cursor.execute(
                """SELECT entry_type,cash_delta_eur,qty_delta,valuation_version FROM bot_ledger
                   WHERE user_id=%s AND bot_id=%s ORDER BY id""",
                (user_id, bot_id),
            )
            ledger = cursor.fetchall()
            cursor.execute("SELECT COUNT(*) FROM exchange_keys WHERE user_id=%s", (user_id,))
            keys = cursor.fetchone()[0]
            cursor.execute("SELECT is_active FROM users WHERE id=%s", (user_id,))
            active = cursor.fetchone()[0]
        # A source update during the run makes exact fill provenance ambiguous.
        # Keep the failed fixture for diagnosis rather than accepting an
        # approximate conversion as proof.
        if _verified_source_price_eur() != source:
            raise RuntimeError("portfolio_paper_fx_source_changed")
        projected = asyncio.run(_projection(user_id))["data"]
        bot = projected.bots[0] if len(projected.bots) == 1 else None
        expected_cash = START_CASH_EUR + float(ledger[1][1]) if len(ledger) == 2 else None
        if not (len(orders) == 1 and orders[0][0:2] == ("filled", "paper")
                and abs(float(orders[0][2]) - source["raw_price"] * source["fx_factor"]) < 0.000001
                and float(orders[0][3]) > 0
                and orders[0][4:] == ("filled", "executed", "auto")
                and len(ledger) == 2 and ledger[0][0] == "paper_initial_funding"
                and float(ledger[0][1]) == START_CASH_EUR
                and ledger[1][0] == "execute" and ledger[1][3] == 2
                and float(ledger[1][1]) < 0 and float(ledger[1][2]) > 0
                and portfolio and abs(float(portfolio[0]) - expected_cash) < 0.01
                and abs(float(portfolio[1]) - float(orders[0][3])) < 1e-8
                and bot and bot.valuation_status == "available"
                and bot.price_quote_currency == source["quote"]
                and bot.fx_as_of is not None and bot.source_price_as_of is not None
                and abs(float(bot.fx_eur_per_unit or 0) - source["fx_factor"]) < 0.000000001
                and bot.cash_eur is not None and bot.position_value_eur is not None
                and bot.equity is not None
                and abs(bot.equity - bot.cash_eur - bot.position_value_eur) < 0.01
                and projected.valuation_status == "available"
                and keys == 0 and active is False):
            raise RuntimeError("portfolio_paper_fx_contract_failed")
        return {
            "result": "PASS", "environment": "paper", "quote_currency": source["quote"],
            "valuation_status": "available", "fx_dated": True,
            "source_price_dated": True, "order_count": 1,
            "execution_ledger_entries": 1, "replay": "rejected_without_second_fill",
            "forged_estimate_used": False, "exchange_keys": 0,
            "execution_environment": "paper",
        }
    finally:
        connection.close()


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
            cursor.execute("UPDATE bot_configs SET is_active=FALSE WHERE id=%s AND user_id=%s", (bot_id, user_id))
            if cursor.rowcount != 1:
                raise RuntimeError("fixture_cleanup_bot_mismatch")
        connection.commit()
        if bot[0] is not False:
            raise RuntimeError("fixture_bot_became_live")
        if passed:
            with connection.cursor() as cursor:
                for table in (
                    "bot_trade_plans", "bot_executions", "bot_ledger", "bot_orders",
                    "bot_decisions", "portfolio_value_snapshots_v2",
                    "bot_portfolio_snapshots", "portfolio_balance_snapshots",
                    "bot_portfolios", "bot_configs", "strategies", "setups",
                ):
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
    source = _verified_source_price_eur()
    user_id = bot_id = None
    passed = False
    try:
        user_id, bot_id, decision_id = _seed(namespace, bound)
        _execute_and_replay(user_id, bot_id, decision_id, source["eur_price"])
        result = _verify(user_id, bot_id, decision_id, source)
        passed = True
        return result
    finally:
        if user_id is not None and bot_id is not None:
            _finish(namespace, user_id, bot_id, passed=passed)
