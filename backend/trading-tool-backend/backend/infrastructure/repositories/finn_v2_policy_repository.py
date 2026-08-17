from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import FinnV2PolicyDecision as FinnV2PolicyDecisionModel


class FinnV2PolicyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_for_run_version(self, *, run_id: str, user_id: int, policy_version: str) -> Optional[FinnV2PolicyDecisionModel]:
        result = await self.session.execute(
            select(FinnV2PolicyDecisionModel).where(
                FinnV2PolicyDecisionModel.run_id == run_id,
                FinnV2PolicyDecisionModel.user_id == user_id,
                FinnV2PolicyDecisionModel.policy_version == policy_version,
            )
        )
        return result.scalars().first()

    async def get_by_id_for_user(self, *, policy_decision_id: str, user_id: int) -> Optional[FinnV2PolicyDecisionModel]:
        result = await self.session.execute(
            select(FinnV2PolicyDecisionModel).where(
                FinnV2PolicyDecisionModel.id == policy_decision_id,
                FinnV2PolicyDecisionModel.user_id == user_id,
            )
        )
        return result.scalars().first()

    async def create(self, **kwargs) -> FinnV2PolicyDecisionModel:
        row = FinnV2PolicyDecisionModel(
            created_at=kwargs.pop("created_at", datetime.now(timezone.utc)),
            **kwargs,
        )
        self.session.add(row)
        await self.session.flush()
        return row
