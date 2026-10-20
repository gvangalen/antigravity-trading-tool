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
        if analyze_pending_trade_reviews.run() != 1:
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
