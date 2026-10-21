"""Owner isolation for populated trade reviews on a disposable, migrated database.

Run with FINN_REVIEW_OWNER_PG_INTEGRATION=1 and the local FINN database env.
Set FINN_REVIEW_OWNER_PG_DISPOSABLE_PORT to DB_PORT and
FINN_REVIEW_OWNER_PG_DB_MARKER to a unique database comment created in the
disposable database with COMMENT ON DATABASE finn_local IS '<unique marker>'.
First bootstrap the local FINN schema and apply all deploy migrations. Then
run this file with pytest using the same local DB_* values and marker. The
guard rejects an unmarked target before fixture writes.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import text


pytestmark = pytest.mark.skipif(
    os.getenv("FINN_REVIEW_OWNER_PG_INTEGRATION") != "1",
    reason="requires the disposable local FINN PostgreSQL database",
)


def test_populated_review_list_and_detail_are_owner_scoped(monkeypatch):
    if (
        os.getenv("APP_ENV") != "local_finn"
        or os.getenv("DB_HOST") not in {"127.0.0.1", "localhost", "::1"}
        or os.getenv("DB_NAME") != "finn_local"
        or os.getenv("DB_USER") != "finn_local"
        or not os.getenv("FINN_REVIEW_OWNER_PG_DISPOSABLE_PORT")
        or os.getenv("DB_PORT") != os.getenv("FINN_REVIEW_OWNER_PG_DISPOSABLE_PORT")
        or not os.getenv("FINN_REVIEW_OWNER_PG_DB_MARKER")
    ):
        raise RuntimeError("review owner integration requires an explicitly marked disposable local database")
    monkeypatch.setenv("FINN_TRADE_REVIEW_ROLLOUT", "all")
    asyncio.run(_exercise_owner_isolation())


async def _exercise_owner_isolation():
    from backend.infrastructure.database import async_session_factory, engine
    from backend.main import app
    from backend.services.finn_trade_review_service import completed_reflection_week
    from backend.utils.auth_utils import create_token

    marker = uuid.uuid4().hex
    _, _, week_start, _ = completed_reflection_week()
    exit_at = week_start + timedelta(days=1)
    owners: list[tuple[int, str]] = []
    reviews: list[list[int]] = []
    try:
        async with async_session_factory() as session:
            actual_marker = await session.scalar(text("""
                SELECT pg_catalog.shobj_description(oid, 'pg_database')
                FROM pg_database WHERE datname=current_database()
            """))
            if actual_marker != os.environ["FINN_REVIEW_OWNER_PG_DB_MARKER"]:
                raise RuntimeError("review owner integration database marker mismatch")
            for index, symbol in enumerate(("XRP", "ADA"), start=1):
                email = f"review-owner-{marker}-{index}@example.invalid"
                user_id = await session.scalar(text("""
                    INSERT INTO users (email, password_hash, role, is_active)
                    VALUES (:email, 'unusable-disposable-fixture', 'user', TRUE) RETURNING id
                """), {"email": email})
                owner_reviews = []
                for review_number in range(1, index + 1):
                    review_id = await session.scalar(text("""
                    INSERT INTO finn_trade_reviews (
                        user_id, bot_id, symbol, execution_environment,
                        opening_ledger_id, closing_ledger_id, entry_at, exit_at,
                        entry_qty, entry_value_eur, exit_value_eur,
                        entry_price_eur, exit_price_eur, pnl_eur_before_fees,
                        base_currency, fills, note, analysis_status, candles_status
                    ) VALUES (
                        :user_id, :bot_id, :symbol, 'paper',
                        :opening_ledger_id, :closing_ledger_id, :entry_at, :exit_at,
                        1, 100, 110, 100, 110, 10,
                        'EUR', '[]'::jsonb, :note, 'unavailable', 'unavailable'
                    ) RETURNING id
                    """), {
                        "user_id": user_id, "bot_id": index,
                        "symbol": symbol,
                        "opening_ledger_id": -(index * 10 + review_number * 2),
                        "closing_ledger_id": -(index * 10 + review_number * 2 + 1),
                        "entry_at": exit_at - timedelta(hours=1),
                        "exit_at": exit_at + timedelta(minutes=review_number),
                        "note": f"private-{symbol}-{review_number}-{marker}",
                    })
                    owner_reviews.append(review_id)
                owners.append((user_id, email))
                reviews.append(owner_reviews)
            await session.commit()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver",
        ) as client:
            for index, (user_id, _) in enumerate(owners):
                token = create_token(
                    {"sub": str(user_id), "role": "user"},
                    timedelta(minutes=5), "access",
                )
                headers = {"Authorization": f"Bearer {token}"}
                listing = await client.get("/api/bot/trade-reviews", headers=headers)
                assert listing.status_code == 200, listing.text
                payload = listing.json()
                assert payload["total"] == index + 1
                assert payload["weekly"]["trades"] == index + 1
                assert {item["id"] for item in payload["items"]} == set(reviews[index])
                symbol = ("XRP", "ADA")[index]
                assert {item["note"] for item in payload["items"]} == {
                    f"private-{symbol}-{number}-{marker}"
                    for number in range(1, index + 2)
                }
                assert all(item["symbol"] == symbol for item in payload["items"])

                own = await client.get(f"/api/bot/trade-reviews/{reviews[index][0]}", headers=headers)
                assert own.status_code == 200, own.text
                assert own.json()["id"] == reviews[index][0]
                assert own.json()["note"] == f"private-{symbol}-1-{marker}"
                foreign = await client.get(
                    f"/api/bot/trade-reviews/{reviews[1 - index][0]}", headers=headers,
                )
                assert foreign.status_code == 404
                assert marker not in foreign.text
    finally:
        try:
            if owners:
                async with async_session_factory() as cleanup:
                    for user_id, email in owners:
                        await cleanup.execute(
                            text("DELETE FROM users WHERE id=:id AND email=:email"),
                            {"id": user_id, "email": email},
                        )
                    await cleanup.commit()
        finally:
            await engine.dispose()
