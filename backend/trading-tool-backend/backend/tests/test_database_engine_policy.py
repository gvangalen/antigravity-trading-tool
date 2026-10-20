import asyncio

from backend.infrastructure.database import _async_engine_options
from backend.celery_task import finn_v2_task


def test_interactive_finn_worker_uses_fresh_bounded_database_connections():
    options = _async_engine_options("celery-worker-finn-interactive")

    assert options["pool_size"] == 1
    assert options["max_overflow"] == 0
    assert options["pool_pre_ping"] is True
    assert options["pool_use_lifo"] is True
    assert options["pool_recycle"] == 1800
    assert options["connect_args"] == {"timeout": 3, "command_timeout": 2}


def test_api_and_background_workers_have_bounded_database_pools():
    options = _async_engine_options("backend")

    assert options["pool_pre_ping"] is True
    assert options["pool_size"] == 16
    assert options["max_overflow"] == 4
    assert options["pool_timeout"] == 3
    background = _async_engine_options("celery-worker-default")
    assert background["pool_size"] == 2
    assert background["max_overflow"] == 0


def test_celery_task_disposes_pooled_connections_in_each_event_loop(monkeypatch):
    from backend.infrastructure import database

    events = []

    class Engine:
        async def dispose(self):
            events.append(("dispose", asyncio.get_running_loop()))

    monkeypatch.setattr(database, "engine", Engine())

    async def task():
        events.append(("task", asyncio.get_running_loop()))
        return 7

    assert database.run_celery_coroutine(task()) == 7
    assert database.run_celery_coroutine(task()) == 7
    assert [kind for kind, _ in events] == ["task", "dispose", "task", "dispose"]
    assert events[0][1] is events[1][1]
    assert events[2][1] is events[3][1]
    assert events[0][1] is not events[2][1]


def test_interactive_task_reuses_pre_pinged_pool_between_runs():
    import inspect

    source = inspect.getsource(finn_v2_task._process_finn_v2_run)

    assert "engine.dispose" not in source
