from __future__ import annotations

from backend.infrastructure.repositories.user_repository import UserRepository
from backend.services.trader_profile_service import normalize_trader_profile_preferences


class ProfileToolAdapter:
    def __init__(self, session):
        self.users = UserRepository(session)

    async def execute(self, *, user_id: int, **_kwargs):
        user = await self.users.get_by_id(user_id)
        preferences = getattr(user, "ai_preferences", {}) or {}
        profile = normalize_trader_profile_preferences(preferences)
        return {
            "data": {
                "trader_profile": profile,
                "has_profile": any(bool(values) for values in profile.values()),
            },
            "summary": {"title": "profile", "keys": [key for key, value in profile.items() if value]},
            "as_of": None,
        }

