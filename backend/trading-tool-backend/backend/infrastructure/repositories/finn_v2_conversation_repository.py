from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import FinnV2Conversation
from backend.infrastructure.repositories.finn_v2_repository_transaction_mixin import FinnV2RepositoryTransactionMixin


class FinnV2ConversationRepository(FinnV2RepositoryTransactionMixin):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id_for_user(self, conversation_id: str, user_id: int) -> Optional[FinnV2Conversation]:
        result = await self.session.execute(
            select(FinnV2Conversation).where(
                FinnV2Conversation.id == conversation_id,
                FinnV2Conversation.user_id == user_id,
            )
        )
        return result.scalars().first()

    async def get_by_session_id_for_user(self, session_id: str, user_id: int) -> Optional[FinnV2Conversation]:
        """Resolve only a stable composer session belonging to this user."""
        result = await self.session.execute(
            select(FinnV2Conversation).where(
                FinnV2Conversation.user_id == user_id,
                FinnV2Conversation.context_json["session_id"].astext == session_id,
            )
        )
        return result.scalars().first()

    async def create(
        self,
        *,
        conversation_id: str,
        user_id: int,
        title: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> FinnV2Conversation:
        now = datetime.now(timezone.utc)
        row = FinnV2Conversation(
            id=conversation_id,
            user_id=user_id,
            title=title,
            status="active",
            created_at=now,
            updated_at=now,
            context_json=dict(context or {}),
        )
        self.session.add(row)
        await self._flush_with_rollback(operation="create", entity_type="FinnV2Conversation")
        return row

    async def set_last_run(self, *, conversation_id: str, user_id: int, run_id: str) -> None:
        row = await self.get_by_id_for_user(conversation_id, user_id)
        if row is None:
            return
        row.last_run_id = run_id
        row.updated_at = datetime.now(timezone.utc)
        await self._flush_with_rollback(operation="update_last_run", entity_type="FinnV2Conversation", run_id=run_id)

    async def get_context(self, *, conversation_id: str, user_id: int) -> Dict[str, Any]:
        row = await self.get_by_id_for_user(conversation_id, user_id)
        return dict(row.context_json or {}) if row is not None else {}

    async def update_context(self, *, conversation_id: str, user_id: int, context: Dict[str, Any]) -> None:
        row = await self.get_by_id_for_user(conversation_id, user_id)
        if row is None:
            return
        row.context_json = dict(context)
        row.updated_at = datetime.now(timezone.utc)
        await self._flush_with_rollback(
            operation="update_context",
            entity_type="FinnV2Conversation",
            run_id=row.last_run_id,
        )
