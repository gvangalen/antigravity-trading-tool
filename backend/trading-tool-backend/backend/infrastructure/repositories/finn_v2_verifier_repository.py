from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import FinnV2VerifierResult
from backend.infrastructure.repositories.finn_v2_repository_transaction_mixin import FinnV2RepositoryTransactionMixin


class FinnV2VerifierRepository(FinnV2RepositoryTransactionMixin):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_latest_for_run(self, *, run_id: str, user_id: int) -> Optional[FinnV2VerifierResult]:
        result = await self.session.execute(
            select(FinnV2VerifierResult)
            .where(FinnV2VerifierResult.run_id == run_id, FinnV2VerifierResult.user_id == user_id)
            .order_by(FinnV2VerifierResult.created_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def get_by_id_for_user(self, *, verifier_result_id: str, user_id: int) -> Optional[FinnV2VerifierResult]:
        result = await self.session.execute(
            select(FinnV2VerifierResult).where(
                FinnV2VerifierResult.id == verifier_result_id,
                FinnV2VerifierResult.user_id == user_id,
            )
        )
        return result.scalars().first()

    async def create(self, **kwargs) -> FinnV2VerifierResult:
        row = FinnV2VerifierResult(
            created_at=kwargs.pop("created_at", datetime.now(timezone.utc)),
            **kwargs,
        )
        self.session.add(row)
        await self._flush_with_rollback(
            operation="create",
            entity_type="FinnV2VerifierResult",
            run_id=getattr(row, "run_id", None),
        )
        return row
