from datetime import datetime, timedelta
from types import SimpleNamespace

from backend.services.report_service import ReportService
from backend.utils import openai_client as openai_module


def test_openai_quota_breaker_short_circuits_json_calls(monkeypatch):
    openai_module._openai_runtime_state.update(
        {
            "quota_exhausted_until": 0.0,
            "quota_failures": 0,
            "blocked_calls": 0,
            "text_calls": 0,
            "json_calls": 0,
            "last_error": None,
            "last_error_at": None,
        }
    )
    monkeypatch.setattr(openai_module, "client", object())
    monkeypatch.setattr(openai_module, "api_key", "sk-test")
    monkeypatch.setattr(openai_module, "QUOTA_COOLDOWN_SECONDS", 600)

    openai_module._mark_quota_exhausted()
    result = openai_module.ask_gpt_json(prompt="{}", system_role="system")

    assert result == {"error": "quota"}
    status = openai_module.get_openai_runtime_status()
    assert status["quota_breaker_active"] is True
    assert status["blocked_calls"] >= 1


class _Repo:
    def __init__(self, latest_report):
        self.latest_report = latest_report

    async def get_latest_report(self, user_id, table_name, symbol=None):
        return self.latest_report


def test_generate_report_reuses_recent_daily_report_without_queueing_task(monkeypatch):
    now = datetime.utcnow()
    repository = _Repo(
        {
            "report_date": now.date(),
            "generated_at": now - timedelta(minutes=5),
        }
    )
    service = ReportService(repository)

    class _Task:
        id = "should-not-run"

    monkeypatch.setattr("backend.services.report_service.generate_daily_report", SimpleNamespace(delay=lambda **kwargs: _Task()))

    result = __import__("asyncio").run(service.generate_report(7, "daily"))

    assert result["source"] == "existing_daily_report"
    assert result["task_id"] is None
