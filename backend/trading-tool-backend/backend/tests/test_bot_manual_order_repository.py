"""Exercise the manual-order repository against the real bot_orders column contract."""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import create_engine, event, text

from backend.infrastructure.repositories.bot_repository import BotRepository


def test_paper_order_insert_and_replay_use_canonical_bot_orders_columns():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _sqlite_now(connection, _record):
        connection.create_function("NOW", 0, lambda: datetime.now(timezone.utc).isoformat())

    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE bot_orders (
                id INTEGER PRIMARY KEY, user_id INTEGER, bot_id INTEGER,
                decision_id INTEGER, symbol TEXT, side TEXT, order_type TEXT,
                quote_amount_eur NUMERIC, estimated_price_eur NUMERIC,
                estimated_qty NUMERIC, executed_price_eur NUMERIC,
                executed_qty NUMERIC, status TEXT, created_at TEXT,
                updated_at TEXT, idempotency_key TEXT,
                execution_environment TEXT, exchange_name TEXT, exchange_order_id TEXT
            )
        """))
        connection.execute(text("""
            CREATE UNIQUE INDEX uq_manual_order_owner_key
            ON bot_orders(user_id, idempotency_key)
            WHERE idempotency_key IS NOT NULL
        """))

        class Session:
            async def execute(self, query, parameters):
                return connection.execute(query, parameters)

        repo = BotRepository(Session())

        async def exercise():
            first = await repo.create_manual_order(
                7, 9, "BTC", "buy", 0.9975, 100,
                idempotency_key="same-paper-order", quote_amount_eur=100, status="filled",
            )
            second = await repo.create_manual_order(
                7, 9, "BTC", "buy", 0.9975, 100,
                idempotency_key="same-paper-order", quote_amount_eur=100, status="filled",
            )
            row = await repo.get_manual_order_by_idempotency_key(7, "same-paper-order")
            return first, second, row

        first, second, row = asyncio.run(exercise())
        assert first == (second[0], True)
        assert second == (first[0], False)
        assert row["quantity"] == 0.9975
        assert row["limit_price"] == 100
        assert row["quote_amount_eur"] == 100
        stored = connection.execute(text("""
            SELECT executed_qty, executed_price_eur, status FROM bot_orders WHERE id=:id
        """), {"id": first[0]}).one()
        assert tuple(stored) == (0.9975, 100, "filled")
