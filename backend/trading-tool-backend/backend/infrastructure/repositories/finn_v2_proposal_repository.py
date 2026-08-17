from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import FinnV2Proposal


class FinnV2ProposalRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id_for_user(self, *, proposal_id: str, user_id: int) -> Optional[FinnV2Proposal]:
        result = await self.session.execute(
            select(FinnV2Proposal).where(
                FinnV2Proposal.id == proposal_id,
                FinnV2Proposal.user_id == user_id,
            )
        )
        return result.scalars().first()

    async def get_by_idempotency_key_for_user(self, *, idempotency_key: str, user_id: int) -> Optional[FinnV2Proposal]:
        result = await self.session.execute(
            select(FinnV2Proposal).where(
                FinnV2Proposal.user_id == user_id,
                FinnV2Proposal.idempotency_key == idempotency_key,
            )
        )
        return result.scalars().first()

    async def get_by_payload_hash_for_run(self, *, payload_hash: str, run_id: str, user_id: int) -> Optional[FinnV2Proposal]:
        result = await self.session.execute(
            select(FinnV2Proposal).where(
                FinnV2Proposal.run_id == run_id,
                FinnV2Proposal.user_id == user_id,
                FinnV2Proposal.payload_hash == payload_hash,
            )
        )
        return result.scalars().first()

    async def create(self, **kwargs) -> FinnV2Proposal:
        now = datetime.now(timezone.utc)
        row = FinnV2Proposal(
            created_at=kwargs.pop("created_at", now),
            updated_at=kwargs.pop("updated_at", now),
            **kwargs,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def update_status(self, proposal: FinnV2Proposal, *, status: str) -> FinnV2Proposal:
        proposal.status = status
        proposal.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return proposal
