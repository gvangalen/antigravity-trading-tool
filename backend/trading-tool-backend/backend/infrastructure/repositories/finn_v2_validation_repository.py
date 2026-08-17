from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import FinnV2ValidationResult


class FinnV2ValidationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_for_snapshot_version(
        self,
        *,
        snapshot_id: str,
        user_id: int,
        validator_version: str,
    ) -> Optional[FinnV2ValidationResult]:
        result = await self.session.execute(
            select(FinnV2ValidationResult).where(
                FinnV2ValidationResult.snapshot_id == snapshot_id,
                FinnV2ValidationResult.user_id == user_id,
                FinnV2ValidationResult.validator_version == validator_version,
            )
        )
        return result.scalars().first()

    async def create(self, **kwargs) -> FinnV2ValidationResult:
        row = FinnV2ValidationResult(
            validated_at=kwargs.pop("validated_at", datetime.now(timezone.utc)),
            **kwargs,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def redact_payloads_older_than(self, cutoff: datetime) -> int:
        result = await self.session.execute(
            select(FinnV2ValidationResult).where(
                FinnV2ValidationResult.validated_at < cutoff,
                FinnV2ValidationResult.result_json.is_not(None),
            )
        )
        rows = list(result.scalars().all())
        for row in rows:
            row.result_json = None
            row.redacted_at = datetime.now(timezone.utc)
        await self.session.flush()
        return len(rows)
