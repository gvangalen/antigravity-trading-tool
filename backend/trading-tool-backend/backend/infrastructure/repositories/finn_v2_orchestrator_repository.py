from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import FinnV2OrchestratorResult
from backend.infrastructure.repositories.finn_v2_repository_transaction_mixin import FinnV2RepositoryTransactionMixin


class FinnV2OrchestratorRepository(FinnV2RepositoryTransactionMixin):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_for_run_version(
        self,
        *,
        run_id: str,
        user_id: int,
        orchestrator_version: str,
    ) -> Optional[FinnV2OrchestratorResult]:
        result = await self.session.execute(
            select(FinnV2OrchestratorResult).where(
                FinnV2OrchestratorResult.run_id == run_id,
                FinnV2OrchestratorResult.user_id == user_id,
                FinnV2OrchestratorResult.orchestrator_version == orchestrator_version,
            )
        )
        return result.scalars().first()

    async def create(self, **kwargs) -> FinnV2OrchestratorResult:
        row = FinnV2OrchestratorResult(
            created_at=kwargs.pop("created_at", datetime.now(timezone.utc)),
            **kwargs,
        )
        self.session.add(row)
        await self._flush_with_rollback(
            operation="create",
            entity_type="FinnV2OrchestratorResult",
            run_id=getattr(row, "run_id", None),
        )
        return row
