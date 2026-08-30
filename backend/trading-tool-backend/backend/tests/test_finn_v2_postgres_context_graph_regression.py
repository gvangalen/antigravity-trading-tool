"""PostgreSQL regression for the canonical indicator context contract.

Run explicitly with FINN_V2_PG_INTEGRATION=1 against the disposable database
after the deploy migration sequence has been applied.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from sqlalchemy import text


pytestmark = pytest.mark.skipif(
    os.getenv("FINN_V2_PG_INTEGRATION") != "1",
    reason="requires a disposable PostgreSQL database",
)


def test_canonical_context_graph_reads_migrated_indicator_configuration_without_undefined_column():
    asyncio.run(_run_with_fresh_asyncpg_pool(_build_personal_context_graph()))


def test_degraded_lineage_survives_a_fresh_postgresql_session_for_safe_reformulation():
    asyncio.run(_run_with_fresh_asyncpg_pool(_reload_degraded_lineage()))


async def _run_with_fresh_asyncpg_pool(coroutine) -> None:
    """Do not leave asyncpg transports attached to this test's closed loop."""
    from backend.infrastructure.database import engine

    try:
        await coroutine
    finally:
        await engine.dispose()


async def _build_personal_context_graph() -> None:
    from backend.infrastructure.database import async_session_factory
    from backend.infrastructure.repositories.assistant_context_repository import AssistantContextRepository
    from backend.infrastructure.repositories.technical_data_repository import TechnicalDataRepository

    fixture_indicator = f"finn_qa_{uuid.uuid4().hex[:12]}"
    user_id = None
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
        await TechnicalDataRepository(session).ensure_user_config(
            int(user_id), fixture_indicator, category="technical", symbol="BTC", asset_class="crypto"
        )
        await session.commit()
        graph = await AssistantContextRepository(session).build_canonical_context_graph(
            user_id=int(user_id),
            query="Welke indicatoren gebruik ik voor mijn persoonlijke plan?",
            request_context={"symbol": "BTC"},
        )

    try:
        assert graph["asset"] == "BTC"
        assert fixture_indicator in graph["indicators"]["technical"]["configured"]
    finally:
        async with async_session_factory() as cleanup_session:
            await cleanup_session.execute(
                text(
                    """
                    DELETE FROM user_indicator_configs
                    WHERE user_id = :user_id AND indicator = :indicator
                      AND category = 'technical' AND symbol = 'BTC'
                    """
                ),
                {"user_id": int(user_id), "indicator": fixture_indicator},
            )
            await cleanup_session.commit()


async def _reload_degraded_lineage() -> None:
    from backend.infrastructure.database import async_session_factory
    from backend.infrastructure.repositories.finn_v2_conversation_repository import FinnV2ConversationRepository
    from backend.services.finn_v2_request_analysis_service import FinnV2RequestAnalysisService

    conversation_id = f"finn-v2-pg-lineage-{uuid.uuid4().hex}"
    async with async_session_factory() as setup_session:
        user_id = await setup_session.scalar(text("SELECT id FROM users ORDER BY id LIMIT 1"))
        if user_id is None:
            pytest.skip("disposable schema has no user fixture")
        repository = FinnV2ConversationRepository(setup_session)
        await repository.create(
            conversation_id=conversation_id,
            user_id=int(user_id),
            context={
                "conversation_state_version": "finn_v2.conversation-contracts.v1",
                "last_degraded_context": {
                    "run_id": "degraded-pg-run-1",
                    "evidence_refs": ["E1"],
                    "released_response": {
                        "direct_answer": "De eerdere beoordeling is begrensd door ontbrekende indicator-evidence.",
                    },
                    "resolved_entities": {"asset": "BTC", "setup_id": 1, "strategy_id": 1, "bot_id": 1},
                },
            },
        )
        await setup_session.commit()

    try:
        async with async_session_factory() as reload_session:
            context = await FinnV2ConversationRepository(reload_session).get_context(
                conversation_id=conversation_id, user_id=int(user_id)
            )
        analysis = FinnV2RequestAnalysisService().analyze(
            message="Vertel hetzelfde oordeel opnieuw in twee eenvoudige zinnen.",
            conversation_context=context,
        )
        assert analysis.request_plan.operation_id == "reformulate_previous_response"
        assert analysis.request_plan.conversation_reference == "degraded-pg-run-1"
        assert analysis.request_plan.conversation_reference_kind == "previous_degraded_response"
    finally:
        async with async_session_factory() as cleanup_session:
            await cleanup_session.execute(
                text("DELETE FROM finn_v2_conversations WHERE id = :conversation_id"),
                {"conversation_id": conversation_id},
            )
            await cleanup_session.commit()
