"""Protected, owner-scoped automatic Paper-exit reconciliation probe."""

from __future__ import annotations

import asyncio
import json
import math
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from backend.scripts import probe_protected_score2_stale_paper as fixture
from backend.scripts.qa_browser_error_signature import (
    append_bounded_signature,
    classify_browser_error,
)
from backend.scripts.qa_trader_gate_invariants import check_paper_exit


async def _rendered_exit(user_id: int, bot_id: int, expected: dict) -> dict:
    phase = "bootstrap"
    token = None
    bot_responses = []
    onboarding_responses = []
    page_error_count = 0
    console_error_count = 0
    page_error_signatures = []
    console_error_signatures = []

    def observe_response(response):
        if (urlsplit(response.url).path == "/api/bot/configs"
                and response.request.method == "GET"):
            bot_responses.append(response)
        if (urlsplit(response.url).path == "/api/onboarding/status"
                and response.request.method == "GET"):
            onboarding_responses.append(response)

    def observe_page_error(error):
        nonlocal page_error_count
        page_error_count += 1
        append_bounded_signature(
            page_error_signatures,
            classify_browser_error(error, stack=getattr(error, "stack", None) or str(error)),
        )

    def observe_console(message):
        nonlocal console_error_count
        if getattr(message, "type", None) == "error":
            console_error_count += 1
            raw_location = getattr(message, "location", None)
            location = raw_location if isinstance(raw_location, dict) else {}
            append_bounded_signature(
                console_error_signatures,
                classify_browser_error(getattr(message, "text", ""), stack=location.get("url")),
            )

    async def inspect(page):
        nonlocal phase
        phase = "owner_bot_wait"
        selected_error = False
        try:
            await page.locator('div[aria-label] > button[aria-pressed="true"]').first.wait_for(timeout=20000)
        except Exception:
            selected_error = True
        phase = "owner_bot_page_get"
        if not bot_responses:
            phase = "owner_bot_page_get_unseen"
            raise RuntimeError(phase)
        found_owner_bot = False
        bot_shape = "unavailable"
        bot_count = None
        for response in bot_responses:
            if response.status in {401, 403}:
                phase = "owner_bot_page_get_auth"
                raise RuntimeError(phase)
            if response.status != 200:
                phase = "owner_bot_page_get_unavailable"
                raise RuntimeError(phase)
            try:
                bots = await response.json()
            except Exception:
                phase = "owner_bot_page_get_unparseable"
                raise RuntimeError(phase) from None
            bot_shape = "array" if isinstance(bots, list) else "wrapper" if isinstance(bots, dict) else "other"
            bot_count = len(bots) if isinstance(bots, list) else None
            found_owner_bot |= isinstance(bots, list) and any(
                isinstance(bot, dict) and bot.get("id") == bot_id for bot in bots
            )
        if not found_owner_bot or selected_error:
            path = urlsplit(page.url).path
            if path == "/bot":
                ui = await page.evaluate("""() => ({
                    focus_nav_present: !!document.querySelector('section:has(> header h1) > nav[aria-label]'),
                    bot_button_count: document.querySelectorAll('div[aria-label] > button[aria-pressed]').length,
                    onboarding_guide_present: !!document.querySelector('div.mb-10.space-y-6 > section'),
                })""")
                return {
                    "rendered_failure_reason": (
                        "owner_bot_page_get_missing" if not found_owner_bot else "owner_bot_not_selected"
                    ),
                    "ui_diagnostic": {
                        "route": "bot", "bot_get_status": 200,
                        "bot_get_shape": bot_shape, "bot_get_count": bot_count,
                        "owner_bot_present": found_owner_bot,
                        "onboarding_get_seen": bool(onboarding_responses),
                        "focus_nav_present": ui.get("focus_nav_present") is True,
                        "bot_button_count": ui.get("bot_button_count"),
                        "onboarding_guide_present": ui.get("onboarding_guide_present") is True,
                        "page_error_count": page_error_count,
                        "console_error_count": console_error_count,
                        "page_error_signatures": page_error_signatures,
                        "console_error_signatures": console_error_signatures,
                    },
                }
            phase = (
                "login_redirect" if path == "/login" else
                "onboarding_redirect" if path.startswith("/onboarding") else
                "owner_bot_absent" if path == "/bot" else "owner_bot_wait"
            )
            raise
        phase = "trades_tab_wait"
        trades_tab = page.locator('section:has(> header h1) > nav[aria-label] > button').nth(1)
        try:
            await trades_tab.wait_for(timeout=20000)
        except Exception:
            path = urlsplit(page.url).path
            phase = (
                "login_redirect" if path == "/login" else
                "onboarding_redirect" if path.startswith("/onboarding") else
                "tab_absent" if path == "/bot" else "trades_tab_wait"
            )
            raise
        phase = "trades_tab_click"
        await trades_tab.click()
        phase = "trades_api"
        trade_read = await page.evaluate("""async botId => {
            try {
                const response = await fetch('/api/bot/trades/all?limit=50&offset=0', {cache: 'no-store'});
                if (!response.ok) return {status: response.status, present: false};
                const data = await response.json();
                return {status: response.status, present: Array.isArray(data?.items) &&
                    data.items.some(trade => Number(trade.bot_id) === botId &&
                        trade.side === 'sell' && !!trade.exit_evidence)};
            } catch (_) { return {status: 0, present: false}; }
        }""", bot_id)
        if trade_read.get("status") != 200:
            phase = "trades_api_auth" if trade_read.get("status") in {401, 403} else "trades_api_unavailable"
            raise RuntimeError(phase)
        if trade_read.get("present") is not True:
            phase = "trades_api_missing"
            raise RuntimeError(phase)
        phase = "details"
        details = page.locator("table tbody details:has(dl)")
        await details.first.locator("summary").wait_for(timeout=20000)
        if await details.count() != 1:
            return {"rendered_exit_row_unique": False}
        await details.first.locator("summary").click()
        lines = await details.first.locator("dl > div").all_text_contents()
        phase = "projection"
        return await page.evaluate("""({lines, evidence}) => {
            const format = (value, digits) => new Intl.NumberFormat('nl-NL', {
                maximumFractionDigits: digits,
            }).format(Number(value));
            const time = (value) => new Intl.DateTimeFormat('nl-NL', {
                day: '2-digit', month: 'short', year: 'numeric',
                hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Amsterdam',
                timeZoneName: 'short',
            }).format(new Date(value));
            return {
                rendered_exit_fields_present: lines.length >= 10,
                rendered_saved_target: lines[2]?.includes(format(evidence.saved_first_target, 6)) &&
                    lines[2]?.includes(evidence.source_price_currency),
                rendered_decision_source_quote: lines[3]?.includes(format(evidence.source_price, 6)) &&
                    lines[3]?.includes(evidence.source_price_currency) &&
                    lines[3]?.includes(time(evidence.source_price_at)),
                rendered_decision_fx: lines[4]?.includes(format(evidence.fx_eur_per_unit, 6)) &&
                    lines[4]?.includes(time(evidence.fx_observed_at)),
                rendered_exit_eur_price: lines[5]?.includes(`${format(evidence.execution_eur_price, 6)} EUR`) ?? false,
                rendered_exit_quantity: lines[6]?.includes(format(evidence.execution_qty, 8)) ?? false,
                rendered_exit_proceeds: lines[7]?.includes(`${format(evidence.execution_proceeds_eur, 6)} EUR`) ?? false,
                rendered_exit_source_quote: lines[8]?.includes(format(evidence.execution_source_price, 6)) &&
                    lines[8]?.includes(evidence.execution_source_price_currency) &&
                    lines[8]?.includes(time(evidence.execution_source_price_at)),
                rendered_exit_fx: lines[9]?.includes(format(evidence.execution_fx_eur_per_unit, 6)) &&
                    lines[9]?.includes(time(evidence.execution_fx_observed_at)),
                rendered_conversion: lines[10]?.includes(format(evidence.execution_source_price, 6)) &&
                    lines[10]?.includes(format(evidence.execution_fx_eur_per_unit, 6)) &&
                    lines[10]?.includes(format(evidence.execution_eur_price, 6)),
            };
        }""", {"lines": lines, "evidence": expected})

    try:
        from backend.scripts.qa_protected_browser import observe_page
        from backend.utils.auth_utils import create_access_token

        token = create_access_token({"sub": str(user_id), "role": "user"})
        return await observe_page(
            base_url="https://tradamind.com", path=f"/bot?bot_id={bot_id}",
            token=token, inspect=inspect, bypass_fixture_onboarding=True,
            observe_response=observe_response,
            observe_page_error=observe_page_error, observe_console=observe_console,
        )
    except Exception:
        raise RuntimeError(f"paper_exit_rendered_{phase}_failed") from None
    finally:
        token = None


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


