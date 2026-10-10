from backend.celery_task import daily_report_task as daily_report_module
from backend.celery_task import indicator_history_task as history_module
from backend.celery_task import onboarding_task as onboarding_module
from backend.celery_task import store_daily_scores_task as score_module


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.query = query
        self.params = params

    def fetchall(self):
        return list(self._rows)


class _Connection:
    def __init__(self, rows):
        self.rows = rows
        self.commit_count = 0
        self.rollback_count = 0
        self.closed = False

    def cursor(self):
        return _Cursor(self.rows)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        self.closed = True


class _TaskStub:
    def __init__(self, name):
        self.name = name

    def si(self, *args, **kwargs):
        return (self.name, args, kwargs)


def test_run_onboarding_pipeline_queues_expected_workflow(monkeypatch):
    conn = _Connection(rows=[(1,)])
    monkeypatch.setattr(onboarding_module, "get_db_connection", lambda: conn)

    monkeypatch.setattr(score_module, "store_daily_scores_task", _TaskStub("store_daily_scores_task"))
    monkeypatch.setattr(history_module, "bootstrap_indicator_histories", _TaskStub("bootstrap_indicator_histories"))
    monkeypatch.setattr(daily_report_module, "generate_daily_report", _TaskStub("generate_daily_report"))
    monkeypatch.setattr(onboarding_module, "enqueue_first_dashboard_briefing", _TaskStub("enqueue_first_dashboard_briefing"))

    captured = {}

    class _Workflow:
        def __init__(self, steps):
            self.steps = steps

        def apply_async(self):
            captured["applied"] = True

    def _fake_chain(*steps):
        captured["steps"] = steps
        return _Workflow(steps)

    monkeypatch.setattr(onboarding_module, "chain", _fake_chain)

    result = onboarding_module.run_onboarding_pipeline.run(user_id=315)

    assert result["status"] == "started"
    assert captured["applied"] is True
    assert [step[0] for step in captured["steps"]] == [
        "bootstrap_indicator_histories",
        "store_daily_scores_task",
        "enqueue_first_dashboard_briefing",
        "generate_daily_report",
    ]
    assert captured["steps"][0][2] == {"user_id": 315, "enqueue_score_refresh": False}
    assert captured["steps"][2][2] == {"trigger": "onboarding_scores_ready"}
    assert conn.commit_count >= 1
    assert conn.closed is True
