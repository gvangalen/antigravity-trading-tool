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


def test_monitor_reports_stale_reservations(monkeypatch):
    import backend.celery_task.dispatcher as dispatcher

    events = []
    class Redis:
        def zcount(self, key, minimum, maximum):
            return 2 if key.endswith(":execution_critical") else 0

        def close(self):
            return None

    monkeypatch.setattr(dispatcher, "_broker_client", lambda: Redis())
    monkeypatch.setattr(dispatcher, "increment_dispatcher_counter", lambda name: events.append(name))
    dispatcher.monitor_dispatch_reservations()
    assert events == ["stale_reservation_alert_count"]


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


def test_dispatch_window_bucket_and_keys_are_deterministic(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    bucket = _dispatch_window_bucket(now_ts=1812000000, window_seconds=900)

    assert bucket == 2013333
    assert _dispatch_wave_key("task.alpha", window_bucket=bucket) == "dispatcher:production:wave:task.alpha:2013333"
    assert _dispatch_user_key("task.alpha", user_id=42, window_bucket=bucket) == "dispatcher:production:user:task.alpha:42:2013333"
    monkeypatch.setenv("APP_ENV", "staging")
    assert _dispatch_wave_key("task.alpha", window_bucket=bucket) == "dispatcher:staging:wave:task.alpha:2013333"


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
            if ":wave:" in key:
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

    continuations = []

    monkeypatch.setattr(dispatcher, "get_db_connection", lambda: _Conn())
    monkeypatch.setattr(dispatcher, "_broker_client", lambda: _Redis())
    monkeypatch.setattr(dispatcher, "current_app", SimpleNamespace(tasks={"demo.task": _Task()}))
    monkeypatch.setattr(dispatcher.dispatch_for_all_users, "apply_async", lambda **kwargs: continuations.append(kwargs))
    monkeypatch.setattr(dispatcher, "resolve_task_queue", lambda task_name: "execution_critical")
    monkeypatch.setattr(dispatcher, "resolve_workload_class", lambda task_name: "execution_critical")
    monkeypatch.setattr(dispatcher, "resolve_task_rate_limit", lambda task_name: "30/m")
    monkeypatch.setattr(dispatcher, "resolve_queue_backlog_limit", lambda task_name: 10)
    monkeypatch.setattr(dispatcher, "resolve_dispatch_window_seconds", lambda task_name, fallback_seconds: fallback_seconds)

    result = dispatch_for_all_users("demo.task", batch_size=2, max_spread_seconds=10)

    assert result["skipped"] is True
    assert result["reason"] == "queue_backlog"
    assert result["queue_depth"] == 25
    assert result["continued"] is True
    assert continuations[0]["kwargs"]["start_after_user_id"] == 0


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
            self.reservations = set()

        def set(self, key, value, nx=True, ex=None):
            if ":wave:" in key:
                return True
            if key in self.user_keys:
                return False
            self.user_keys.add(key)
            return not key.endswith(":31:0")

        def llen(self, queue_name):
            return 0

        def eval(self, script, key_count, queue_name, reservations_key, limit, token, created_at):
            assert key_count == 2
            self.reservations.add(token)
            return [1, 0, len(self.reservations) - 1]

        def delete(self, key):
            self.user_keys.discard(key)

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


def test_dispatcher_defers_remaining_users_at_capacity_and_resumes(monkeypatch):
    import backend.celery_task.dispatcher as dispatcher

    class Cursor:
        def execute(self, sql):
            assert "ORDER BY id" in sql

        def fetchall(self):
            return [(i,) for i in range(1, 6)]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Conn:
        def cursor(self):
            return Cursor()

        def close(self):
            pass

    class Redis:
        def __init__(self):
            self.leases = set()
            self.reservations = set()

        def set(self, key, value, nx=True, ex=None):
            if key in self.leases:
                return False
            self.leases.add(key)
            return True

        def llen(self, queue_name):
            return 0

        def eval(self, script, key_count, queue_name, reservations_key, limit, token, created_at):
            if len(self.reservations) >= limit:
                return [0, 0, len(self.reservations)]
            self.reservations.add(token)
            return [1, 0, len(self.reservations) - 1]

        def delete(self, key):
            self.leases.discard(key)

        def close(self):
            pass

    client = Redis()
    queued = []
    continuations = []
    task = SimpleNamespace(apply_async=lambda **kwargs: queued.append(kwargs))
    monkeypatch.setattr(dispatcher, "get_db_connection", lambda: Conn())
    monkeypatch.setattr(dispatcher, "_broker_client", lambda: client)
    monkeypatch.setattr(dispatcher, "current_app", SimpleNamespace(tasks={"demo.task": task}))
    monkeypatch.setattr(dispatcher, "resolve_task_queue", lambda _task: "portfolio")
    monkeypatch.setattr(dispatcher.dispatch_for_all_users, "apply_async", lambda **kwargs: continuations.append(kwargs))
    monkeypatch.setattr(dispatcher.time, "time", lambda: 10)

    first = dispatcher.dispatch_for_all_users("demo.task", backlog_limit=2)
    assert first["enqueued"] == 2
    assert first["deferred"] == 3
    assert [item["kwargs"]["user_id"] for item in queued] == [1, 2]
    assert continuations[0]["kwargs"]["start_after_user_id"] == 2

    client.reservations.clear()
    second = dispatcher.dispatch_for_all_users(**continuations.pop(0)["kwargs"])
    assert second["enqueued"] == 2
    assert second["deferred"] == 1
    assert [item["kwargs"]["user_id"] for item in queued] == [1, 2, 3, 4]

    client.reservations.clear()
    third = dispatcher.dispatch_for_all_users(**continuations.pop(0)["kwargs"])
    assert third["enqueued"] == 1
    assert third["deferred"] == 0
    assert [item["kwargs"]["user_id"] for item in queued] == [1, 2, 3, 4, 5]


def test_continuation_remains_durable_after_long_backlog(monkeypatch):
    import backend.celery_task.dispatcher as dispatcher

    scheduled = []
    monkeypatch.setattr(dispatcher.dispatch_for_all_users, "apply_async", lambda **kwargs: scheduled.append(kwargs))
    assert dispatcher._schedule_continuation(
        task_name="demo.task", active_only=True, batch_size=50, max_spread_seconds=60,
        dispatch_window_seconds=900, backlog_limit=400, start_after_user_id=90,
        continuation_attempt=120, window_bucket=1,
    )
    assert scheduled[0]["kwargs"]["continuation_attempt"] == 121
    assert scheduled[0]["kwargs"]["start_after_user_id"] == 90


def test_dispatch_reservation_is_released_only_after_task_postrun(monkeypatch):
    import backend.celery_task.dispatcher as dispatcher

    class Redis:
        def __init__(self):
            self.reservations = set()

        def eval(self, script, key_count, queue_name, reservations_key, limit, token, created_at):
            assert "ZREMRANGEBYSCORE" not in script
            assert "EXPIRE" not in script
            if len(self.reservations) >= limit:
                return [0, 0, len(self.reservations)]
            self.reservations.add(token)
            return [1, 0, len(self.reservations) - 1]

        def zrem(self, key, token):
            self.reservations.discard(token)

        def close(self):
            pass

    client = Redis()
    monkeypatch.setattr(dispatcher, "_broker_client", lambda: client)
    admitted, token = dispatcher._reserve_dispatch_capacity(
        client, queue_name="execution_critical", backlog_limit=1,
    )
    assert admitted is True
    assert dispatcher._reserve_dispatch_capacity(
        client, queue_name="execution_critical", backlog_limit=1,
    )[0] is False
    task = SimpleNamespace(request=SimpleNamespace(headers={
        "dispatch_reservation": token, "dispatch_queue": "execution_critical",
    }))
    dispatcher.release_dispatch_reservation(task_id=token, task=task, state="RETRY")
    assert token in client.reservations
    dispatcher.release_dispatch_reservation(task_id=token, task=task, state="SUCCESS")
    assert not client.reservations
    assert dispatcher._reserve_dispatch_capacity(
        client, queue_name="execution_critical", backlog_limit=1,
    )[0] is True
