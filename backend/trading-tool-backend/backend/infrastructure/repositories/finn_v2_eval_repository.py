from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import FinnV2EvalCaseResult, FinnV2EvalRun


class FinnV2EvalRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_run(self, **kwargs) -> FinnV2EvalRun:
        row = FinnV2EvalRun(
            created_at=kwargs.pop("created_at", datetime.now(timezone.utc)),
            completed_at=kwargs.pop("completed_at", None),
            **kwargs,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def create_case_result(self, **kwargs) -> FinnV2EvalCaseResult:
        row = FinnV2EvalCaseResult(
            created_at=kwargs.pop("created_at", datetime.now(timezone.utc)),
            **kwargs,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def latest_run(self) -> Optional[FinnV2EvalRun]:
        result = await self.session.execute(select(FinnV2EvalRun).order_by(FinnV2EvalRun.created_at.desc()).limit(1))
        return result.scalars().first()

    async def update_run(self, run: FinnV2EvalRun, **kwargs) -> FinnV2EvalRun:
        for key, value in kwargs.items():
            setattr(run, key, value)
        await self.session.flush()
        return run
