from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import FinnV2EligibilityDecision
from backend.services.finn_v2_json_safety import to_json_safe


class FinnV2EligibilityRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def latest_for_proposal_user(self, *, proposal_id: str, user_id: int) -> Optional[FinnV2EligibilityDecision]:
        result = await self.session.execute(
            select(FinnV2EligibilityDecision)
            .where(
                FinnV2EligibilityDecision.proposal_id == proposal_id,
                FinnV2EligibilityDecision.user_id == user_id,
            )
            .order_by(FinnV2EligibilityDecision.checked_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def create(self, **kwargs) -> FinnV2EligibilityDecision:
        if "decision_json" in kwargs:
            kwargs["decision_json"] = to_json_safe(kwargs["decision_json"])
        row = FinnV2EligibilityDecision(
            checked_at=kwargs.pop("checked_at", datetime.now(timezone.utc)),
            **kwargs,
        )
        self.session.add(row)
        await self.session.flush()
        return row
