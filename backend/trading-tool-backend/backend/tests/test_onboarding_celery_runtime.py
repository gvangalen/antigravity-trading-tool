from backend.celery_task.celery_app import reset_sqlalchemy_pools_after_fork
from backend.celery_task import onboarding_task
from backend.infrastructure import database


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



def test_onboarding_registers_no_retired_first_dashboard_tasks():
    assert not hasattr(onboarding_task, "enqueue_first_dashboard_briefing")
    assert not hasattr(onboarding_task, "generate_first_dashboard_briefing")
