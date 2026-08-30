"""PostgreSQL regression for the canonical indicator context contract.

Run explicitly with FINN_V2_PG_INTEGRATION=1 against the disposable database
after the deploy migration sequence has been applied.
"""

from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import text


pytestmark = pytest.mark.skipif(
    os.getenv("FINN_V2_PG_INTEGRATION") != "1",
    reason="requires a disposable PostgreSQL database",
)


def test_canonical_context_graph_reads_migrated_indicator_configuration_without_undefined_column():
    asyncio.run(_build_personal_context_graph())


async def _build_personal_context_graph() -> None:
    from backend.infrastructure.database import async_session_factory
    from backend.infrastructure.repositories.assistant_context_repository import AssistantContextRepository

    async with async_session_factory() as session:
        metadata = await session.execute(
            text(
                """
                SELECT udt_name, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'user_indicator_configs'
                  AND column_name = 'config_json'
                """
            )
        )
        assert metadata.one() == ("jsonb", "NO", "'{}'::jsonb")

        fixture_user_id = os.getenv("FINN_V2_PG_TEST_USER_ID")
        user_id = await session.scalar(
            text("SELECT id FROM users WHERE id = :user_id")
            if fixture_user_id
            else text("SELECT id FROM users ORDER BY id LIMIT 1"),
            {"user_id": int(fixture_user_id)} if fixture_user_id else {},
        )
        if user_id is None:
            pytest.skip("disposable schema has no user fixture")
        graph = await AssistantContextRepository(session).build_canonical_context_graph(
            user_id=int(user_id),
            query="Welke indicatoren gebruik ik voor mijn persoonlijke plan?",
            request_context={"symbol": "BTC"},
        )

    assert graph["asset"] == "BTC"
    assert "indicators" in graph
