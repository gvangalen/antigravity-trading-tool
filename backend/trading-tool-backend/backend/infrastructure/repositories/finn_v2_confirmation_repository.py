from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import FinnV2Confirmation


class FinnV2ConfirmationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_for_proposal_user(self, *, proposal_id: str, user_id: int) -> Optional[FinnV2Confirmation]:
        result = await self.session.execute(
            select(FinnV2Confirmation).where(
                FinnV2Confirmation.proposal_id == proposal_id,
                FinnV2Confirmation.user_id == user_id,
            )
        )
        return result.scalars().first()

    async def create(self, **kwargs) -> FinnV2Confirmation:
        row = FinnV2Confirmation(
            created_at=kwargs.pop("created_at", datetime.now(timezone.utc)),
            **kwargs,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def update(self, confirmation: FinnV2Confirmation, **kwargs) -> FinnV2Confirmation:
        for key, value in kwargs.items():
            setattr(confirmation, key, value)
        await self.session.flush()
        return confirmation