def _aapl_fixture_context() -> tuple[None, dict]:
    """A dated process-local USD quote; no shared market-data write or market claim."""
    from backend.engine.trading_bot_execution import PAPER_AUTO_EXIT_CUTOVER
    from backend.services.portfolio_fx_service import trade_quote_context

    if not PAPER_AUTO_EXIT_CUTOVER:
        raise RuntimeError("paper_exit_cutover_unavailable")
    connection = fixture._connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT quote_currency FROM asset_catalog WHERE symbol='AAPL'")
            rows = cursor.fetchall()
        if len(rows) != 1 or str(rows[0][0]).upper() != "USD":
            raise RuntimeError("paper_exit_aapl_catalog_unavailable")
    finally:
        connection.close()
    now = datetime.now(timezone.utc)
    quote_at, fx_at = now - timedelta(seconds=30), now - timedelta(seconds=45)
    context = trade_quote_context(
        price=400, price_at=quote_at, row_quote="USD", catalog_quote="USD",
        usd_fx={"eur_per_unit": 0.92, "observed_at": fx_at},
        quote_fx={"eur_per_unit": 0.92, "observed_at": fx_at},
        require_usd=True, now=now,
    )
    if context.get("reason") is not None:
        raise RuntimeError("paper_exit_aapl_fixture_quote_invalid")
    return None, {**context, "source_ref": None}


