from backend.celery_task.celery_app import reset_sqlalchemy_pools_after_fork
from backend.celery_task.onboarding_task import (
    enqueue_first_dashboard_briefing,
    generate_first_dashboard_briefing,
)
from backend.infrastructure import database
import backend.services.finn_plan_service as finn_plan_service


def test_reset_sqlalchemy_pools_after_fork_disposes_inherited_pools(monkeypatch):
    calls = []

    class FakeAsyncSyncEngine:
        def dispose(self):
            calls.append("async-sync-engine")

    class FakeAsyncEngine:
        sync_engine = FakeAsyncSyncEngine()

    class FakeSyncEngine:
        def dispose(self):
            calls.append("sync-engine")

    monkeypatch.setattr(database, "engine", FakeAsyncEngine())
    monkeypatch.setattr(database, "sync_engine", FakeSyncEngine())

    reset_sqlalchemy_pools_after_fork()

    assert calls == ["async-sync-engine", "sync-engine"]


def test_generate_first_dashboard_briefing_resets_engines_before_async_session(monkeypatch):
    calls = []

    class FakeAsyncEngine:
        async def dispose(self):
            calls.append("async-engine")

    class FakeSyncEngine:
        def dispose(self):
            calls.append("sync-engine")

    class FakeSessionFactory:
        def __call__(self):
            return self

        async def __aenter__(self):
            calls.append("session-enter")
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            calls.append("session-exit")
            return False

    class FakeService:
        def __init__(self, session):
            calls.append("service-init")

        async def generate_and_store_first_dashboard_briefing(self, user_id, trigger="onboarding_pipeline"):
            calls.append(("generate", user_id, trigger))
            return {"status": "ready", "user_id": user_id}

        @staticmethod
        def invalidate_runtime_caches_for_user(user_id):
            calls.append(("invalidate", user_id))

    monkeypatch.setattr(database, "engine", FakeAsyncEngine())
    monkeypatch.setattr(database, "sync_engine", FakeSyncEngine())
    monkeypatch.setattr(database, "async_session_factory", FakeSessionFactory())
    monkeypatch.setattr(finn_plan_service, "FinnPlanService", FakeService)

    result = generate_first_dashboard_briefing(315)

    assert result == {"status": "ready", "user_id": 315}
    assert calls[:4] == ["async-engine", "sync-engine", "session-enter", "service-init"]
    assert ("generate", 315, "onboarding_pipeline") in calls


def test_enqueue_first_dashboard_briefing_queues_generate_task(monkeypatch):
    queued = []

    class FakeDelay:
        def delay(self, user_id):
            queued.append(user_id)

    monkeypatch.setattr(
        "backend.celery_task.onboarding_task.generate_first_dashboard_briefing",
        FakeDelay(),
    )

    result = enqueue_first_dashboard_briefing(315, trigger="bootstrap_agents")

    assert result == {"status": "queued", "user_id": 315, "trigger": "bootstrap_agents"}
    assert queued == [315]
