from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import FinnV2Execution
from backend.infrastructure.repositories.finn_v2_repository_transaction_mixin import FinnV2RepositoryTransactionMixin


class FinnV2ExecutionRepository(FinnV2RepositoryTransactionMixin):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **kwargs) -> FinnV2Execution:
        row = FinnV2Execution(
            started_at=kwargs.pop("started_at", datetime.now(timezone.utc)),
            completed_at=kwargs.pop("completed_at", None),
            **kwargs,
        )
        self.session.add(row)
        await self._flush_with_rollback(
            operation="create",
            entity_type="finn_v2_execution",
            run_id=getattr(row, "run_id", None),
        )
        return row

    async def get_by_idempotency_key_for_user(self, *, idempotency_key: str, user_id: int) -> Optional[FinnV2Execution]:
        result = await self.session.execute(
            select(FinnV2Execution).where(
                FinnV2Execution.idempotency_key == idempotency_key,
                FinnV2Execution.user_id == user_id,
            )
        )
        return result.scalars().first()

    async def get_for_proposal(self, *, proposal_id: str, user_id: int) -> Optional[FinnV2Execution]:
        result = await self.session.execute(
            select(FinnV2Execution).where(
                FinnV2Execution.proposal_id == proposal_id,
                FinnV2Execution.user_id == user_id,
            )
        )
        return result.scalars().first()
