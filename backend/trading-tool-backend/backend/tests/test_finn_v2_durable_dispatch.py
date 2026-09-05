import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import backend.celery_task.finn_v2_task as task_module
from backend.infrastructure.repositories.finn_v2_dispatch_repository import FinnV2DispatchRepository


class _Session:
    def __init__(self, run):
        self.run = run
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def execute(self, _statement):
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(first=lambda: self.run),
            scalar_one=lambda: self.run.user_id,
        )

    async def commit(self):
        self.commits += 1


class _Dispatches:
    claimed = True
    events = []
    recoverable = []
    stale = []

    def __init__(self, _session):
        pass

    async def claim(self, **kwargs):
        self.events.append(("claim", kwargs))
        if not self.claimed:
            return None
        return SimpleNamespace(dispatch_id="dispatch-1")

    async def heartbeat(self, **kwargs):
        self.events.append(("heartbeat", kwargs))
        return True

    async def mark_completed(self, dispatch_id):
        self.events.append(("completed", dispatch_id))

    async def mark_terminal_failure(self, **kwargs):
        self.events.append(("terminal_failure", kwargs))

    async def mark_failure(self, **kwargs):
        self.events.append(("retryable_failure", kwargs))
        return "retryable_failure"

    async def list_recoverable(self, **_kwargs):
        return self.recoverable

    async def reserve_recovery(self, **kwargs):
        self.events.append(("reserve_recovery", kwargs))
        return True

    async def mark_published(self, dispatch_id):
        self.events.append(("published", dispatch_id))

    async def expire_stale_unclaimed(self, **_kwargs):
        return self.stale


def _install_worker_fakes(monkeypatch, run):
    sessions = []

    def _factory():
        session = _Session(run)
        sessions.append(session)
        return session

    _Dispatches.claimed = True
    _Dispatches.events = []
    _Dispatches.recoverable = []
    _Dispatches.stale = []
    monkeypatch.setattr(task_module, "async_session_factory", _factory)
    monkeypatch.setattr(task_module, "FinnV2DispatchRepository", _Dispatches)
    return sessions


def test_worker_claims_once_and_completes_terminal_run(monkeypatch):
    run = SimpleNamespace(id="run-1", user_id=7, status="planned", retryable=False, error_code=None)
    _install_worker_fakes(monkeypatch, run)

    async def _lifecycle(**_kwargs):
        run.status = "completed"

    monkeypatch.setattr(task_module.FinnV2RunService, "run_foundation_lifecycle_owned", _lifecycle)

    assert asyncio.run(task_module._process_finn_v2_run(run_id="run-1", owner="worker-1")) == "run-1"
    assert [event[0] for event in _Dispatches.events] == ["claim", "heartbeat", "completed"]


def test_interactive_task_acknowledges_only_after_worker_lifecycle_completes():
    assert task_module.process_finn_v2_run.acks_late is True
    assert task_module.process_finn_v2_run.reject_on_worker_lost is True
    assert task_module.process_finn_v2_run.track_started is True


def test_unclaimed_dispatch_deadline_is_bounded_for_interactive_runs():
    assert task_module.DISPATCH_STALE_UNCLAIMED_SECONDS <= 10


def test_unclaimed_dispatch_deadline_starts_after_broker_handoff():
    source = inspect.getsource(FinnV2DispatchRepository.expire_stale_unclaimed)

    assert "dispatched_at.is_not(None)" in source
    assert "dispatched_at < now - timedelta(seconds=max_age_seconds)" in source
    assert "created_at < now - timedelta(seconds=max_age_seconds)" not in source


def test_duplicate_worker_delivery_does_not_start_second_lifecycle(monkeypatch):
    run = SimpleNamespace(id="run-2", user_id=7, status="planned", retryable=False, error_code=None)
    _install_worker_fakes(monkeypatch, run)
    _Dispatches.claimed = False
    lifecycle_calls = []

    async def _lifecycle(**kwargs):
        lifecycle_calls.append(kwargs)

    monkeypatch.setattr(task_module.FinnV2RunService, "run_foundation_lifecycle_owned", _lifecycle)

    assert asyncio.run(task_module._process_finn_v2_run(run_id="run-2", owner="worker-2")) == "run-2"
    assert lifecycle_calls == []
    assert [event[0] for event in _Dispatches.events] == ["claim"]


