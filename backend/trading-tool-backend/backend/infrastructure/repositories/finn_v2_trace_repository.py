from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import FinnV2RunTrace
from backend.infrastructure.repositories.finn_v2_repository_transaction_mixin import FinnV2RepositoryTransactionMixin


class FinnV2TraceRepository(FinnV2RepositoryTransactionMixin):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def next_event_order(self, *, run_id: str, user_id: int) -> int:
        # A PostgreSQL sequence is atomic across concurrent tool sessions and
        # does not hold a transaction lock while evidence is persisted. The
        # value only needs to be monotonic for ordering; gaps after rollback
        # are valid trace semantics.
        result = await self.session.execute(
            text(
                "SELECT nextval(pg_get_serial_sequence("
                "'finn_v2_run_traces', 'id'))"
            )
        )
        return int(result.scalar_one())

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
        await self._flush_with_rollback(operation="append_event", entity_type="FinnV2RunTrace", run_id=run_id)
        return row

    async def list_for_run(self, *, run_id: str, user_id: int) -> list[FinnV2RunTrace]:
        result = await self.session.execute(
            select(FinnV2RunTrace)
            .where(FinnV2RunTrace.run_id == run_id, FinnV2RunTrace.user_id == user_id)
            .order_by(FinnV2RunTrace.event_order.asc())
        )
        return list(result.scalars().all())
