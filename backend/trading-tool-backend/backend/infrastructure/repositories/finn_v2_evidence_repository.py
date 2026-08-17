from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import FinnV2EvidenceArtifact


class FinnV2EvidenceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **kwargs) -> FinnV2EvidenceArtifact:
        row = FinnV2EvidenceArtifact(
            created_at=kwargs.pop("created_at", datetime.now(timezone.utc)),
            **kwargs,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def get_by_tool_call_id(self, *, tool_call_id: int, user_id: int) -> Optional[FinnV2EvidenceArtifact]:
        result = await self.session.execute(
            select(FinnV2EvidenceArtifact).where(
                FinnV2EvidenceArtifact.tool_call_id == tool_call_id,
                FinnV2EvidenceArtifact.user_id == user_id,
            )
        )
        return result.scalars().first()

    async def list_for_run(self, *, run_id: str, user_id: int) -> list[FinnV2EvidenceArtifact]:
        result = await self.session.execute(
            select(FinnV2EvidenceArtifact)
            .where(FinnV2EvidenceArtifact.run_id == run_id, FinnV2EvidenceArtifact.user_id == user_id)
            .order_by(FinnV2EvidenceArtifact.created_at.asc(), FinnV2EvidenceArtifact.id.asc())
        )
        return list(result.scalars().all())

    async def redact_payloads_older_than(self, cutoff: datetime) -> int:
        result = await self.session.execute(
            select(FinnV2EvidenceArtifact).where(
                FinnV2EvidenceArtifact.created_at < cutoff,
                FinnV2EvidenceArtifact.payload_json.is_not(None),
            )
        )
        rows = list(result.scalars().all())
        for row in rows:
            row.payload_json = None
            row.redacted_at = datetime.now(timezone.utc)
        await self.session.flush()
        return len(rows)
