"""PostgreSQL-only regressions for FINN V2 transaction boundaries.

Run explicitly with FINN_V2_PG_INTEGRATION=1 against a disposable database.
The regular unit suite intentionally remains database-independent.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from sqlalchemy import text

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry


pytestmark = pytest.mark.skipif(
    os.getenv("FINN_V2_PG_INTEGRATION") != "1",
    reason="requires a disposable PostgreSQL database",
)


def test_tool_failure_does_not_rollback_committed_collecting_transition():
    asyncio.run(_run_with_fresh_asyncpg_pool(_run_regression()))


async def _run_with_fresh_asyncpg_pool(coroutine) -> None:
    """Mirror the FINN worker boundary before its asyncio loop closes."""
    from backend.infrastructure.database import engine

    try:
        await coroutine
    finally:
        await engine.dispose()


async def _run_regression() -> None:
    from backend.infrastructure.database import async_session_factory
    from backend.services.finn_v2_tool_execution_service import FinnV2ToolExecutionService

    run_id = f"finn-v2-pg-regression-{uuid.uuid4().hex}"
    async with async_session_factory() as setup_session:
        fixture_user_id = os.getenv("FINN_V2_PG_TEST_USER_ID")
        source = await setup_session.execute(
            text(
                "SELECT id, user_id FROM finn_v2_conversations "
                "WHERE user_id = :user_id ORDER BY created_at LIMIT 1"
            )
            if fixture_user_id
            else text("SELECT id, user_id FROM finn_v2_conversations ORDER BY created_at LIMIT 1"),
            {"user_id": int(fixture_user_id)} if fixture_user_id else {},
        )
        conversation = source.mappings().first()
        if conversation is None:
            pytest.skip("disposable schema has no FINN V2 conversation fixture")
        await setup_session.execute(
            text(
                """
                INSERT INTO finn_v2_runs (
                    id, conversation_id, user_id, request_id, trace_id, idempotency_key,
                    transport, visibility, feature_mode, status, message
                ) VALUES (
                    :id, :conversation_id, :user_id, :request_id, :trace_id, :idempotency_key,
                    'chat', 'shadow', 'shadow', 'collecting', 'PostgreSQL transaction regression'
                )
                """
            ),
            {
                "id": run_id,
                "conversation_id": conversation["id"],
                "user_id": conversation["user_id"],
                "request_id": f"request-{run_id}",
                "trace_id": f"trace-{run_id}",
                "idempotency_key": f"idempotency-{run_id}",
            },
        )
        await setup_session.commit()

    async with async_session_factory() as tool_session:
        service = FinnV2ToolExecutionService(tool_session)

        async def fail_inside_tool_execution(**_kwargs):
            # This is a real PostgreSQL FK violation, not a mocked exception.
            await tool_session.execute(
                text(
                    """
                    INSERT INTO finn_v2_tool_calls (
                        run_id, user_id, tool_name, status, selector_json, error_codes_json
                    ) VALUES ('missing-run', :user_id, 'read_profile', 'requested', '{}'::jsonb, '[]'::jsonb)
                    """
                ),
                {"user_id": conversation["user_id"]},
            )
            await tool_session.flush()

        service._dispatch_tool = fail_inside_tool_execution
        result = await service.execute_tool(
            run_id=run_id,
            user_id=conversation["user_id"],
            tool_name="read_profile",
            selector={},
            operation_id="evaluate_plan",
            operation_contract_version=FinnV2OperationRegistry.VERSION,
        )
        assert result.error_codes == ["tool_internal_error"]

    async with async_session_factory() as verification_session:
        status = await verification_session.scalar(
            text("SELECT status FROM finn_v2_runs WHERE id = :id"), {"id": run_id}
        )
        assert status == "collecting"
        operation_metadata = await verification_session.execute(
            text(
                """
                SELECT operation_id, operation_contract_version
                FROM finn_v2_tool_calls
                WHERE run_id = :id
                ORDER BY id DESC
                LIMIT 1
                """
            ),
            {"id": run_id},
        )
        row = operation_metadata.mappings().one()
        assert row["operation_id"] == "evaluate_plan"
        assert row["operation_contract_version"] == FinnV2OperationRegistry.VERSION
        await verification_session.execute(text("DELETE FROM finn_v2_runs WHERE id = :id"), {"id": run_id})
        await verification_session.commit()
