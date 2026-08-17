from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import FinnV2StateSnapshot


class FinnV2StateRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id_for_user(self, *, snapshot_id: str, user_id: int) -> Optional[FinnV2StateSnapshot]:
        result = await self.session.execute(
            select(FinnV2StateSnapshot).where(
                FinnV2StateSnapshot.id == snapshot_id,
                FinnV2StateSnapshot.user_id == user_id,
            )
        )
        return result.scalars().first()

    async def get_by_evidence_hash(self, *, run_id: str, user_id: int, evidence_set_hash: str) -> Optional[FinnV2StateSnapshot]:
        result = await self.session.execute(
            select(FinnV2StateSnapshot).where(
                FinnV2StateSnapshot.run_id == run_id,
                FinnV2StateSnapshot.user_id == user_id,
                FinnV2StateSnapshot.evidence_set_hash == evidence_set_hash,
            )
        )
        return result.scalars().first()

    async def next_revision(self, *, run_id: str, user_id: int) -> int:
        result = await self.session.execute(
            select(func.max(FinnV2StateSnapshot.revision)).where(
                FinnV2StateSnapshot.run_id == run_id,
                FinnV2StateSnapshot.user_id == user_id,
            )
        )
        current = result.scalar_one_or_none()
        return int(current or 0) + 1

    async def create(self, **kwargs) -> FinnV2StateSnapshot:
        row = FinnV2StateSnapshot(
            assembled_at=kwargs.pop("assembled_at", datetime.now(timezone.utc)),
            **kwargs,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def list_for_run(self, *, run_id: str, user_id: int) -> list[FinnV2StateSnapshot]:
        result = await self.session.execute(
            select(FinnV2StateSnapshot)
            .where(FinnV2StateSnapshot.run_id == run_id, FinnV2StateSnapshot.user_id == user_id)
            .order_by(FinnV2StateSnapshot.revision.asc())
        )
        return list(result.scalars().all())

    async def redact_payloads_older_than(self, cutoff: datetime) -> int:
        result = await self.session.execute(
            select(FinnV2StateSnapshot).where(
                FinnV2StateSnapshot.assembled_at < cutoff,
                FinnV2StateSnapshot.snapshot_json.is_not(None),
            )
        )
        rows = list(result.scalars().all())
        for row in rows:
            row.snapshot_json = None
            row.redacted_at = datetime.now(timezone.utc)
        await self.session.flush()
        return len(rows)
