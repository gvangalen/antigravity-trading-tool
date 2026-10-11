from backend.celery_task.store_daily_scores_task import run_rule_based_daily_scores
import threading


def test_run_rule_based_daily_scores_skips_when_previous_run_is_active(monkeypatch):
    import backend.celery_task.store_daily_scores_task as task_module

    monkeypatch.setattr(task_module, "_try_acquire_rule_based_scores_lease", lambda: None)

    result = run_rule_based_daily_scores()

    assert result["skipped"] is True
    assert result["reason"] == "lease_already_active"


def test_run_rule_based_daily_scores_releases_lease_after_success(monkeypatch):
    import backend.celery_task.store_daily_scores_task as task_module

    released = []

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

    lease = object()
    users_built = []

    monkeypatch.setattr(task_module, "_try_acquire_rule_based_scores_lease", lambda: lease)
    monkeypatch.setattr(task_module, "_release_rule_based_scores_lease", lambda client: released.append(client))
    monkeypatch.setattr(task_module, "get_db_connection", lambda: _Conn())
    monkeypatch.setattr(task_module, "build_daily_scores_for_user", lambda user_id: users_built.append(user_id))

    run_rule_based_daily_scores()

    assert users_built == [30, 31]
    assert released == [lease]


def test_daily_score_storage_keeps_missing_macro_as_null(monkeypatch):
    import backend.celery_task.store_daily_scores_task as task_module
    events = []

    class Cursor:
        def __init__(self, conn):
            self.conn = conn

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params):
            if "pg_advisory_xact_lock" in sql:
                events.append(("lock", params))
            if "INSERT INTO daily_scores" in sql:
                self.conn.saved = params
                events.append(("upsert", None))

        def fetchall(self):
            return [("AAPL",)]

    class Connection:
        saved = None

        def cursor(self):
            return Cursor(self)

        def commit(self):
            events.append(("commit", None))

        def close(self):
            pass

    conn = Connection()
    monkeypatch.setattr(task_module, "get_db_connection", lambda: conn)
    def generate(category, **_):
        events.append(("source_read", category))
        return {
            "scores": {} if category == "macro" else {"signal": {"score": 70, "weight": 1}},
            "total_score": 10 if category == "macro" else 70,
        }

    monkeypatch.setattr(task_module, "generate_scores_db", generate)

    task_module.build_daily_scores_for_user(7)

    assert conn.saved[:5] == (7, "AAPL", None, 70, 70)
    assert conn.saved[5] is None  # The retired AI setup score is never stored.
    assert events[0] == ("lock", (task_module.SCORE_OWNER_LOCK_NAMESPACE, 7))
    assert [event[0] for event in events][-2:] == ["upsert", "commit"]
    assert task_module._confirmed_component_score({
        "total_score": 10, "scores": {"unused": {"weight": 0}},
    }) is None


def test_overlapping_owner_rebuilds_write_newest_source_evidence_last(monkeypatch):
    import backend.celery_task.store_daily_scores_task as task_module

    owner_lock = threading.Lock()
    first_read = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    source = {"score": 20}
    committed = []

    class Cursor:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params):
            if "pg_advisory_xact_lock" in sql:
                owner_lock.acquire()
                self.connection.locked = True
            elif "INSERT INTO daily_scores" in sql:
                self.connection.saved = params

    class Connection:
        locked = False
        saved = None

        def cursor(self):
            return Cursor(self)

        def commit(self):
            committed.append(self.saved)
            if self.locked:
                owner_lock.release()
                self.locked = False

        def rollback(self):
            if self.locked:
                owner_lock.release()
                self.locked = False

        def close(self):
            pass

    def generate(category, **_):
        score = source["score"]
        if threading.current_thread().name == "first" and category == "macro":
            first_read.set()
            assert release_first.wait(2)
        return {"scores": {"signal": {"score": score, "weight": 1}}, "total_score": score}

    monkeypatch.setattr(task_module, "get_db_connection", Connection)
    monkeypatch.setattr(task_module, "generate_scores_db", generate)

    def rebuild(started=None):
        if started is not None:
            started.set()
        task_module.build_daily_scores_for_user(7, symbols=["ETH"])

    first = threading.Thread(target=rebuild, name="first")
    second = threading.Thread(target=rebuild, args=(second_started,), name="second")
    first.start()
    assert first_read.wait(2)
    source["score"] = 40
    second.start()
    assert second_started.wait(2)
    release_first.set()
    first.join(2)
    second.join(2)

    assert not first.is_alive() and not second.is_alive()
    assert len(committed) == 2
    assert committed[0][2] == 20  # older macro score
    assert committed[-1][2:5] == (40, 40, 40)
