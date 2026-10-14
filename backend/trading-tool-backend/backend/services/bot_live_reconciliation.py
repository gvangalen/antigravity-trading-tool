"""Book confirmed exchange fills incrementally and finalize terminal orders."""

import asyncio
import logging
import math
from typing import Optional

from backend.ai_agents.trading_bot_agent import record_bot_ledger_entry
from backend.services.exchange_service import ExchangeService
from backend.utils.db import get_db_connection

logger = logging.getLogger(__name__)
TERMINAL_STATUSES = {"closed", "canceled", "cancelled", "expired", "rejected"}


def _fetch_exchange_order(conn, row: dict) -> dict:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT api_key, api_secret, api_passphrase
            FROM exchange_keys
            WHERE user_id=%s AND exchange_name=%s AND is_active=TRUE
            LIMIT 1
        """, (row["user_id"], row["exchange_name"]))
        credentials = cur.fetchone()
    if not credentials:
        raise RuntimeError("Exchange connection is no longer active")

    async def fetch():
        client = await ExchangeService.get_client(row["exchange_name"], *credentials)
        return await ExchangeService.fetch_order(
            client, row["exchange_order_id"], row["exchange_symbol"] or row["symbol"]
        )

    return asyncio.run(fetch())


def reconcile_live_orders(*, user_id: Optional[int] = None, order_id: Optional[int] = None, limit: int = 100) -> dict:
    conn = get_db_connection()
    processed = 0
    settled = 0
    errors = 0
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, user_id, bot_id, decision_id, symbol, side, exchange_name,
                       exchange_order_id, exchange_symbol, COALESCE(estimated_qty, quantity) AS submitted_qty, estimated_price_eur,
                       executed_qty, executed_price_eur
                FROM bot_orders
                WHERE execution_environment='live' AND status='sent'
                  AND exchange_order_id IS NOT NULL
                  AND (%s IS NULL OR user_id=%s)
                  AND (%s IS NULL OR id=%s)
                ORDER BY created_at ASC LIMIT %s
            """, (user_id, user_id, order_id, order_id, max(1, min(limit, 200))))
            rows = [dict(zip(
                ("id", "user_id", "bot_id", "decision_id", "symbol", "side", "exchange_name",
                 "exchange_order_id", "exchange_symbol", "submitted_qty", "estimated_price_eur",
                 "executed_qty", "executed_price_eur"), value
            )) for value in cur.fetchall()]
        conn.commit()

        for row in rows:
            processed += 1
            try:
                exchange_order = _fetch_exchange_order(conn, row)
                status = str(exchange_order.get("status") or "").lower()
                terminal = status in TERMINAL_STATUSES
                if status not in TERMINAL_STATUSES and status not in {"open", "partial"}:
                    conn.rollback()
                    continue
                raw_filled = exchange_order.get("filled")
                if raw_filled is None:
                    raise RuntimeError("Exchange returned order without filled quantity")
                filled_qty = float(raw_filled)
                if not math.isfinite(filled_qty) or filled_qty < 0:
                    raise RuntimeError("Exchange returned invalid filled quantity")
                requested_qty = float(row["submitted_qty"] or 0)
                if not math.isfinite(requested_qty) or requested_qty <= 0 or filled_qty > requested_qty + max(1e-10, requested_qty * 1e-6):
                    raise RuntimeError("Exchange filled quantity exceeds submitted order")
                if status == "closed" and filled_qty == 0:
                    raise RuntimeError("Exchange returned closed order without a fill")
                avg_price = None
                if filled_qty > 0:
                    average = exchange_order.get("average")
                    cost = exchange_order.get("cost")
                    avg_price = float(average) if average is not None else (
                        float(cost) / filled_qty if cost is not None else None
                    )
                    if avg_price is None or not math.isfinite(avg_price) or avg_price <= 0:
                        raise RuntimeError("Exchange returned fill without an actual average or cost")
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT status, COALESCE(executed_qty, 0), executed_price_eur
                        FROM bot_orders
                        WHERE id=%s AND user_id=%s AND bot_id=%s FOR UPDATE
                    """, (row["id"], row["user_id"], row["bot_id"]))
                    locked = cur.fetchone()
                    if not locked or locked[0] != "sent":
                        conn.rollback()
                        continue
                    prior_qty = float(locked[1] or 0)
                    prior_avg = float(locked[2] or 0)
                    if filled_qty < prior_qty - 1e-10:
                        raise RuntimeError("Exchange cumulative fill decreased")
                    new_qty = max(0.0, filled_qty - prior_qty)
                    if new_qty > 1e-10:
                        cumulative_cash = round(filled_qty * avg_price, 2)
                        prior_cash = round(prior_qty * prior_avg, 2)
                        cash = round(cumulative_cash - prior_cash, 2)
                        if cash <= 0:
                            raise RuntimeError("Exchange cumulative fill cost did not increase")
                        cur.execute("""
                            SELECT COALESCE(MAX(fill_sequence), -1) + 1
                            FROM bot_ledger
                            WHERE user_id=%s AND order_id=%s AND entry_type='execute'
                        """, (row["user_id"], row["id"]))
                        fill_sequence = int(cur.fetchone()[0])
                        side = str(row["side"] or "buy").lower()
                        record_bot_ledger_entry(
                            conn=conn, user_id=row["user_id"], bot_id=row["bot_id"],
                            decision_id=row["decision_id"], order_id=row["id"],
                            entry_type="execute", symbol=row["symbol"],
                            cash_delta_eur=-cash if side == "buy" else cash,
                            qty_delta=new_qty if side == "buy" else -new_qty,
                            price_eur=cash / new_qty, note="Exchange confirmed fill",
                            fill_sequence=fill_sequence,
                            meta={"exchange_order_id": row["exchange_order_id"], "exchange_status": status,
                                  "cumulative_filled_qty": filled_qty},
                        )
                    if not terminal and new_qty <= 1e-10:
                        conn.rollback()
                        continue
                    final_status = (
                        "filled" if status == "closed" and filled_qty > 0 else
                        "partial" if terminal and filled_qty > 0 else
                        "cancelled" if terminal else "sent"
                    )
                    cur.execute("""
                        UPDATE bot_orders SET status=%s, executed_qty=%s, executed_price_eur=%s,
                          updated_at=NOW() WHERE id=%s AND user_id=%s
                    """, (final_status, filled_qty, avg_price, row["id"], row["user_id"]))
                    cur.execute("""
                        INSERT INTO bot_executions
                          (user_id, bot_order_id, status, filled_qty, avg_fill_price, created_at, updated_at)
                        VALUES (%s,%s,%s,%s,%s,NOW(),NOW())
                        ON CONFLICT (user_id, bot_order_id) DO UPDATE SET
                          status=EXCLUDED.status, filled_qty=EXCLUDED.filled_qty,
                          avg_fill_price=EXCLUDED.avg_fill_price, updated_at=NOW()
                    """, (row["user_id"], row["id"],
                          "partial" if not terminal else final_status, filled_qty, avg_price))
                    if row["decision_id"] and terminal:
                        cur.execute("""
                            UPDATE bot_decisions SET status=%s,
                              executed_at=CASE WHEN %s > 0 THEN NOW() ELSE executed_at END,
                              updated_at=NOW()
                            WHERE id=%s AND user_id=%s AND bot_id=%s
                        """, ("executed" if filled_qty > 0 else "failed_execution", filled_qty,
                              row["decision_id"], row["user_id"], row["bot_id"]))
                conn.commit()
                if terminal:
                    settled += 1
            except Exception as exc:
                conn.rollback()
                errors += 1
                logger.error("Could not reconcile live bot order %s (%s)", row["id"], type(exc).__name__)
        return {"processed": processed, "settled": settled, "errors": errors}
    finally:
        conn.close()
