from datetime import datetime
from copy import deepcopy
from typing import Optional

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.models import User, AuthRefreshSession, AuthPasswordResetToken

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

    async def create_user(
        self,
        email: str,
        password_hash: str,
        role: str,
        first_name: str,
        last_name: Optional[str],
        ai_preferences: Optional[dict] = None,
    ) -> User:
        new_user = User(
            email=email,
            password_hash=password_hash,
            role=role,
            is_active=True,
            first_name=first_name,
            last_name=last_name,
            ai_preferences=deepcopy(ai_preferences or {}),
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
            # Reassign a fresh JSON object so SQLAlchemy/Postgres JSONB persistence
            # reliably detects trader-profile preference updates.
            current_prefs = deepcopy(user.ai_preferences or {})
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

    async def create_refresh_session(
        self,
        user_id: int,
        jti: str,
        token_hash: str,
        expires_at,
    ) -> AuthRefreshSession:
        session = AuthRefreshSession(
            user_id=user_id,
            jti=jti,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def get_refresh_session(self, jti: str) -> Optional[AuthRefreshSession]:
        result = await self.db.execute(
            select(AuthRefreshSession).where(AuthRefreshSession.jti == jti)
        )
        return result.scalars().first()

    async def rotate_refresh_session(
        self,
        current_session: AuthRefreshSession,
        *,
        replaced_by_jti: str,
        rotated_at: datetime,
    ) -> None:
        current_session.rotated_at = rotated_at
        current_session.revoked_at = rotated_at
        current_session.revoked_reason = "rotated"
        current_session.replaced_by_jti = replaced_by_jti
        current_session.last_used_at = rotated_at
        await self.db.commit()

    async def revoke_refresh_session(
        self,
        current_session: AuthRefreshSession,
        *,
        reason: str,
        revoked_at: datetime,
    ) -> None:
        current_session.revoked_at = revoked_at
        current_session.revoked_reason = reason
        current_session.last_used_at = revoked_at
        await self.db.commit()

    async def revoke_all_refresh_sessions_for_user(
        self,
        user_id: int,
        *,
        reason: str,
        revoked_at: datetime,
    ) -> None:
        await self.db.execute(
            update(AuthRefreshSession)
            .where(
                AuthRefreshSession.user_id == user_id,
                AuthRefreshSession.revoked_at.is_(None),
            )
            .values(
                revoked_at=revoked_at,
                revoked_reason=reason,
                last_used_at=revoked_at,
            )
        )
        await self.db.commit()

    async def update_password_hash(self, user_id: int, password_hash: str) -> Optional[User]:
        user = await self.get_by_id(user_id)
        if not user:
            return None
        user.password_hash = password_hash
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def create_password_reset_token(
        self,
        *,
        user_id: int,
        token_hash: str,
        expires_at: datetime,
        locale: Optional[str] = None,
    ) -> AuthPasswordResetToken:
        token = AuthPasswordResetToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            locale=locale,
        )
        self.db.add(token)
        await self.db.commit()
        await self.db.refresh(token)
        return token

    async def get_password_reset_token(self, token_hash: str) -> Optional[AuthPasswordResetToken]:
        result = await self.db.execute(
            select(AuthPasswordResetToken).where(AuthPasswordResetToken.token_hash == token_hash)
        )
        return result.scalars().first()

    async def revoke_password_reset_tokens_for_user(
        self,
        user_id: int,
        *,
        reason: str,
        revoked_at: datetime,
        exclude_token_id: Optional[int] = None,
    ) -> None:
        query = (
            update(AuthPasswordResetToken)
            .where(
                AuthPasswordResetToken.user_id == user_id,
                AuthPasswordResetToken.used_at.is_(None),
                AuthPasswordResetToken.revoked_at.is_(None),
            )
            .values(
                revoked_at=revoked_at,
                revoked_reason=reason,
            )
        )
        if exclude_token_id is not None:
            query = query.where(AuthPasswordResetToken.id != exclude_token_id)
        await self.db.execute(query)
        await self.db.commit()

    async def consume_password_reset_token(
        self,
        token: AuthPasswordResetToken,
        *,
        used_at: datetime,
    ) -> None:
        token.used_at = used_at
        token.revoked_reason = "used"
        await self.db.commit()
