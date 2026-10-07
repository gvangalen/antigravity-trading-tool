from backend.celery_task.celery_app import celery_app
from backend.celery_task.setup_task import run_setup_agent_daily


def test_only_finn_report_is_scheduled_from_ai_report_family():
    schedule = celery_app.conf.beat_schedule
    assert "dispatch_finn_daily_report" in schedule
    assert "dispatch_regime_memory" in schedule
    assert {"macro_ai", "market_ai", "technical_ai",
            "dispatch_strategy_snapshot", "run_master_score_ai", "dispatch_daily_report"}.isdisjoint(schedule)


def test_retired_setup_agent_remains_a_noop_for_queued_messages():
    assert run_setup_agent_daily.run(user_id=42) == {
        "status": "disabled", "reason": "retired_setup_ai_agent", "user_id": 42,
    }
