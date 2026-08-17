from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import FinnV2Conversation


class FinnV2ConversationRepository:
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

    async def create(
        self,
        *,
        conversation_id: str,
        user_id: int,
        title: Optional[str] = None,
    ) -> FinnV2Conversation:
        now = datetime.now(timezone.utc)
        row = FinnV2Conversation(
            id=conversation_id,
            user_id=user_id,
            title=title,
            status="active",
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def set_last_run(self, *, conversation_id: str, user_id: int, run_id: str) -> None:
        row = await self.get_by_id_for_user(conversation_id, user_id)
        if row is None:
            return
        row.last_run_id = run_id
        row.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
