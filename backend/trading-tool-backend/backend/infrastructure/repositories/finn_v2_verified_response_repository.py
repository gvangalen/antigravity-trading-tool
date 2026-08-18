from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import FinnV2VerifiedResponse
from backend.infrastructure.repositories.finn_v2_repository_transaction_mixin import FinnV2RepositoryTransactionMixin


class FinnV2VerifiedResponseRepository(FinnV2RepositoryTransactionMixin):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_for_run_version(self, *, run_id: str, user_id: int, response_version: str) -> Optional[FinnV2VerifiedResponse]:
        result = await self.session.execute(
            select(FinnV2VerifiedResponse).where(
                FinnV2VerifiedResponse.run_id == run_id,
                FinnV2VerifiedResponse.user_id == user_id,
                FinnV2VerifiedResponse.response_version == response_version,
            )
        )
        return result.scalars().first()

    async def get_latest_for_run(self, *, run_id: str, user_id: int) -> Optional[FinnV2VerifiedResponse]:
        result = await self.session.execute(
            select(FinnV2VerifiedResponse)
            .where(FinnV2VerifiedResponse.run_id == run_id, FinnV2VerifiedResponse.user_id == user_id)
            .order_by(FinnV2VerifiedResponse.created_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def create(self, **kwargs) -> FinnV2VerifiedResponse:
        row = FinnV2VerifiedResponse(
            created_at=kwargs.pop("created_at", datetime.now(timezone.utc)),
            **kwargs,
        )
        self.session.add(row)
        await self._flush_with_rollback(
            operation="create",
            entity_type="FinnV2VerifiedResponse",
            run_id=getattr(row, "run_id", None),
        )
        return row
