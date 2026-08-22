import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

import backend.celery_task.finn_v2_task as task_module


class _Session:
    def __init__(self, run):
        self.run = run
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def execute(self, _statement):
        return SimpleNamespace(scalars=lambda: SimpleNamespace(first=lambda: self.run))

    async def commit(self):
        self.commits += 1


class _Dispatches:
    claimed = True
    events = []
    recoverable = []

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

    async def mark_dispatched(self, dispatch_id):
        self.events.append(("dispatched", dispatch_id))


def _install_worker_fakes(monkeypatch, run):
    sessions = []

    def _factory():
        session = _Session(run)
        sessions.append(session)
        return session

    _Dispatches.claimed = True
    _Dispatches.events = []
    _Dispatches.recoverable = []
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
    assert ("dispatched", "dispatch-5") in _Dispatches.events


MIGRATION = Path(__file__).resolve().parents[1] / "scripts" / "migrations" / "2026_08_22_finn_v2_dispatch_outbox.py"


def test_dispatch_outbox_migration_is_idempotent_and_has_controlled_rollback():
    source = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS finn_v2_run_dispatches" in source
    assert "CREATE INDEX IF NOT EXISTS idx_finn_v2_dispatch_recovery" in source
    assert "run_id TEXT NOT NULL UNIQUE" in source
    assert "task_id TEXT NOT NULL UNIQUE" in source
    assert "ROLLBACK_SQL" in source
    assert "DROP TABLE IF EXISTS finn_v2_run_dispatches" in source
