import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import DBAPIError

from backend.api import ai_assistant_api
from backend.schemas.assistant_schema import AssistantPreferenceUpdate
from backend.infrastructure.repositories.user_repository import UserRepository


class FakeSession:
    def __init__(self):
        self.rollbacks = 0

    async def rollback(self):
        self.rollbacks += 1


def test_new_profile_save_recovers_once_from_invalidated_database_connection(monkeypatch):
    user = SimpleNamespace(ai_preferences={})
    calls = {"read": 0, "write": 0, "events": []}

    class FakeRepository:
        def __init__(self, db):
            pass

        async def get_by_id(self, user_id):
            calls["read"] += 1
            return user

        async def update_ai_preferences(self, user_id, updates):
            calls["write"] += 1
            if calls["write"] == 1:
                raise DBAPIError("UPDATE users", {}, Exception("connection lost"), connection_invalidated=True)
            user.ai_preferences = {**user.ai_preferences, **updates}
            return user

    monkeypatch.setattr(ai_assistant_api, "UserRepository", FakeRepository)
    monkeypatch.setattr(ai_assistant_api, "_record_finn_product_event", lambda **kw: calls["events"].append(kw))
    # The route is idempotent: a reconnect may repeat the same preference patch.
    db = FakeSession()
    response = asyncio.run(ai_assistant_api.update_preferences(
        AssistantPreferenceUpdate(trader_types=["dca_investor"]), {"id": 7}, db,
    ))

    assert db.rollbacks == 1
    assert calls["read"] == 2
    assert calls["write"] == 2
    assert response.preferences["trader_types"] == ["dca_investor"]
    assert [event["event_name"] for event in calls["events"]] == ["trader_profile_created"]


def test_profile_save_does_not_retry_nontransient_database_error(monkeypatch):
    calls = {"write": 0}

    class FakeRepository:
        def __init__(self, db):
            pass

        async def get_by_id(self, user_id):
            return SimpleNamespace(ai_preferences={})

        async def update_ai_preferences(self, user_id, updates):
            calls["write"] += 1
            raise DBAPIError("UPDATE users", {}, Exception("invalid data"), connection_invalidated=False)

    monkeypatch.setattr(ai_assistant_api, "UserRepository", FakeRepository)
    db = FakeSession()
    with pytest.raises(DBAPIError):
        asyncio.run(ai_assistant_api.update_preferences(
            AssistantPreferenceUpdate(trader_types=["dca_investor"]), {"id": 7}, db,
        ))

    assert calls["write"] == 1
    assert db.rollbacks == 0


def test_detected_browser_zone_only_fills_missing_preference_under_row_lock():
    user = SimpleNamespace(ai_preferences={"time_zone": "America/New_York"})

    class Result:
        def scalars(self):
            return self

        def first(self):
            return user

    class Session:
        async def execute(self, statement):
            assert "FOR UPDATE" in str(statement)
            return Result()

        async def commit(self):
            pass

        async def refresh(self, _user):
            pass

    repository = UserRepository(Session())
    asyncio.run(repository.update_ai_preferences(
        7, {"locale": "nl"}, detected_time_zone="Europe/Amsterdam"))
    assert user.ai_preferences == {"time_zone": "America/New_York", "locale": "nl"}
    user.ai_preferences = {}
    asyncio.run(repository.update_ai_preferences(
        7, {}, detected_time_zone="Europe/Amsterdam"))
    assert user.ai_preferences["time_zone"] == "Europe/Amsterdam"


def test_detected_zone_patch_does_not_store_internal_request_field(monkeypatch):
    user = SimpleNamespace(ai_preferences={})

    class FakeRepository:
        def __init__(self, _db):
            pass

        async def get_by_id(self, _user_id):
            return user

        async def update_ai_preferences(self, _user_id, updates, *, detected_time_zone):
            assert updates == {}
            user.ai_preferences = {"time_zone": detected_time_zone}
            return user

    monkeypatch.setattr(ai_assistant_api, "UserRepository", FakeRepository)
    response = asyncio.run(ai_assistant_api.update_preferences(
        AssistantPreferenceUpdate(detected_time_zone="Pacific/Kiritimati"),
        {"id": 7}, FakeSession()))
    assert response.preferences == {"time_zone": "Pacific/Kiritimati"}
