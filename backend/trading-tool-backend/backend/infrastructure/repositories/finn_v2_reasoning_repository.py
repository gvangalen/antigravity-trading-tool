from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import FinnV2ReasoningResult


class FinnV2ReasoningRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_reusable_result(
        self,
        *,
        run_id: str,
        user_id: int,
        context_version: str,
        evidence_set_hash: str,
        prompt_version: str,
        model: str,
    ) -> Optional[FinnV2ReasoningResult]:
        result = await self.session.execute(
            select(FinnV2ReasoningResult).where(
                FinnV2ReasoningResult.run_id == run_id,
                FinnV2ReasoningResult.user_id == user_id,
                FinnV2ReasoningResult.context_version == context_version,
                FinnV2ReasoningResult.evidence_set_hash == evidence_set_hash,
                FinnV2ReasoningResult.prompt_version == prompt_version,
                FinnV2ReasoningResult.model == model,
                FinnV2ReasoningResult.status == "ready",
            )
        )
        return result.scalars().first()

    async def get_by_id_for_user(self, *, reasoning_result_id: str, user_id: int) -> Optional[FinnV2ReasoningResult]:
        result = await self.session.execute(
            select(FinnV2ReasoningResult).where(
                FinnV2ReasoningResult.id == reasoning_result_id,
                FinnV2ReasoningResult.user_id == user_id,
            )
        )
        return result.scalars().first()

    async def create(self, **kwargs) -> FinnV2ReasoningResult:
        now = datetime.now(timezone.utc)
        row = FinnV2ReasoningResult(
            created_at=kwargs.pop("created_at", now),
            completed_at=kwargs.pop("completed_at", None),
            **kwargs,
        )
        self.session.add(row)
        await self.session.flush()
        return row
