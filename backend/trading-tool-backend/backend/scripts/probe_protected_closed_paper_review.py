"""Protected QA round trip: two Paper fills, closed dossier and confirmed lesson.

The owner is inactive, has no exchange keys, and is retained disabled as
private QA evidence. This module never opens a Live order or exports IDs.
"""

from __future__ import annotations

import asyncio
import os
from datetime import date, timedelta

from backend.scripts import probe_protected_auto_paper_history as fixture


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
            if len(items) != 1:
                raise RuntimeError("closed_paper_review_not_projected_once")
            review_id = int(items[0]["id"])
            detail = await reviews.get_review(user_id, review_id)
            if (detail.get("execution_environment") != "paper"
                    or len(detail.get("fills") or []) != 2
                    or detail.get("entry_qty") is None
                    or detail.get("pnl_eur_before_fees") is None):
                raise RuntimeError("closed_paper_review_dossier_incomplete")
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
        result = asyncio.run(_read_review(user_id))
        return result
    finally:
        if user_id is not None and bot_id is not None:
            # Preserve this bounded synthetic evidence, but make execution
            # impossible even if dossier projection or readback fails.
            fixture._finish(namespace, user_id, bot_id, passed=False)
