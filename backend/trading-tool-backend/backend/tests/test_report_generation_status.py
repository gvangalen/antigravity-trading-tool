from datetime import timedelta
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.api import report_api
from backend.utils.auth_utils import create_token


def _client(monkeypatch, user_id=7, state="FAILURE", error="daily_report_ai_rate_limited"):
    app = FastAPI()
    app.include_router(report_api.router, prefix="/api")
    app.dependency_overrides[report_api.get_current_user] = lambda: {"id": user_id}
    monkeypatch.setattr(report_api, "AsyncResult", lambda *_args, **_kwargs: SimpleNamespace(
        state=state, result=RuntimeError(error),
    ))
    return TestClient(app)


def _token(owner=7, period="daily"):
    return create_token(
        {"sub": str(owner), "task_id": "task-123", "period": period},
        timedelta(hours=1), "report_generation",
    )


def test_report_generation_status_reports_typed_failure_without_raw_error(monkeypatch):
    response = _client(monkeypatch).post(
        "/api/report/daily/generation-status", json={"status_token": _token()},
    )
    assert response.status_code == 200
    assert response.json() == {"state": "FAILURE", "error_code": "ai_rate_limited"}


def test_report_generation_status_rejects_other_owner(monkeypatch):
    response = _client(monkeypatch, user_id=8).post(
        "/api/report/daily/generation-status", json={"status_token": _token(owner=7)},
    )
    assert response.status_code == 404


def test_report_generation_status_rejects_other_period(monkeypatch):
    response = _client(monkeypatch).post(
        "/api/report/daily/generation-status", json={"status_token": _token(period="weekly")},
    )
    assert response.status_code == 404


def test_report_generation_status_hides_unknown_worker_error(monkeypatch):
    response = _client(monkeypatch, error="sensitive backend details").post(
        "/api/report/daily/generation-status", json={"status_token": _token()},
    )
    assert response.json() == {"state": "FAILURE", "error_code": "generation_failed"}


@pytest.mark.parametrize("period", ["weekly", "monthly", "quarterly"])
def test_period_report_generation_status_exposes_typed_failure_to_owner(monkeypatch, period):
    response = _client(monkeypatch).post(
        f"/api/report/{period}/generation-status",
        json={"status_token": _token(period=period)},
    )
    assert response.status_code == 200
    assert response.json() == {"state": "FAILURE", "error_code": "ai_rate_limited"}


def test_period_report_generation_status_rejects_mismatched_period(monkeypatch):
    response = _client(monkeypatch).post(
        "/api/report/monthly/generation-status",
        json={"status_token": _token(period="weekly")},
    )
    assert response.status_code == 404
