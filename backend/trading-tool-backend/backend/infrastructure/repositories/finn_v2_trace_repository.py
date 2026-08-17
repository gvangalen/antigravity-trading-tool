from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import FinnV2RunTrace


class FinnV2TraceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def next_event_order(self, *, run_id: str, user_id: int) -> int:
        result = await self.session.execute(
            select(FinnV2RunTrace.event_order)
            .where(FinnV2RunTrace.run_id == run_id, FinnV2RunTrace.user_id == user_id)
            .order_by(FinnV2RunTrace.event_order.desc())
            .limit(1)
        )
        current = result.scalar_one_or_none()
        return int(current or 0) + 1

    async def append_event(
        self,
        *,
        run_id: str,
        user_id: int,
        trace_id: str,
        event_type: str,
        payload_json: Dict[str, Any],
        event_order: Optional[int] = None,
    ) -> FinnV2RunTrace:
        resolved_order = event_order or await self.next_event_order(run_id=run_id, user_id=user_id)
        row = FinnV2RunTrace(
            run_id=run_id,
            user_id=user_id,
            trace_id=trace_id,
            event_type=event_type,
            event_order=resolved_order,
            payload_json=payload_json,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def list_for_run(self, *, run_id: str, user_id: int) -> list[FinnV2RunTrace]:
        result = await self.session.execute(
            select(FinnV2RunTrace)
            .where(FinnV2RunTrace.run_id == run_id, FinnV2RunTrace.user_id == user_id)
            .order_by(FinnV2RunTrace.event_order.asc())
        )
        return list(result.scalars().all())
