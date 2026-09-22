from backend.infrastructure.database import _async_engine_options
from backend.celery_task import finn_v2_task


def test_interactive_finn_worker_keeps_one_warm_connection_with_bounded_read_burst():
    options = _async_engine_options("celery-worker-finn-interactive")

    assert options["pool_size"] == 1
    assert options["max_overflow"] == 7
    assert options["pool_pre_ping"] is True
    assert options["pool_use_lifo"] is True
    assert options["pool_recycle"] == 1800
    assert options["connect_args"] == {"timeout": 3, "command_timeout": 2}


def test_api_and_other_workers_keep_normal_database_pooling():
    options = _async_engine_options("backend")

    assert options["pool_pre_ping"] is True
    assert options["pool_size"] == 10
    assert options["pool_timeout"] == 3


def test_interactive_task_reuses_pre_pinged_pool_between_runs():
    import inspect

    source = inspect.getsource(finn_v2_task._process_finn_v2_run)

    assert "engine.dispose" not in source