@contextmanager
def _fixture_quote_context(symbol: str, context: dict):
    """Restrict synthetic context to the inactive AAPL fixture engine calls."""
    if symbol != "AAPL":
        yield
        return
    from backend.engine import trading_bot_execution as execution

    original = execution._get_trade_quote_fx_context

    def fixture_quote(_connection, requested_symbol, *, require_usd=True, market_id=None):
        if requested_symbol != "AAPL" or market_id is not None or not require_usd:
            raise RuntimeError("paper_exit_fixture_quote_scope_changed")
        return context

    execution._get_trade_quote_fx_context = fixture_quote
    try:
        yield
    finally:
        execution._get_trade_quote_fx_context = original


def _seed_trade(user_id: int, bot_id: int,
                market_id: int | None, context: dict, *, symbol: str = "BTC") -> tuple[int, int]:
    if symbol not in {"BTC", "AAPL"} or (symbol == "BTC") != (market_id is not None):
        raise RuntimeError("paper_exit_fixture_identity_invalid")
    currency = "USD" if symbol == "AAPL" else "USDT"
    source_price = float(context["market_price"])
    eur_price = float(context["market_price_eur"])
    entry, stop, target = source_price * 0.7, source_price * 0.6, source_price * 0.8
    qty = 1 if symbol == "AAPL" else 0.001
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
            cursor.execute("""UPDATE setups SET symbol=%s,market_id=%s,setup_type='trade',
                              dca_frequency=NULL,last_validated=%s
                              WHERE id=%s AND user_id=%s""",
                           (symbol, market_id, now, setup_id, user_id))
            phase = "target_type"
            cursor.execute("""SELECT udt_name FROM information_schema.columns
                              WHERE table_schema='public' AND table_name='strategies'
                                AND column_name='targets'""")
            target_type = cursor.fetchone()
            target_expression = _target_array_expression(target_type[0] if target_type else None)
            phase = "strategy_update"
            cursor.execute(f"""UPDATE strategies SET symbol=%s,market_id=%s,setup_type='trade',
                              entry=%s,stop_loss=%s,targets={target_expression},data=%s::jsonb
                              WHERE id=%s AND user_id=%s""",
                           (symbol, market_id, entry, stop, str(target),
                            json.dumps({"price_currency": currency, "price_currency_confirmed": True}),
                            strategy_id, user_id))
            phase = "bot_update"
            cursor.execute("""UPDATE bot_configs SET symbol=%s,market_id=%s,mode='auto',
                              is_live=FALSE,is_active=TRUE,budget_total_eur=1000,
                              budget_daily_limit_eur=1000,budget_max_order_eur=1000,
                              paper_initial_cash_eur=1000
                              WHERE id=%s AND user_id=%s AND is_live=FALSE""",
                           (symbol, market_id, bot_id, user_id))
            if cursor.rowcount != 1:
                raise RuntimeError("paper_exit_fixture_identity_invalid")
            phase = "portfolio_update"
            cursor.execute("""UPDATE bot_portfolios SET symbol=%s,cash_eur=%s,
                              position_qty=%s,invested_eur=%s,avg_entry=%s,realized_pnl_eur=0
                              WHERE bot_id=%s AND user_id=%s""",
                           (symbol, 1000 - invested, qty, invested, eur_price, bot_id, user_id))
            if cursor.rowcount != 1:
                raise RuntimeError("paper_exit_fixture_identity_invalid")
            opening = {"trade_plan": {
                "source_price_currency": currency,
                "source_levels": {"entry": entry, "stop_loss": stop, "targets": [target]},
            }}
            phase = "decision_insert"
            cursor.execute("""INSERT INTO bot_decisions
                              (user_id,bot_id,strategy_id,setup_id,symbol,market_id,
                               decision_date,decision_ts,action,confidence,amount_eur,
                               scores_json,status,executed_by)
                               VALUES (%s,%s,%s,%s,%s,%s,CURRENT_DATE,%s,'buy','high',
                                      %s,%s::jsonb,'executed','auto') RETURNING id""",
                           (user_id, bot_id, strategy_id, setup_id, symbol, market_id,
                            now, invested, json.dumps(opening)))
            decision_id = int(cursor.fetchone()[0])
            phase = "order_insert"
            cursor.execute("""INSERT INTO bot_orders
                              (user_id,bot_id,decision_id,symbol,market_id,side,order_type,
                               quote_amount_eur,estimated_price_eur,estimated_qty,status,
                               execution_environment)
                              VALUES (%s,%s,%s,%s,%s,'buy','market',%s,%s,%s,
                                      'filled','paper') RETURNING id""",
                           (user_id, bot_id, decision_id, symbol, market_id, invested, eur_price, qty))
            order_id = int(cursor.fetchone()[0])
            # The opening order must carry the original quote-currency plan.
            # The review projector reads this immutable capture, not today's
            # mutable strategy levels or a later exit decision.
            phase = "plan_capture"
            opening_at = datetime.now(timezone.utc)
            cursor.execute("""UPDATE finn_trade_order_context
                              SET plan_snapshot=%s::jsonb,captured_at=%s
                              WHERE user_id=%s AND order_id=%s AND decision_id=%s""",
                           (json.dumps({"source_price_currency": currency,
                                        "source_levels": {"entry": entry,
                                                          "stop_loss": stop,
                                                          "targets": [target]}}),
                            opening_at, user_id, order_id, decision_id))
            if cursor.rowcount != 1:
                raise RuntimeError("paper_exit_open_plan_capture_missing")
            phase = "ledger_insert"
            cursor.execute("""INSERT INTO bot_ledger
                              (user_id,bot_id,decision_id,order_id,entry_type,symbol,market_id,
                               cash_delta_eur,qty_delta,price_eur,note,meta,ts,valuation_version)
                              VALUES (%s,%s,%s,%s,'execute',%s,%s,%s,%s,%s,
                                      'Protected QA Paper opening','{}'::jsonb,%s,2)""",
                           (user_id, bot_id, decision_id, order_id, symbol, market_id,
                            -invested, qty, eur_price, opening_at))
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


