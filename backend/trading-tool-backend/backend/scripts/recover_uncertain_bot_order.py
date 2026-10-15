"""Operator-only recovery for a live order whose exchange submission is uncertain.

Run after inspecting the exchange account and recording the evidence in an
incident ticket. This script never submits an exchange order. The attach path
fetches the supplied exchange order and leaves fill booking to the reconciler.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.bot_live_reconciliation import is_expected_eur_pair, reconcile_live_orders
from backend.services.exchange_service import ExchangeService
from backend.utils.db import get_db_connection

UNCERTAIN_STATUSES = ("sending", "unknown_exchange_state")


def _read_order(conn, user_id: int, order_id: int) -> dict:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT user_id, id, bot_id, decision_id, symbol, side,
                   COALESCE(estimated_qty, quantity),
                   COALESCE(estimated_price_eur, limit_price), exchange_name,
                   exchange_order_id, status
            FROM bot_orders
            WHERE user_id=%s AND id=%s AND execution_environment='live'
        """, (user_id, order_id))
        row = cur.fetchone()
    if not row:
        raise ValueError("Live order not found for this user and order ID")
    keys = ("user_id", "id", "bot_id", "decision_id", "symbol", "side",
            "quantity", "price", "exchange_name", "exchange_order_id", "status")
    return dict(zip(keys, row))


def _fetch_verified_exchange_order(conn, row: dict, exchange_order_id: str) -> dict:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT api_key, api_secret, api_passphrase
            FROM exchange_keys
            WHERE user_id=%s AND exchange_name=%s AND is_active=TRUE
            LIMIT 1
        """, (row["user_id"], row["exchange_name"]))
        credentials = cur.fetchone()
    if not credentials:
        raise ValueError("The order's exchange connection is not active")

    async def fetch():
        client = await ExchangeService.get_client(row["exchange_name"], *credentials)
        return await ExchangeService.fetch_order(client, exchange_order_id, row["symbol"])

    order = asyncio.run(fetch())
    if not isinstance(order, dict) or str(order.get("id") or "") != exchange_order_id:
        raise ValueError("Exchange order ID could not be verified")
    if not is_expected_eur_pair(order.get("symbol"), row["symbol"]):
        raise ValueError("Exchange order EUR pair differs from local order")
    if str(order.get("side") or "").lower() != str(row["side"]).lower():
        raise ValueError("Exchange order side differs from local order")
    try:
        amount = float(order.get("amount"))
        expected = float(row["quantity"])
        price = float(order.get("price"))
        expected_price = float(row["price"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Exchange order amount is missing") from exc
    if not math.isfinite(amount) or abs(amount - expected) > max(1e-10, expected * 1e-6):
        raise ValueError("Exchange order amount differs from local order")
    if not math.isfinite(price) or abs(price - expected_price) > max(0.01, expected_price * 1e-4):
        raise ValueError("Exchange order limit price differs from local order")
    return order


def recover_order(*, user_id: int, order_id: int, action: str,
                  exchange_order_id: str | None, operator_id: str,
                  evidence_reference: str, confirmation: str) -> dict:
    if not operator_id.strip() or not evidence_reference.strip():
        raise ValueError("Operator ID and evidence reference are required")
    if len(operator_id) > 128 or len(evidence_reference) > 512:
        raise ValueError("Operator ID or evidence reference is too long")
    if action == "attach_exchange_order":
        if not exchange_order_id or confirmation != "I VERIFIED THIS EXCHANGE ORDER":
            raise ValueError("Verified exchange order ID and confirmation are required")
    elif action == "verified_no_order":
        if exchange_order_id or confirmation != "I VERIFIED NO EXCHANGE ORDER":
            raise ValueError("Confirm no order exists at the exchange before clearing the block")
    else:
        raise ValueError("Unknown recovery action")

    conn = get_db_connection()
    if conn is None:
        raise RuntimeError("Database connection unavailable")
    try:
        row = _read_order(conn, user_id, order_id)
        if row["status"] not in UNCERTAIN_STATUSES or row["exchange_order_id"]:
            raise ValueError("Order is no longer an uncertain submission without an exchange ID")
        exchange_order = None
        if action == "attach_exchange_order":
            exchange_order = _fetch_verified_exchange_order(conn, row, exchange_order_id)
        conn.rollback()

        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s, 0)", (user_id,))
            cur.execute("""
                SELECT status, exchange_order_id, exchange_name, symbol, side,
                       COALESCE(estimated_qty, quantity),
                       COALESCE(estimated_price_eur, limit_price), decision_id
                FROM bot_orders WHERE user_id=%s AND id=%s
                  AND execution_environment='live' FOR UPDATE
            """, (user_id, order_id))
            locked = cur.fetchone()
            if (not locked or locked[0] not in UNCERTAIN_STATUSES or locked[1]
                    or locked[2] != row["exchange_name"] or locked[3] != row["symbol"]
                    or locked[4] != row["side"] or float(locked[5]) != float(row["quantity"])
                    or float(locked[6]) != float(row["price"])):
                raise ValueError("Order changed during exchange verification; review it again")
            if action == "attach_exchange_order":
                cur.execute("""
                    SELECT id FROM bot_orders
                    WHERE user_id=%s AND exchange_name=%s AND exchange_order_id=%s AND id<>%s
                    LIMIT 1
                """, (user_id, row["exchange_name"], exchange_order_id, order_id))
                if cur.fetchone():
                    raise ValueError("Exchange order ID is already linked to another local order")
            if action == "attach_exchange_order":
                cur.execute("""
                    UPDATE bot_orders SET exchange_order_id=%s, exchange_symbol=%s,
                        status='sent', updated_at=NOW()
                    WHERE user_id=%s AND id=%s
                """, (exchange_order_id, exchange_order["symbol"], user_id, order_id))
                if locked[7]:
                    cur.execute("""
                        UPDATE bot_decisions SET status='awaiting_exchange', updated_at=NOW()
                        WHERE user_id=%s AND id=%s AND bot_id=%s
                    """, (user_id, locked[7], row["bot_id"]))
            else:
                cur.execute("""
                    UPDATE bot_orders SET status='rejected', updated_at=NOW()
                    WHERE user_id=%s AND id=%s
                """, (user_id, order_id))
                if locked[7]:
                    cur.execute("""
                        UPDATE bot_decisions SET status='failed_execution', updated_at=NOW()
                        WHERE user_id=%s AND id=%s AND bot_id=%s
                    """, (user_id, locked[7], row["bot_id"]))
            cur.execute("""
                INSERT INTO bot_order_recovery_events
                    (user_id, order_id, action, exchange_order_id, operator_id, evidence_reference)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (user_id, order_id, action, exchange_order_id,
                  operator_id.strip(), evidence_reference.strip()))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    result = {"order_id": order_id, "action": action, "status": "sent" if exchange_order_id else "rejected"}
    if exchange_order_id:
        result["reconciliation"] = reconcile_live_orders(user_id=user_id, order_id=order_id)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--order-id", type=int, required=True)
    parser.add_argument("--action", choices=("attach_exchange_order", "verified_no_order"), required=True)
    parser.add_argument("--exchange-order-id")
    parser.add_argument("--operator-id", required=True)
    parser.add_argument("--evidence-reference", required=True)
    parser.add_argument("--confirmation", required=True)
    args = parser.parse_args()
    if args.user_id <= 0 or args.order_id <= 0:
        parser.error("User and order IDs must be positive")
    print(recover_order(**vars(args)))


if __name__ == "__main__":
    main()
