"""Protected QA round trip: two Paper fills, closed dossier and confirmed lesson.

The owner is inactive, has no exchange keys, and is retained disabled as
private QA evidence. This module never opens a Live order or exports IDs.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import contextmanager
from datetime import date, timedelta

from backend.scripts import probe_protected_auto_paper_history as fixture


@contextmanager
def _fixture_review_rollout(user_id: int):
    """Limit this runner process's review jobs to its inactive fixture owner."""
    keys = ("FINN_TRADE_REVIEW_ROLLOUT", "FINN_TRADE_REVIEW_USER_IDS")
    previous = {key: os.environ.get(key) for key in keys}
    try:
        os.environ["FINN_TRADE_REVIEW_ROLLOUT"] = "allowlist"
        os.environ["FINN_TRADE_REVIEW_USER_IDS"] = str(user_id)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _process_review_for_fixture(user_id: int) -> None:
    """Run the production projection/analysis jobs for just this QA owner.

    The regular workers use the deployed rollout allowlist and cannot see a
    newly created inactive fixture child. Calling their actual task bodies
    here avoids treating a one-minute beat delay as a product failure while
    keeping the production workers' rollout unchanged.
    """
    from backend.celery_task.finn_trade_review_task import (
        analyze_pending_trade_reviews, project_dirty_trade_reviews,
    )

    with _fixture_review_rollout(user_id):
        if project_dirty_trade_reviews.run() != 1:
            raise RuntimeError("closed_paper_review_projection_failed")
        with _capture_fixture_ai_errors() as ai_errors:
            analyzed = analyze_pending_trade_reviews.run()
        if ai_errors:
            raise RuntimeError("closed_paper_review_ai_unavailable:" + ai_errors[0])
        if analyzed != 1:
            raise RuntimeError("closed_paper_review_analysis_failed")


def _dossier_incomplete_fields(detail: dict) -> list[str]:
    """Name failed QA checks without disclosing the fixture's trade contents."""
    failed = []
    if detail.get("execution_environment") != "paper":
        failed.append("execution_environment")
    if len(detail.get("fills") or []) != 2:
        failed.append("fill_count")
    if detail.get("entry_qty") is None:
        failed.append("entry_qty")
    if detail.get("pnl_eur_before_fees") is None:
        failed.append("pnl_eur_before_fees")
    status = str(detail.get("analysis_status") or "missing")
    if status != "ready":
        known = {"pending", "running", "failed", "unavailable", "missing"}
        failed.append(f"analysis_status_{status if status in known else 'unknown'}")
    if not detail.get("analysis_json"):
        failed.append("analysis_json")
    return failed


@contextmanager
def _controlled_fixture_paper_quote():
    """Supply only this inactive Paper fixture with a deterministic EUR quote.

    The review probe tests ledger-to-dossier projection, not live market quote
    ingestion. This process-local override is restored before any review read
    or AI task and never changes application workers or market data.
    """
    if os.getenv("FINN_QA_ALLOW_CLOSED_PAPER_REVIEW_FIXTURE") != "1":
        raise RuntimeError("closed_paper_review_fixture_not_authorized")
    from backend.engine import trading_bot_execution as execution

    original = execution._get_live_price

    def paper_quote(conn, symbol: str, max_age_seconds=None):
        if str(symbol).upper() == fixture.SYMBOL and max_age_seconds is None:
            return float(fixture.PRICE_EUR)
        return original(conn, symbol, max_age_seconds)

    try:
        execution._get_live_price = paper_quote
        yield
    finally:
        execution._get_live_price = original


def _safe_ai_error_category(error: object) -> str:
    """Reduce provider/configuration failures to a fixed non-sensitive code."""
    value = str(error or "").casefold()
    if value == "ai_rate_limited":
        return "local_rate_limit"
    if "ai_unavailable_configuration" in value or "api key" in value or "api_key" in value:
        return "configuration"
    if "ai_rate_limited" in value or "429" in value or "rate limit" in value:
        return "rate_limit"
    if "quota" in value or "budget" in value:
        return "quota"
    if "authentication" in value or "401" in value:
        return "authentication"
    if "model" in value and ("not found" in value or "does not exist" in value):
        return "model"
    if "timeout" in value or "timed out" in value:
        return "timeout"
    if "connection" in value or "network" in value:
        return "connection"
    return "provider"


@contextmanager
def _capture_fixture_ai_errors():
    """Observe only safe error categories during this QA process's analysis."""
    from backend.utils import openai_client

    original = openai_client.ask_gpt_json_async
    categories: list[str] = []

    async def capture(*args, **kwargs):
        result = await original(*args, **kwargs)
        if isinstance(result, dict) and result.get("error"):
            categories.append(_safe_ai_error_category(result["error"]))
        return result

    try:
        openai_client.ask_gpt_json_async = capture
        yield categories
    finally:
        openai_client.ask_gpt_json_async = original