def _evidence(namespace: str, user_id: int, bot_id: int, market_id: int | None,
              initial_cash: float, initial_qty: float,
              live_calls: int, *, symbol: str = "BTC") -> dict:
    connection = fixture._connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT d.id,d.scores_json,d.status,o.side,o.status,
                                     o.execution_environment,o.executed_qty,
                                     o.executed_price_eur,o.quote_amount_eur,o.id
                              FROM bot_decisions d JOIN bot_orders o
                                ON o.decision_id=d.id AND o.user_id=d.user_id
                              WHERE d.user_id=%s AND d.bot_id=%s
                                AND d.market_id IS NOT DISTINCT FROM %s
                                AND d.decision_kind='paper_exit'""",
                           (user_id, bot_id, market_id))
            rows = cursor.fetchall()
            cursor.execute("""SELECT cash_eur,position_qty FROM bot_portfolios
                              WHERE user_id=%s AND bot_id=%s AND symbol=%s""",
                           (user_id, bot_id, symbol))
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
            "ui_projection": projection,
        }
    finally:
        connection.close()


async def _review_chain(user_id: int, bot_id: int, expected: dict) -> dict:
    """Project the same closed Paper position and require an owner-bound FINN read."""
    from backend.infrastructure.database import async_session_factory, engine
    from backend.services.finn_trade_review_service import FinnTradeReviewService
    from backend.scripts import probe_protected_closed_paper_review as review_probe

    await asyncio.to_thread(review_probe._process_review_for_fixture, user_id)
    try:
        async with async_session_factory() as session:
            service = FinnTradeReviewService(session)
            items = (await service.list_reviews(user_id, limit=10)).get("items") or []
            if len(items) != 1:
                raise RuntimeError("paper_exit_review_count_invalid")
            detail = await service.get_review(user_id, int(items[0]["id"]))
            exit_proof = detail.get("paper_exit_evidence") or {}
            plan = detail.get("plan_snapshot") or {}
            analysis = detail.get("analysis_json") or {}
            levels = plan.get("source_levels") or {}
            matches_level = lambda actual, saved: (
                isinstance(actual, (int, float)) and isinstance(saved, (int, float))
                and math.isclose(float(actual), float(saved), rel_tol=1e-9, abs_tol=1e-6)
            )
            if (detail.get("bot_id") != bot_id or detail.get("execution_environment") != "paper"
                    or detail.get("analysis_status") != "ready"
                    or analysis.get("format_version") != 4
                    or exit_proof.get("trigger") != "first_target"
                    or exit_proof.get("source_price_currency") != expected.get("source_price_currency")
                    or exit_proof.get("source_price") != expected.get("source_price")
                    or exit_proof.get("source_price_at") != expected.get("source_price_at")
                    or exit_proof.get("fx_eur_per_unit") != expected.get("fx_eur_per_unit")
                    or exit_proof.get("fx_observed_at") != expected.get("fx_observed_at")
                    or exit_proof.get("execution_source_price") != expected.get("execution_source_price")
                    or exit_proof.get("execution_source_price_at") != expected.get("execution_source_price_at")
                    or exit_proof.get("execution_fx_eur_per_unit") != expected.get("execution_fx_eur_per_unit")
                    or exit_proof.get("execution_fx_observed_at") != expected.get("execution_fx_observed_at")
                    or not matches_level(exit_proof.get("saved_stop_loss"), levels.get("stop_loss"))
                    or not matches_level(exit_proof.get("saved_first_target"), (levels.get("targets") or [None])[0])
                    or plan.get("source_price_currency") != expected.get("source_price_currency")
                    or detail.get("plan_status") != "entry_order_plan_recorded"):
                raise RuntimeError("paper_exit_review_evidence_incomplete")
            evidence_ids = {evidence_id for observation in analysis.get("observations") or []
                            for evidence_id in observation.get("evidence_ids") or []}
            if "paper_exit:decision" not in evidence_ids:
                raise RuntimeError("paper_exit_review_analysis_evidence_missing")
            review_id = int(detail["id"])
    finally:
        await engine.dispose()

    with review_probe._fixture_review_rollout(user_id):
        answer = await review_probe._chat_turn(
            user_id,
            f"Wat was bij mijn trade-reflectie #{review_id} de vastgelegde Paper-exitreden? "
            "Noem de oorspronkelijke koersvaluta, het opgeslagen eerste doel en de "
            "wisselkoers bij uitvoering. Alleen teruglezen; geen voorstel of actie.",
        )
    response = answer.response
    if (answer.status != "completed" or response is None
            or response.proposal_id or response.confirmation_required
            or (answer.policy and answer.policy.execute_allowed)):
        raise RuntimeError("paper_exit_finn_read_failed")
    if (not any(item.entity_type == "review_history" for item in response.evidence)
            or not await review_probe._has_responses_exchange(
                user_id, answer.run_id, answer.conversation_id)):
        raise RuntimeError("paper_exit_finn_owner_evidence_missing")
    text = response.content.casefold()
    numbers = text.replace(",", ".")
    target = f'{float(expected["saved_first_target"]):.6f}'.rstrip("0").rstrip(".")
    fx = f'{float(expected["execution_fx_eur_per_unit"]):.6f}'.rstrip("0").rstrip(".")
    if (not any(term in text for term in ("first_target", "eerste doel", "eerste koersdoel"))
            or expected["source_price_currency"].casefold() not in text
            or target not in numbers or fx not in numbers):
        raise RuntimeError("paper_exit_finn_answer_incomplete")
    return {"result": "PASS", "owner_scoped_review": True,
            "analysis_format_version": 4, "exit_evidence_cited": True,
            "owner_scoped_finn_read": True, "action_proposals": 0}


def _assert_fixture_absent(user_id: int) -> None:
    connection = fixture._connection()
    try:
        with connection.cursor() as cursor:
            for table in ("users", "finn_trade_reviews", "finn_v2_runs", "bot_orders"):
                cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {'id' if table == 'users' else 'user_id'}=%s",
                               (user_id,))
                if cursor.fetchone()[0]:
                    raise RuntimeError("paper_exit_fixture_cleanup_incomplete")
    finally:
        connection.close()


def run(namespace: str, *, source_parity: bool = False, review_chain: bool = False) -> dict:
    if os.getenv("FINN_QA_ALLOW_PAPER_EXIT_FIXTURE") != "1":
        raise RuntimeError("paper_exit_fixture_not_authorized")
    if not fixture.NAMESPACE_PATTERN.fullmatch(namespace):
        raise RuntimeError("paper_exit_namespace_invalid")
    bound = os.getenv("FINN_QA_USER_ID", "")
    if not bound.isdecimal() or int(bound) <= 0:
        raise RuntimeError("fixture_binding_invalid")
    symbol = "AAPL" if review_chain else "BTC"
    with _stage("preflight"):
        market_id, context = _aapl_fixture_context() if review_chain else _preflight()
    user_id = bot_id = None
    passed = False
    try:
        with _stage("seed"):
            user_id, bot_id, _ = fixture._seed(namespace, int(bound))
        with _stage("paper_open"):
            _seed_trade(user_id, bot_id, market_id, context, **({"symbol": symbol} if review_chain else {}))
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
            with _guard_live_exchange() as live_attempts, _fixture_quote_context(symbol, context):
                first = run_trading_bot_execution(user_id, bot_id=bot_id, paper_only=True)
                second = run_trading_bot_execution(user_id, bot_id=bot_id, paper_only=True)
        live_calls = len(live_attempts)
        if not first.get("ok") or not second.get("ok"):
            raise RuntimeError("paper_exit_engine_unavailable")
        with _stage("evidence"):
            evidence = _evidence(namespace, user_id, bot_id, market_id,
                                 float(initial_cash), float(initial_qty), live_calls,
                                 **({"symbol": symbol} if review_chain else {}))
        result = check_paper_exit(evidence)
        if result["result"] != "PASS":
            return {**result, "rendered_ui_checked": False,
                    "gate_status": "FAIL", "engine_calls": 2,
                    "live_calls": live_calls}
        with _stage("rendered_ui"):
            rendered = asyncio.run(_rendered_exit(user_id, bot_id, evidence["ui_projection"]))
        required_rendered = {
            "rendered_exit_fields_present", "rendered_saved_target",
            "rendered_decision_source_quote", "rendered_decision_fx",
            "rendered_exit_eur_price",
            "rendered_exit_quantity", "rendered_exit_proceeds",
            "rendered_exit_source_quote", "rendered_exit_fx", "rendered_conversion",
        }
        if not all(
            rendered.get(key) is True for key in required_rendered
        ):
            failed_checks = ([rendered["rendered_failure_reason"]]
                             if rendered.get("rendered_failure_reason") else sorted(
                                 key for key in required_rendered if rendered.get(key) is not True
                             ))
            return {"result": "FAIL", "failed_checks": failed_checks,
                    **({"browser_diagnostic": rendered["ui_diagnostic"]}
                       if rendered.get("ui_diagnostic") else {}),
                    "rendered_ui_checked": True, "gate_status": "FAIL",
                "engine_calls": 2, "live_calls": live_calls,
                "onboarding_navigation_override": True}
        parity = None
        if source_parity:
            from backend.scripts.probe_protected_source_time_parity import run as check_source_parity
            from backend.scripts.probe_protected_account_answer import _business_state
            with _stage("source_parity"):
                before_readback = _business_state(user_id)
                with _guard_live_exchange() as parity_live_attempts:
                    parity = check_source_parity(
                        user_id=user_id, market_id=market_id,
                        paper_evidence=evidence, frozen_ref=context.get("source_ref"),
                    )
                after_readback = _business_state(user_id)
            live_calls += len(parity_live_attempts)
            safety_failures = []
            if parity_live_attempts:
                safety_failures.append("live_execution_attempt")
            if (before_readback["counts"] != after_readback["counts"]
                    or before_readback["fingerprints"] != after_readback["fingerprints"]):
                safety_failures.append("unexpected_business_write")
            if safety_failures:
                return {"result": "FAIL", "failed_checks": safety_failures,
                        "rendered_ui_checked": True, "gate_status": "FAIL",
                        "engine_calls": 2, "live_calls": live_calls,
                        "onboarding_navigation_override": True}
            if parity["result"] != "PASS":
                status = "INCONCLUSIVE" if parity["result"] == "INCONCLUSIVE" else "FAIL"
                return {"result": status, "failed_checks": parity["failed_checks"],
                        "source_time_parity": parity, "rendered_ui_checked": True,
                        "gate_status": status, "engine_calls": 2,
                        "live_calls": live_calls, "onboarding_navigation_override": True}
        review_result = None
        if review_chain:
            with _stage("review_chain"):
                review_result = asyncio.run(_review_chain(user_id, bot_id, evidence["ui_projection"]))
        passed = True
        return {**result, "exit_decisions": 1, "replay_duplicate_sells": 0,
                "engine_calls": 2, "live_calls": live_calls,
                "rendered_ui_checked": True,
                "onboarding_navigation_override": True,
                **({"review_chain": review_result} if review_result is not None else {}),
                **({"fixture_quote_source": "process_local_synthetic_usd_fx"} if review_chain else {}),
                **({"source_time_parity": parity} if parity is not None else {}),
                "gate_status": "PASS"}
    finally:
        if user_id is not None and bot_id is not None:
            if passed:
                fixture._cleanup(namespace, user_id, bot_id)
                if review_chain:
                    _assert_fixture_absent(user_id)
            else:
                fixture._quarantine(namespace, user_id, bot_id)