def test_worker_terminal_failure_is_not_retried(monkeypatch):
    run = SimpleNamespace(id="run-3", user_id=7, status="planned", retryable=False, error_code=None)
    _install_worker_fakes(monkeypatch, run)

    async def _lifecycle(**_kwargs):
        run.status = "failed"
        run.error_code = "verifier_rejected"

    monkeypatch.setattr(task_module.FinnV2RunService, "run_foundation_lifecycle_owned", _lifecycle)

    asyncio.run(task_module._process_finn_v2_run(run_id="run-3", owner="worker-3"))
    assert ("terminal_failure", {"dispatch_id": "dispatch-1", "error_code": "verifier_rejected"}) in _Dispatches.events
    assert not any(event[0] == "retryable_failure" for event in _Dispatches.events)


def test_worker_retryable_failure_keeps_dispatch_recoverable(monkeypatch):
    run = SimpleNamespace(id="run-4", user_id=7, status="planned", retryable=False, error_code=None)
    _install_worker_fakes(monkeypatch, run)

    async def _lifecycle(**_kwargs):
        raise TimeoutError("provider timeout")

    monkeypatch.setattr(task_module.FinnV2RunService, "run_foundation_lifecycle_owned", _lifecycle)

    with pytest.raises(TimeoutError):
        asyncio.run(task_module._process_finn_v2_run(run_id="run-4", owner="worker-4"))
    assert any(event[0] == "retryable_failure" for event in _Dispatches.events)


def test_worker_provider_error_after_planned_keeps_same_dispatch_recoverable(monkeypatch):
    run = SimpleNamespace(id="run-4b", user_id=7, status="planned", retryable=False, error_code=None)
    _install_worker_fakes(monkeypatch, run)

    async def _lifecycle(**_kwargs):
        run.status = "failed"
        run.retryable = True
        run.error_code = "provider_timeout"

    monkeypatch.setattr(task_module.FinnV2RunService, "run_foundation_lifecycle_owned", _lifecycle)

    with pytest.raises(RuntimeError, match="provider_timeout"):
        asyncio.run(task_module._process_finn_v2_run(run_id="run-4b", owner="worker-4b"))
    assert any(event[0] == "retryable_failure" for event in _Dispatches.events)


def test_stale_dispatch_recovery_reuses_persisted_task_id(monkeypatch):
    run = SimpleNamespace(dispatch_id="dispatch-5", run_id="run-5", task_id="task-5", queue="ai_generation")
    _install_worker_fakes(monkeypatch, SimpleNamespace(id="unused", user_id=0, status="completed"))
    _Dispatches.recoverable = [run]
    enqueued = []

    class _Task:
        name = "backend.celery_task.finn_v2_task.process_finn_v2_run"

        @staticmethod
        def apply_async(**kwargs):
            enqueued.append(kwargs)

    monkeypatch.setattr(task_module, "process_finn_v2_run", _Task())

    assert asyncio.run(task_module._recover_finn_v2_dispatches()) == 1
    assert enqueued == [{"kwargs": {"run_id": "run-5"}, "task_id": "task-5", "queue": "ai_generation"}]
    assert ("published", "dispatch-5") in _Dispatches.events


def test_recovery_publish_does_not_claim_a_dispatch(monkeypatch):
    run = SimpleNamespace(dispatch_id="dispatch-6", run_id="run-6", task_id="task-6", queue="finn_interactive")
    _install_worker_fakes(monkeypatch, SimpleNamespace(id="unused", user_id=0, status="completed"))
    _Dispatches.recoverable = [run]

    class _Task:
        name = "backend.celery_task.finn_v2_task.process_finn_v2_run"

        @staticmethod
        def apply_async(**_kwargs):
            return None

    monkeypatch.setattr(task_module, "process_finn_v2_run", _Task())
    assert asyncio.run(task_module._recover_finn_v2_dispatches()) == 1
    assert ("published", "dispatch-6") in _Dispatches.events
    assert not any(event[0] == "claim" for event in _Dispatches.events)


