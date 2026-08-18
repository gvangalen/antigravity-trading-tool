from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import FinnV2Run
from backend.infrastructure.repositories.finn_v2_repository_transaction_mixin import FinnV2RepositoryTransactionMixin


class FinnV2RunRepository(FinnV2RepositoryTransactionMixin):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id_for_user(self, *, run_id: str, user_id: int) -> Optional[FinnV2Run]:
        result = await self.session.execute(
            select(FinnV2Run).where(FinnV2Run.id == run_id, FinnV2Run.user_id == user_id)
        )
        return result.scalars().first()

    async def get_by_idempotency_key_for_user(self, *, idempotency_key: str, user_id: int) -> Optional[FinnV2Run]:
        result = await self.session.execute(
            select(FinnV2Run).where(
                FinnV2Run.user_id == user_id,
                FinnV2Run.idempotency_key == idempotency_key,
            )
        )
        return result.scalars().first()

    async def create(self, **kwargs) -> FinnV2Run:
        now = datetime.now(timezone.utc)
        row = FinnV2Run(
            created_at=kwargs.pop("created_at", now),
            updated_at=kwargs.pop("updated_at", now),
            **kwargs,
        )
        self.session.add(row)
        await self._flush_with_rollback(
            operation="create",
            entity_type="FinnV2Run",
            run_id=getattr(row, "id", None),
        )
        return row

    async def update_status(
        self,
        *,
        run: FinnV2Run,
        status: str,
        interaction_mode: Optional[str] = None,
        policy_json: Optional[dict] = None,
        response_json: Optional[dict] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        retryable: Optional[bool] = None,
        completed_at: Optional[datetime] = None,
        canceled_at: Optional[datetime] = None,
    ) -> FinnV2Run:
        run.status = status
        run.updated_at = datetime.now(timezone.utc)
        if interaction_mode is not None:
            run.interaction_mode = interaction_mode
        if policy_json is not None:
            run.policy_json = policy_json
        if response_json is not None:
            run.response_json = response_json
        if error_code is not None:
            run.error_code = error_code
        if error_message is not None:
            run.error_message = error_message
        if retryable is not None:
            run.retryable = retryable
        if completed_at is not None:
            run.completed_at = completed_at
        if canceled_at is not None:
            run.canceled_at = canceled_at
        await self._flush_with_rollback(operation="update_status", entity_type="FinnV2Run", run_id=run.id)
        return run

    async def redact_messages_older_than(self, cutoff: datetime) -> int:
        result = await self.session.execute(
            select(FinnV2Run).where(FinnV2Run.created_at < cutoff, FinnV2Run.message.is_not(None))
        )
        rows = list(result.scalars().all())
        for row in rows:
            row.message = "[redacted by finn_v2_retention]"
        await self._flush_with_rollback(operation="redact_messages", entity_type="FinnV2Run")
        return len(rows)

    async def delete_traces_older_than(self, cutoff: datetime) -> int:
        from backend.infrastructure.models import FinnV2RunTrace

        result = await self.session.execute(
            select(FinnV2RunTrace).where(FinnV2RunTrace.created_at < cutoff)
        )
        rows = list(result.scalars().all())
        for row in rows:
            await self.session.delete(row)
        await self._flush_with_rollback(operation="delete_traces", entity_type="FinnV2RunTrace")
        return len(rows)