def _close_paper_position(user_id: int, bot_id: int, buy_decision_id: int) -> None:
    from backend.engine.trading_bot_execution import _auto_execute_decision, _persist_bot_order

    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT p.position_qty,o.execution_environment,o.status
                   FROM bot_portfolios p JOIN bot_orders o ON o.bot_id=p.bot_id
                   WHERE p.user_id=%s AND p.bot_id=%s AND o.decision_id=%s
                     AND p.symbol='BTC'""",
                (user_id, bot_id, buy_decision_id),
            )
            opened = cur.fetchone()
            if not opened or opened[1:] != ("paper", "filled") or float(opened[0]) <= 0:
                raise RuntimeError("closed_paper_open_fill_missing")
            qty = float(opened[0])
            cur.execute(
                """SELECT strategy_id,setup_id FROM bot_decisions
                   WHERE id=%s AND user_id=%s AND bot_id=%s""",
                (buy_decision_id, user_id, bot_id),
            )
            strategy_id, setup_id = cur.fetchone()
            cur.execute(
                """INSERT INTO bot_decisions
                   (user_id,bot_id,strategy_id,setup_id,symbol,decision_date,
                    action,confidence,amount_eur,status,scores_json)
                   VALUES (%s,%s,%s,%s,'BTC',%s,'sell','high',50,'planned','{}'::jsonb)
                   RETURNING id""",
                (user_id, bot_id, strategy_id, setup_id, date.today()),
            )
            sell_decision_id = int(cur.fetchone()[0])
        # A Paper sell uses a verified current EUR quote; the recorded quantity
        # is exactly the amount opened by the preceding Paper buy.
        order = {"symbol": "BTC", "side": "sell", "quote_amount_eur": 50,
                 "estimated_price": fixture.PRICE_EUR, "estimated_qty": qty}
        _persist_bot_order(conn=conn, user_id=user_id, bot_id=bot_id,
                           decision_id=sell_decision_id, order=order, is_live=False)
        if _auto_execute_decision(conn=conn, user_id=user_id, bot_id=bot_id,
                                  decision_id=sell_decision_id, order=order,
                                  is_live=False, mode="auto") != "filled":
            raise RuntimeError("closed_paper_sell_not_filled")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def _read_review(user_id: int) -> dict:
    from backend.infrastructure.database import async_session_factory, engine
    from backend.services.finn_trade_review_service import FinnTradeReviewService

    try:
        async with async_session_factory() as session:
            reviews = FinnTradeReviewService(session)
            listing = await reviews.list_reviews(user_id, limit=10)
            items = listing.get("items") or []
            if not items:
                raise RuntimeError("closed_paper_review_missing")
            if len(items) != 1:
                raise RuntimeError("closed_paper_review_duplicate")
            review_id = int(items[0]["id"])
            detail = await reviews.get_review(user_id, review_id)
            incomplete_fields = _dossier_incomplete_fields(detail)
            if incomplete_fields:
                raise RuntimeError("closed_paper_review_dossier_incomplete:" + ",".join(incomplete_fields))
            await reviews.set_lesson(user_id, review_id, "Ik controleer mijn exitplan na iedere Paper-trade.")
            reread = await reviews.get_review(user_id, review_id)
            lesson = reread.get("lesson") or {}
            if (lesson.get("status") != "active"
                    or lesson.get("lesson_text") != "Ik controleer mijn exitplan na iedere Paper-trade."):
                raise RuntimeError("closed_paper_lesson_not_readable")
            return {"result": "PASS", "environment": "paper",
                    "closed_positions": 1, "fills": 2,
                    "dossier_readable": True, "lesson_confirmed_and_readable": True}
    finally:
        await engine.dispose()


def run(namespace: str) -> dict:
    if os.getenv("FINN_QA_ALLOW_CLOSED_PAPER_REVIEW_FIXTURE") != "1":
        raise RuntimeError("closed_paper_review_fixture_not_authorized")
    bound = fixture._require_protected_run(namespace)
    user_id = bot_id = None
    try:
        user_id, bot_id, buy_decision_id = fixture._seed(namespace, bound)
        conn = fixture._connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE bot_decisions SET decision_date=%s
                       WHERE id=%s AND user_id=%s AND bot_id=%s AND status='planned'""",
                    (date.today() - timedelta(days=1), buy_decision_id, user_id, bot_id),
                )
                if cur.rowcount != 1:
                    raise RuntimeError("closed_paper_entry_decision_missing")
            conn.commit()
        finally:
            conn.close()
        with _controlled_fixture_paper_quote():
            fixture._execute(user_id, bot_id, buy_decision_id)
            _close_paper_position(user_id, bot_id, buy_decision_id)
        _process_review_for_fixture(user_id)
        result = asyncio.run(_read_review(user_id))
        return result
    finally:
        if user_id is not None and bot_id is not None:
            # Preserve this bounded synthetic evidence, but make execution
            # impossible even if dossier projection or readback fails.
            fixture._finish(namespace, user_id, bot_id, passed=False)
