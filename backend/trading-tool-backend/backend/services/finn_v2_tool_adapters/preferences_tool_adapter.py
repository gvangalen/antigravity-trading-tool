from __future__ import annotations

from backend.infrastructure.repositories.user_repository import UserRepository
from backend.schemas.finn_v2_evidence_schema import UserPreferencesData


class PreferencesToolAdapter:
    def __init__(self, session):
        self.users = UserRepository(session)

    async def execute(self, *, user_id: int, **_kwargs):
        user = await self.users.get_by_id(user_id)
        preferences = getattr(user, "ai_preferences", {}) or {}
        public_preferences = {
            "report_style": preferences.get("report_style"),
            "tone": preferences.get("tone"),
            "detail_level": preferences.get("detail_level"),
            "coaching_style": preferences.get("coaching_style"),
            "experience_level": preferences.get("experience_level"),
            "risk_profile": preferences.get("risk_profile"),
            "selected_asset": preferences.get("selected_asset"),
            "active_asset": preferences.get("active_asset"),
        }
        return {
            "data": UserPreferencesData(**public_preferences),
            "summary": {"title": "preferences", "keys": list(public_preferences.keys())},
            "as_of": None,
            "source": "users.ai_preferences",
            "schema_name": "UserPreferencesData",
            "entity_type": "preferences",
        }
