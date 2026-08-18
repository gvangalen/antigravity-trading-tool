from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import FinnV2ToolCall


logger = logging.getLogger(__name__)


class FinnV2ToolCallRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **kwargs) -> FinnV2ToolCall:
        row = FinnV2ToolCall(
            started_at=kwargs.pop("started_at", datetime.now(timezone.utc)),
            **kwargs,
        )
        self.session.add(row)
        run_id = getattr(row, "run_id", None)
        user_id = getattr(row, "user_id", None)
        tool_name = getattr(row, "tool_name", None)
        try:
            await self.session.flush()
        except Exception as exc:
            logger.exception(
                "FINN V2 tool-call create flush failed",
                extra={
                    "repository": self.__class__.__name__,
                    "operation": "create",
                    "entity_type": "FinnV2ToolCall",
                    "run_id": run_id,
                    "user_id": user_id,
                    "tool_name": tool_name,
                    "exception_class": exc.__class__.__name__,
                },
            )
            raise
        return row

    async def get_by_id(self, tool_call_id: int) -> Optional[FinnV2ToolCall]:
        result = await self.session.execute(select(FinnV2ToolCall).where(FinnV2ToolCall.id == tool_call_id))
        return result.scalars().first()

    async def list_for_run(self, *, run_id: str, user_id: int) -> list[FinnV2ToolCall]:
        result = await self.session.execute(
            select(FinnV2ToolCall)
            .where(
                FinnV2ToolCall.run_id == run_id,
                FinnV2ToolCall.user_id == user_id,
            )
            .order_by(FinnV2ToolCall.id.asc())
        )
        return list(result.scalars().all())

    async def update(self, row: FinnV2ToolCall, **kwargs) -> FinnV2ToolCall:
        for key, value in kwargs.items():
            setattr(row, key, value)
        run_id = getattr(row, "run_id", None)
        user_id = getattr(row, "user_id", None)
        tool_call_id = getattr(row, "id", None)
        tool_name = getattr(row, "tool_name", None)
        try:
            await self.session.flush()
        except Exception as exc:
            logger.exception(
                "FINN V2 tool-call update flush failed",
                extra={
                    "repository": self.__class__.__name__,
                    "operation": "update",
                    "entity_type": "FinnV2ToolCall",
                    "run_id": run_id,
                    "user_id": user_id,
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "exception_class": exc.__class__.__name__,
                },
            )
            raise
        return row

    async def redact_results_older_than(self, cutoff: datetime) -> int:
        result = await self.session.execute(
            select(FinnV2ToolCall).where(
                FinnV2ToolCall.completed_at.is_not(None),
                FinnV2ToolCall.completed_at < cutoff,
                FinnV2ToolCall.result_summary_json.is_not(None),
            )
        )
        rows = list(result.scalars().all())
        for row in rows:
            row.result_summary_json = {"status": "redacted", "error_codes": ["result_redacted"]}
            row.redacted_at = datetime.now(timezone.utc)
        await self.session.flush()
        return len(rows)

    async def delete_metadata_older_than(self, cutoff: datetime) -> int:
        result = await self.session.execute(
            delete(FinnV2ToolCall).where(FinnV2ToolCall.started_at < cutoff)
        )
        await self.session.flush()
        return int(result.rowcount or 0)
