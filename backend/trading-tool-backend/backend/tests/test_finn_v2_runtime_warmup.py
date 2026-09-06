import asyncio
from types import SimpleNamespace

import backend.celery_task.finn_v2_task as finn_tasks
from backend.celery_task.celery_app import warm_finn_interactive_worker_after_ready


def test_interactive_worker_warmup_is_queued_only_by_the_dedicated_worker(monkeypatch):
    sent = []
    monkeypatch.setenv("TRADAMIND_BUILD_SERVICE", "celery-worker-finn-interactive")

    warm_finn_interactive_worker_after_ready(
        sender=SimpleNamespace(app=SimpleNamespace(send_task=lambda task_name: sent.append(task_name)))
    )

    assert sent == ["backend.celery_task.finn_v2_task.warm_finn_v2_interactive_worker"]


def test_other_workers_never_enqueue_the_interactive_warmup(monkeypatch):
    sent = []
    monkeypatch.setenv("TRADAMIND_BUILD_SERVICE", "celery-worker-default")

    warm_finn_interactive_worker_after_ready(
        sender=SimpleNamespace(app=SimpleNamespace(send_task=lambda task_name: sent.append(task_name)))
    )

    assert sent == []


def test_warmup_task_has_no_run_or_user_input(monkeypatch):
    observed = []

    def fake_run_async(coroutine):
        observed.append(coroutine)
        coroutine.close()
        return "ready"

    monkeypatch.setattr(finn_tasks, "_run_async", fake_run_async)

    assert finn_tasks.warm_finn_v2_interactive_worker() == "ready"
    assert len(observed) == 1


def test_warmup_database_probe_is_read_only(monkeypatch):
    statements = []

    class Session:
        async def execute(self, statement):
            statements.append(str(statement))

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr(finn_tasks, "async_session_factory", lambda: Session())

    assert asyncio.run(finn_tasks._warm_finn_v2_interactive_worker()) == "ready"
    assert statements == ["SELECT 1"]
