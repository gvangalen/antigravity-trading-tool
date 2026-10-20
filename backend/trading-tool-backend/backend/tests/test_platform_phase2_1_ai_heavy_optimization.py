import asyncio
from types import SimpleNamespace

from backend.services import report_service as report_module
from backend.services.report_service import ReportService


def test_daily_report_preview_cache_reuses_generated_preview(monkeypatch):
    report_module._daily_report_preview_cache.clear()
    calls = {"count": 0}

    def fake_generate_daily_report_sections(*, user_id=None):
        calls["count"] += 1
        return {"headline": f"Daily preview for user {user_id}"}

    monkeypatch.setattr(report_module, "generate_daily_report_sections", fake_generate_daily_report_sections)

    service = ReportService(SimpleNamespace())
    first = asyncio.run(service.preview_daily_report(21))
    second = asyncio.run(service.preview_daily_report(21))

    assert calls["count"] == 1
    assert first == second
    assert first["report"]["headline"] == "Daily preview for user 21"


def test_daily_report_preview_prefers_todays_existing_report(monkeypatch):
    report_module._daily_report_preview_cache.clear()

    class _Repo:
        async def get_latest_report(self, user_id, table_name, symbol=None):
            from datetime import datetime

            return {
                "report_date": datetime.utcnow().date(),
                "summary": "Daily summary ready",
                "market_analysis": "Market calm",
                "outlook": "Wait for confirmation",
                "macro_score": 50.0,
                "technical_score": 40.0,
                "market_score": 35.0,
                "setup_score": 72.0,
            }

    def fail_generate(*args, **kwargs):
        raise AssertionError("generator should not run when today's report exists")

    monkeypatch.setattr(report_module, "generate_daily_report_sections", fail_generate)

    service = ReportService(_Repo())
    preview = asyncio.run(service.preview_daily_report(33))

    assert preview["source"] == "latest_daily_report"
    assert preview["report"]["executive_summary"] == "Daily summary ready"
    assert preview["report"]["market_analysis"] == "Market calm"
