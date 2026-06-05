from types import SimpleNamespace

from backend.celery_task.dispatcher import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_DISPATCH_WINDOW_SECONDS,
    DEFAULT_MAX_SPREAD_SECONDS,
    _bounded_countdown,
    _dispatch_user_key,
    _dispatch_wave_key,
    _dispatch_window_bucket,
    _dispatch_plan,
    dispatch_for_all_users,
)


def test_dispatch_plan_is_bounded_for_10k_users():
    plan = _dispatch_plan(
        10_000,
        batch_size=DEFAULT_BATCH_SIZE,
        max_spread_seconds=DEFAULT_MAX_SPREAD_SECONDS,
    )

    assert plan["batch_size"] == 100
    assert plan["batch_count"] == 100
    assert plan["max_countdown_seconds"] == 300


def test_bounded_countdown_repeats_inside_fixed_window():
    first_batch = [
        _bounded_countdown(i, batch_size=5, max_spread_seconds=20)
        for i in range(5)
    ]
    second_batch = [
        _bounded_countdown(i, batch_size=5, max_spread_seconds=20)
        for i in range(5, 10)
    ]

    assert first_batch == [0, 5, 10, 15, 20]
    assert second_batch == first_batch


def test_bounded_countdown_handles_single_user_and_zero_spread():
    assert _bounded_countdown(0, batch_size=1, max_spread_seconds=300) == 0
    assert _bounded_countdown(500, batch_size=100, max_spread_seconds=0) == 0


def test_dispatch_plan_handles_empty_users():
    plan = _dispatch_plan(0, batch_size=100, max_spread_seconds=300)

    assert plan["batch_count"] == 0
    assert plan["max_countdown_seconds"] == 0


def test_dispatch_window_bucket_and_keys_are_deterministic():
    bucket = _dispatch_window_bucket(now_ts=1812000000, window_seconds=900)

    assert bucket == 2013333
    assert _dispatch_wave_key("task.alpha", window_bucket=bucket) == "dispatcher:wave:task.alpha:2013333"
    assert _dispatch_user_key("task.alpha", user_id=42, window_bucket=bucket) == "dispatcher:user:task.alpha:42:2013333"


def test_dispatcher_skips_when_wave_is_already_active(monkeypatch):
    import backend.celery_task.dispatcher as dispatcher

    class _Cursor:
        def execute(self, sql):
            self._rows = [(30,), (31,)]

        def fetchall(self):
            return self._rows

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Conn:
        def cursor(self):
            return _Cursor()

        def close(self):
            return None

    class _Redis:
        def set(self, key, value, nx=True, ex=None):
            if key.startswith("dispatcher:wave:"):
                return False
            return True

        def llen(self, queue_name):
            return 0

        def close(self):
            return None

    class _Task:
        def apply_async(self, **kwargs):
            raise AssertionError("task should not be enqueued when wave is already active")

    monkeypatch.setattr(dispatcher, "get_db_connection", lambda: _Conn())
    monkeypatch.setattr(dispatcher, "_broker_client", lambda: _Redis())
    monkeypatch.setattr(dispatcher, "current_app", SimpleNamespace(tasks={"demo.task": _Task()}))
    monkeypatch.setattr(dispatcher.time, "time", lambda: 1812000000)

    result = dispatch_for_all_users(
        "demo.task",
        batch_size=2,
        max_spread_seconds=10,
        dispatch_window_seconds=DEFAULT_DISPATCH_WINDOW_SECONDS,
    )

    assert result["skipped"] is True
    assert result["reason"] == "wave_already_active"


def test_dispatcher_skips_when_target_queue_backlog_is_over_limit(monkeypatch):
    import backend.celery_task.dispatcher as dispatcher

    class _Cursor:
        def execute(self, sql):
            self._rows = [(30,), (31,)]

        def fetchall(self):
            return self._rows

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Conn:
        def cursor(self):
            return _Cursor()

        def close(self):
            return None

    class _Redis:
        def set(self, key, value, nx=True, ex=None):
            return True

        def llen(self, queue_name):
            return 25

        def close(self):
            return None

    class _Task:
        def apply_async(self, **kwargs):
            raise AssertionError("task should not be enqueued when backlog is above limit")

    monkeypatch.setattr(dispatcher, "get_db_connection", lambda: _Conn())
    monkeypatch.setattr(dispatcher, "_broker_client", lambda: _Redis())
    monkeypatch.setattr(dispatcher, "current_app", SimpleNamespace(tasks={"demo.task": _Task()}))
    monkeypatch.setattr(dispatcher, "resolve_task_queue", lambda task_name: "execution_critical")
    monkeypatch.setattr(dispatcher, "resolve_workload_class", lambda task_name: "execution_critical")
    monkeypatch.setattr(dispatcher, "resolve_task_rate_limit", lambda task_name: "30/m")
    monkeypatch.setattr(dispatcher, "resolve_queue_backlog_limit", lambda task_name: 10)
    monkeypatch.setattr(dispatcher, "resolve_dispatch_window_seconds", lambda task_name, fallback_seconds: fallback_seconds)

    result = dispatch_for_all_users("demo.task", batch_size=2, max_spread_seconds=10)

    assert result["skipped"] is True
    assert result["reason"] == "queue_backlog"
    assert result["queue_depth"] == 25


def test_dispatcher_dedupes_users_inside_same_window(monkeypatch):
    import backend.celery_task.dispatcher as dispatcher

    class _Cursor:
        def execute(self, sql):
            self._rows = [(30,), (31,), (32,)]

        def fetchall(self):
            return self._rows

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Conn:
        def cursor(self):
            return _Cursor()

        def close(self):
            return None

    class _Redis:
        def __init__(self):
            self.user_keys = set()

        def set(self, key, value, nx=True, ex=None):
            if key.startswith("dispatcher:wave:"):
                return True
            if key in self.user_keys:
                return False
            self.user_keys.add(key)
            return not key.endswith(":31:0")

        def llen(self, queue_name):
            return 0

        def close(self):
            return None

    calls = []

    class _Task:
        def apply_async(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(dispatcher, "get_db_connection", lambda: _Conn())
    monkeypatch.setattr(dispatcher, "_broker_client", lambda: _Redis())
    monkeypatch.setattr(dispatcher, "current_app", SimpleNamespace(tasks={"demo.task": _Task()}))
    monkeypatch.setattr(dispatcher.time, "time", lambda: 10)
    monkeypatch.setattr(dispatcher, "resolve_task_queue", lambda task_name: "execution_critical")
    monkeypatch.setattr(dispatcher, "resolve_workload_class", lambda task_name: "execution_critical")
    monkeypatch.setattr(dispatcher, "resolve_task_rate_limit", lambda task_name: "30/m")
    monkeypatch.setattr(dispatcher, "resolve_queue_backlog_limit", lambda task_name: 100)
    monkeypatch.setattr(dispatcher, "resolve_dispatch_window_seconds", lambda task_name, fallback_seconds: 60)

    result = dispatch_for_all_users("demo.task", batch_size=3, max_spread_seconds=20)

    assert result["enqueued"] == 2
    assert result["deduped"] == 1
    assert [call["kwargs"]["user_id"] for call in calls] == [30, 32]
