"""Report language follows the current request, even before account sync completes."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import report_api
from backend.services import locale_service, report_service


def test_period_reports_read_frozen_v2_snapshot_for_web_and_pdf(monkeypatch):
    snapshot = {"content_locale": "nl", "report_v2": {"version": 2, "period": "weekly"}}
    row = {"report_date": "2026-10-31", "meta_json": json.dumps({"score_source_snapshot": snapshot})}
    service = report_service.ReportService.__new__(report_service.ReportService)
    service.repository = SimpleNamespace(
        get_latest_report=AsyncMock(return_value=row),
        get_report_by_date=AsyncMock(return_value=row),
    )
    monkeypatch.setattr(service, "_get_user_locale", AsyncMock(return_value="nl"))
    monkeypatch.setattr(report_service, "localize_report_payload", AsyncMock(side_effect=lambda data, _: data))

    latest = asyncio.run(service.get_latest_report(7, "weekly_reports"))
    by_date = asyncio.run(service.get_report_by_date(7, "weekly_reports", "2026-10-31"))

    assert latest["score_source_snapshot"] == snapshot
    assert by_date["score_source_snapshot"] == snapshot


def test_report_request_locale_wins_over_stored_account_locale(monkeypatch):
    async def translate(**kwargs):
        fields = json.loads(kwargs["prompt"].split("\n\n", 1)[1])
        return json.dumps({key: "Der Markt ist vorsichtig bei Score 50."
                           for key in fields})

    monkeypatch.setattr(locale_service, "ask_gpt_text_async", translate)
    monkeypatch.setattr(report_service, "UserRepository", lambda _db: SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(ai_preferences={"locale": "nl"})),
    ))
    service = asyncio.run(report_api.get_report_service(db=object(), request_locale="de"))
    service.repository.get_latest_report = AsyncMock(return_value={
        "executive_summary": "De markt is voorzichtig bij score 50.",
        "market_score": 50,
        "score_source_snapshot": {"content_locale": "nl", "assets": []},
    })

    report = asyncio.run(service.get_latest_report(7, "daily_reports"))

    assert report["executive_summary"] == "Der Markt ist vorsichtig bei Score 50."
    assert report["market_score"] == 50
    assert report["score_source_snapshot"] == {"content_locale": "nl", "assets": []}


def test_report_http_header_selects_german_before_account_preference_sync(monkeypatch):
    async def translate(**kwargs):
        fields = json.loads(kwargs["prompt"].split("\n\n", 1)[1])
        return json.dumps({key: "Der Markt ist vorsichtig bei Score 50."
                           for key in fields})

    class Reports:
        def __init__(self, db):
            self.db = db

        async def get_latest_report(self, user_id, table_name, symbol=None):
            assert (user_id, table_name) == (7, "daily_reports")
            return {"executive_summary": "De markt is voorzichtig bij score 50.",
                    "market_score": 50,
                    "score_source_snapshot": {"content_locale": "nl", "assets": []}}

    monkeypatch.setattr(locale_service, "ask_gpt_text_async", translate)
    monkeypatch.setattr(report_api, "ReportRepository", Reports)
    monkeypatch.setattr(report_service, "UserRepository", lambda _db: SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(ai_preferences={"locale": "nl"})),
    ))
    app = FastAPI()
    app.include_router(report_api.router, prefix="/api")
    app.dependency_overrides[report_api.get_current_user] = lambda: {"id": 7}
    app.dependency_overrides[report_api.get_db] = lambda: object()

    response = TestClient(app).get("/api/report/daily/latest", headers={"X-Locale": "de"})

    assert response.status_code == 200
    assert response.json()["executive_summary"] == "Der Markt ist vorsichtig bei Score 50."
    assert response.json()["market_score"] == 50