def test_recovery_does_not_republish_a_dispatch_reserved_by_another_worker(monkeypatch):
    run = SimpleNamespace(dispatch_id="dispatch-6b", run_id="run-6b", task_id="task-6b", queue="finn_interactive")
    _install_worker_fakes(monkeypatch, SimpleNamespace(id="unused", user_id=0, status="completed"))
    _Dispatches.recoverable = [run]
    enqueued = []

    async def _not_reserved(self, **kwargs):
        self.events.append(("reserve_recovery", kwargs))
        return False

    class _Task:
        name = "backend.celery_task.finn_v2_task.process_finn_v2_run"

        @staticmethod
        def apply_async(**kwargs):
            enqueued.append(kwargs)

    monkeypatch.setattr(_Dispatches, "reserve_recovery", _not_reserved)
    monkeypatch.setattr(task_module, "process_finn_v2_run", _Task())

    assert asyncio.run(task_module._recover_finn_v2_dispatches()) == 0
    assert enqueued == []
    assert not any(event[0] == "published" for event in _Dispatches.events)


def test_recovery_is_idempotent_after_worker_crash(monkeypatch):
    run = SimpleNamespace(id="run-7", user_id=7, status="planned", retryable=False, error_code=None)
    _install_worker_fakes(monkeypatch, run)

    async def _crash(**_kwargs):
        raise RuntimeError("worker_crash")

    monkeypatch.setattr(task_module.FinnV2RunService, "run_foundation_lifecycle_owned", _crash)
    with pytest.raises(RuntimeError, match="worker_crash"):
        asyncio.run(task_module._process_finn_v2_run(run_id="run-7", owner="worker-a"))
    _Dispatches.claimed = False
    assert asyncio.run(task_module._process_finn_v2_run(run_id="run-7", owner="worker-b")) == "run-7"
    assert [event[0] for event in _Dispatches.events].count("claim") == 2


def test_worker_task_boundary_disposes_async_resources_before_its_loop_closes(monkeypatch):
    events = []

    class _Engine:
        async def dispose(self):
            events.append(("async_dispose", None))

    async def _job():
        events.append(("job", None))
        return "done"

    monkeypatch.setattr(task_module, "engine", _Engine())

    assert task_module._run_async(_job()) == "done"
    assert events == [("job", None), ("async_dispose", None)]


def test_stale_unclaimed_dispatch_is_terminalized_once(monkeypatch):
    run = SimpleNamespace(id="run-8", user_id=7, status="created", retryable=False, error_code=None)
    _install_worker_fakes(monkeypatch, run)
    _Dispatches.stale = [SimpleNamespace(dispatch_id="dispatch-8", run_id="run-8")]
    failures = []

    class _RunService:
        def __init__(self, _session):
            pass

        async def fail_run(self, **kwargs):
            failures.append(kwargs)

    monkeypatch.setattr(task_module, "FinnV2RunService", _RunService)
    assert asyncio.run(task_module._recover_finn_v2_dispatches()) == 0
    assert failures == [{
        "run_id": "run-8", "user_id": 7,
        "error_code": "dispatch_claim_timeout",
        "error_message": "FINN could not start this request in time. Please try again.",
        "retryable": False, "failure_stage": "dispatch_recovery",
    }]
    _Dispatches.stale = []
    assert asyncio.run(task_module._recover_finn_v2_dispatches()) == 0
    assert len(failures) == 1


MIGRATION = Path(__file__).resolve().parents[1] / "scripts" / "migrations" / "2026_08_22_finn_v2_dispatch_outbox.py"


def test_dispatch_outbox_migration_is_idempotent_and_has_controlled_rollback():
    source = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS finn_v2_run_dispatches" in source
    assert "CREATE INDEX IF NOT EXISTS idx_finn_v2_dispatch_recovery" in source
    assert "run_id TEXT NOT NULL UNIQUE" in source
    assert "task_id TEXT NOT NULL UNIQUE" in source
    assert "ROLLBACK_SQL" in source
    assert "DROP TABLE IF EXISTS finn_v2_run_dispatches" in source
