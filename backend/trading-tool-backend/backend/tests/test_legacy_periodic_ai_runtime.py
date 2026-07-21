from backend.celery_task.celery_app import (
    LEGACY_PERIODIC_AI_SCHEDULES,
    celery_app,
)
from backend.celery_task.setup_task import run_setup_agent_daily
from backend.services.legacy_ai_runtime import legacy_periodic_ai_enabled


def test_legacy_periodic_ai_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_LEGACY_PERIODIC_AI", raising=False)

    assert legacy_periodic_ai_enabled() is False
    assert LEGACY_PERIODIC_AI_SCHEDULES.isdisjoint(celery_app.conf.beat_schedule)


def test_legacy_setup_task_stops_before_agent_work(monkeypatch):
    monkeypatch.delenv("ENABLE_LEGACY_PERIODIC_AI", raising=False)

    result = run_setup_agent_daily.run(user_id=42)

    assert result == {
        "status": "disabled",
        "reason": "legacy_periodic_ai_disabled",
        "user_id": 42,
    }


def test_legacy_periodic_ai_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("ENABLE_LEGACY_PERIODIC_AI", "true")

    assert legacy_periodic_ai_enabled() is True
