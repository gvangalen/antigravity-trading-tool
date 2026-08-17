from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import FinnV2ReleaseGateResult


class FinnV2ReleaseGateRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **kwargs) -> FinnV2ReleaseGateResult:
        row = FinnV2ReleaseGateResult(created_at=kwargs.pop("created_at", datetime.now(timezone.utc)), **kwargs)
        self.session.add(row)
        await self.session.flush()
        return row

    async def latest(self) -> Optional[FinnV2ReleaseGateResult]:
        result = await self.session.execute(
            select(FinnV2ReleaseGateResult).order_by(FinnV2ReleaseGateResult.created_at.desc()).limit(1)
        )
        return result.scalars().first()

