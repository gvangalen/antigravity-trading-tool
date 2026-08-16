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

        async def generate_and_store_first_dashboard_briefing(
            self,
            user_id,
            trigger="onboarding_pipeline",
            task_id=None,
            enqueued_context_version=None,
            attempt=None,
            queue_name=None,
            owner_task_id=None,
        ):
            calls.append(
                (
                    "generate",
                    user_id,
                    trigger,
                    task_id,
                    enqueued_context_version,
                    attempt,
                    queue_name,
                    owner_task_id,
                )
            )
            return {"status": "ready", "user_id": user_id}

        @staticmethod
        def invalidate_runtime_caches_for_user(user_id):
            calls.append(("invalidate", user_id))

    monkeypatch.setattr(database, "engine", FakeAsyncEngine())
    monkeypatch.setattr(database, "sync_engine", FakeSyncEngine())
    monkeypatch.setattr(database, "async_session_factory", FakeSessionFactory())
    monkeypatch.setattr(finn_plan_service, "FinnPlanService", FakeService)

    generate_first_dashboard_briefing.push_request(id="task-1", delivery_info={"routing_key": "ai_generation"})
    try:
        result = generate_first_dashboard_briefing(315)
    finally:
        generate_first_dashboard_briefing.pop_request()

    assert result == {"status": "ready", "user_id": 315}
    assert calls[:4] == ["async-engine", "sync-engine", "session-enter", "service-init"]
    assert ("generate", 315, "onboarding_pipeline", "task-1", None, None, "ai_generation", None) in calls


def test_enqueue_first_dashboard_briefing_resets_engines_before_service_enqueue(monkeypatch):
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

        async def enqueue_first_dashboard_briefing(self, user_id, trigger="onboarding_pipeline", owner_task_id=None):
            calls.append(("enqueue", user_id, trigger, owner_task_id))
            return {"status": "queued", "user_id": user_id, "trigger": trigger}

    monkeypatch.setattr(database, "engine", FakeAsyncEngine())
    monkeypatch.setattr(database, "sync_engine", FakeSyncEngine())
    monkeypatch.setattr(database, "async_session_factory", FakeSessionFactory())
    monkeypatch.setattr(finn_plan_service, "FinnPlanService", FakeService)
    enqueue_first_dashboard_briefing.push_request(id="owner-task-1")
    try:
        result = enqueue_first_dashboard_briefing(315, trigger="bootstrap_agents")
    finally:
        enqueue_first_dashboard_briefing.pop_request()

    assert result == {"status": "queued", "user_id": 315, "trigger": "bootstrap_agents"}
    assert calls[:4] == ["async-engine", "sync-engine", "session-enter", "service-init"]
    assert ("enqueue", 315, "bootstrap_agents", "owner-task-1") in calls
