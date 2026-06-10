from backend.celery_task.store_daily_scores_task import run_rule_based_daily_scores


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
