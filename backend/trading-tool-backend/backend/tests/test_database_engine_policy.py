from backend.infrastructure.database import _async_engine_options
from backend.celery_task import finn_v2_task


def test_interactive_finn_worker_uses_fresh_bounded_database_connections():
    options = _async_engine_options("celery-worker-finn-interactive")

    assert options["pool_size"] == 2
    assert options["max_overflow"] == 0
    assert options["pool_pre_ping"] is True
    assert options["connect_args"] == {"timeout": 3}


def test_api_and_other_workers_keep_normal_database_pooling():
    options = _async_engine_options("backend")

    assert options["pool_pre_ping"] is True
    assert options["pool_size"] == 10
    assert options["pool_timeout"] == 3


def test_interactive_task_refreshes_pool_before_first_database_session():
    import inspect

    source = inspect.getsource(finn_v2_task._process_finn_v2_run)

    assert source.index("await engine.dispose(close=False)") < source.index("async with async_session_factory()")
