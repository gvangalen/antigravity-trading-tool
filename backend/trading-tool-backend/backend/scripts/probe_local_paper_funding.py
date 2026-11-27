"""Isolated DB probe for owner-funded Paper cash and its order race.

Run only after ops/local-finn/finn-local.sh start and matrix have prepared the
synthetic local database and a BTC/EUR market. This never calls a broker.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text

from backend.infrastructure.database import async_session_factory
from backend.infrastructure.repositories.paper_reserve_repository import PaperReserveRepository
from backend.services.paper_discretionary_order_service import PaperDiscretionaryOrderService
from backend.services.portfolio_snapshot_service import snapshot_all_for_user


def _require_local() -> None:
    if (os.getenv("APP_ENV") != "local_finn"
            or os.getenv("DB_HOST") not in {"127.0.0.1", "localhost"}
            or os.getenv("FINN_LOCAL_SAFE_ADAPTERS") != "1"):
        raise SystemExit("paper_funding_probe_requires_isolated_local_finn")


async def _quote(market_id: int, _asset: str, _currency: str) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "market_id": market_id, "asset": "BTC", "quote_currency": "EUR",
        "market_fx_eur_per_unit": Decimal("1"),
        "market_price_eur": Decimal("50000"),
        "market_price": Decimal("50000"),
        "market_price_at": now, "market_fx_as_of": now,
    }


async def _main() -> None:
    _require_local()
    email = f"paper-funding-probe-{uuid4().hex}@example.test"
    async with async_session_factory() as db:
        market_id = (await db.execute(text("""
            SELECT id FROM trading_markets
            WHERE asset_symbol='BTC' AND quote_currency='EUR'
              AND venue='BINANCE' AND is_active=TRUE LIMIT 1
        """))).scalar_one_or_none()
        if market_id is None:
            raise SystemExit("paper_funding_probe_requires_local_btc_eur_market")
        user_id = (await db.execute(text("""
            INSERT INTO users (email, password_hash, role, is_active)
            VALUES (:email, 'no-login', 'user', TRUE) RETURNING id
        """), {"email": email})).scalar_one()
        await db.commit()

    try:
        async with async_session_factory() as db:
            reserve = PaperReserveRepository(db)
            added = await reserve.fund(user_id=user_id, direction="add",
                                       amount_eur=Decimal("1250.00"),
                                       idempotency_key="probe-botless-add")
            await db.commit()
            replay = await reserve.fund(user_id=user_id, direction="add",
                                        amount_eur=Decimal("1250.00"),
                                        idempotency_key="probe-botless-add")
            await db.commit()
            assert not added["replayed"] and replay["replayed"]
            try:
                await reserve.fund(user_id=user_id, direction="add",
                                   amount_eur=Decimal("1250.01"),
                                   idempotency_key="probe-botless-add")
            except ValueError as exc:
                assert str(exc) == "paper_funding_key_reused"
                await db.rollback()
            else:
                raise AssertionError("funding key reused with a different amount")
            assert await reserve.cash(user_id) == Decimal("1250.00")
        snapshot_all_for_user(user_id)

        async with async_session_factory() as db:
            reserve = PaperReserveRepository(db)
            await reserve.fund(user_id=user_id, direction="remove",
                               amount_eur=Decimal("1250.00"),
                               idempotency_key="probe-botless-remove")
            await db.commit()
        snapshot_all_for_user(user_id)
        async with async_session_factory() as db:
            point = (await db.execute(text("""
                SELECT equity_eur, cash_eur, position_value_eur, covered_bot_count
                FROM portfolio_value_snapshots_v2
                WHERE user_id=:user_id AND environment='paper' AND bucket='1h'
                ORDER BY ts DESC LIMIT 1
            """), {"user_id": user_id})).one()
            assert tuple(point) == (Decimal("0"), Decimal("0"), Decimal("0"), 0)
            reserve = PaperReserveRepository(db)
            try:
                await reserve.fund(user_id=user_id, direction="remove",
                                   amount_eur=Decimal("0.01"),
                                   idempotency_key="probe-overdraw")
            except ValueError as exc:
                assert str(exc) == "paper_funding_insufficient_reserve"
                await db.rollback()
            else:
                raise AssertionError("empty reserve overdraft accepted")
            await reserve.fund(user_id=user_id, direction="add",
                               amount_eur=Decimal("100.00"),
                               idempotency_key="probe-race-add")
            await db.commit()
            order = PaperDiscretionaryOrderService(db)
            order._quote = lambda asset, currency: _quote(market_id, asset, currency)
            preview = await order.preview(user_id=user_id, asset="BTC",
                                          quote_currency="EUR", amount_quote="80",
                                          idempotency_key="probe-race-order")
            assert preview["ok"]

        async def withdraw() -> str:
            async with async_session_factory() as db:
                try:
                    await PaperReserveRepository(db).fund(
                        user_id=user_id, direction="remove",
                        amount_eur=Decimal("80.00"),
                        idempotency_key="probe-race-remove")
                    await db.commit()
                    return "removed"
                except ValueError:
                    await db.rollback()
                    return "blocked"

        async def buy() -> str:
            async with async_session_factory() as db:
                order = PaperDiscretionaryOrderService(db)
                order._quote = lambda asset, currency: _quote(market_id, asset, currency)
                try:
                    await order.execute(user_id=user_id, asset="BTC",
                                        quote_currency="EUR", amount_quote="80",
                                        idempotency_key="probe-race-order",
                                        preview_token=preview["preview_token"])
                    return "filled"
                except HTTPException:
                    await db.rollback()
                    return "blocked"

        outcomes = await asyncio.gather(withdraw(), buy())
        assert outcomes.count("blocked") == 1, outcomes
        async with async_session_factory() as db:
            assert await PaperReserveRepository(db).cash(user_id) == Decimal("20.00")
            assert (await db.execute(text("""
                SELECT COUNT(*) FROM bot_ledger WHERE user_id=:user_id
            """), {"user_id": user_id})).scalar_one() == 0
            assert (await db.execute(text("""
                SELECT COUNT(*) FROM paper_reserve_funding
                WHERE user_id=:user_id AND idempotency_key='probe-race-remove'
            """), {"user_id": user_id})).scalar_one() + (await db.execute(text("""
                SELECT COUNT(*) FROM paper_discretionary_orders
                WHERE user_id=:user_id AND idempotency_key='probe-race-order'
            """), {"user_id": user_id})).scalar_one() == 1
        print("paper_funding_local_probe: add, replay, key reuse, zero history, overdraft, concurrent order PASS")
    finally:
        async with async_session_factory() as db:
            await db.execute(text("DELETE FROM users WHERE id=:user_id"),
                             {"user_id": user_id})
            await db.commit()


if __name__ == "__main__":
    asyncio.run(_main())
