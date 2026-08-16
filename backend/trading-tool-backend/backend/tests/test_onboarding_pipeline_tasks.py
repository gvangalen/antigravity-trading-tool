from types import SimpleNamespace

from backend.celery_task import bootstrap_agents_task as bootstrap_tasks
from backend.celery_task import daily_report_task as daily_report_module
from backend.celery_task import macro_task as macro_module
from backend.celery_task import market_task as market_module
from backend.celery_task import onboarding_task as onboarding_module
from backend.celery_task import setup_task as setup_tasks
from backend.celery_task import store_daily_scores_task as score_module
from backend.celery_task import strategy_task as strategy_module
from backend.celery_task import technical_task as technical_module


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


class _DelayStub:
    def __init__(self, name, calls):
        self.name = name
        self.calls = calls

    def delay(self, *args, **kwargs):
        self.calls.append((self.name, args, kwargs))
        return SimpleNamespace(id=f"{self.name}-task")


def test_run_onboarding_pipeline_queues_expected_workflow(monkeypatch):
    conn = _Connection(rows=[(1,)])
    monkeypatch.setattr(onboarding_module, "get_db_connection", lambda: conn)

    monkeypatch.setattr(score_module, "store_daily_scores_task", _TaskStub("store_daily_scores_task"))
    monkeypatch.setattr(macro_module, "generate_macro_insight", _TaskStub("generate_macro_insight"))
    monkeypatch.setattr(market_module, "run_market_agent_daily", _TaskStub("run_market_agent_daily"))
    monkeypatch.setattr(technical_module, "run_technical_agent_daily", _TaskStub("run_technical_agent_daily"))
    monkeypatch.setattr(setup_tasks, "run_setup_agent_daily", _TaskStub("run_setup_agent_daily"))
    monkeypatch.setattr(strategy_module, "run_daily_strategy_snapshot", _TaskStub("run_daily_strategy_snapshot"))
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
        "store_daily_scores_task",
        "generate_macro_insight",
        "run_market_agent_daily",
        "run_technical_agent_daily",
        "run_setup_agent_daily",
        "run_daily_strategy_snapshot",
        "generate_daily_report",
        "enqueue_first_dashboard_briefing",
    ]
    assert conn.commit_count >= 1
    assert conn.closed is True


def test_bootstrap_agents_task_queues_report_and_first_dashboard_briefing(monkeypatch):
    calls = []
    monkeypatch.setattr(bootstrap_tasks, "fetch_market_data", lambda: calls.append(("fetch_market_data",)))
    monkeypatch.setattr(bootstrap_tasks, "fetch_macro_data", lambda user_id: calls.append(("fetch_macro_data", user_id)))
    monkeypatch.setattr(bootstrap_tasks, "fetch_technical_data_day", lambda user_id: calls.append(("fetch_technical_data_day", user_id)))
    monkeypatch.setattr(bootstrap_tasks, "run_setup_agent_daily", lambda user_id: calls.append(("run_setup_agent_daily", user_id)))
    monkeypatch.setattr(bootstrap_tasks, "run_market_agent_daily", lambda user_id: calls.append(("run_market_agent_daily", user_id)))
    monkeypatch.setattr(bootstrap_tasks, "snapshot_all_for_user", lambda user_id: calls.append(("snapshot_all_for_user", user_id)))
    monkeypatch.setattr(bootstrap_tasks, "generate_daily_report", _DelayStub("generate_daily_report", calls))
    monkeypatch.setattr(bootstrap_tasks, "enqueue_first_dashboard_briefing", _DelayStub("enqueue_first_dashboard_briefing", calls))

    result = bootstrap_tasks.bootstrap_agents_task.run(user_id=315)

    assert result["status"] == "complete"
    assert ("generate_daily_report", (), {"user_id": 315}) in calls
    assert (
        "enqueue_first_dashboard_briefing",
        (),
        {"user_id": 315, "trigger": "bootstrap_agents"},
    ) in calls
