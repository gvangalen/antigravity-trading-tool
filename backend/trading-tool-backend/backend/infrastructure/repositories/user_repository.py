from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from backend.infrastructure.models import User
from typing import Optional

class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: int) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalars().first()

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalars().first()

    async def count_users(self) -> int:
        result = await self.db.execute(select(func.count()).select_from(User))
        return result.scalar() or 0

    async def create_user(self, email: str, password_hash: str, role: str, first_name: str, last_name: Optional[str]) -> User:
        new_user = User(
            email=email,
            password_hash=password_hash,
            role=role,
            is_active=True,
            first_name=first_name,
            last_name=last_name
        )
        self.db.add(new_user)
        await self.db.commit()
        await self.db.refresh(new_user)
        return new_user

    async def update_last_login(self, user_id: int, login_time) -> None:
        user = await self.get_by_id(user_id)
        if user:
            user.last_login_at = login_time
            await self.db.commit()

    async def update_ai_preferences(self, user_id: int, preferences: dict) -> Optional[User]:
        user = await self.get_by_id(user_id)
        if user:
            # Merge existing preferences with new ones
            current_prefs = user.ai_preferences or {}
            current_prefs.update(preferences)
            user.ai_preferences = current_prefs
            await self.db.commit()
            await self.db.refresh(user)
        return user

    async def update_ai_usage(self, user_id: int, requests: int, cost: float, tokens: int) -> None:
        """
        Updates the AI usage metrics for a user.
        - increments ai_requests_used_day
        - adds cost to ai_usage_current
        - adds tokens to ai_tokens_used_month
        """
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(
                ai_requests_used_day=func.coalesce(User.ai_requests_used_day, 0) + requests,
                ai_usage_current=func.coalesce(User.ai_usage_current, 0) + cost,
                ai_tokens_used_month=func.coalesce(User.ai_tokens_used_month, 0) + tokens,
            )
        )
        await self.db.execute(stmt)
        await self.db.commit()
