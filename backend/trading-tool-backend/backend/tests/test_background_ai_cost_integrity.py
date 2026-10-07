from pathlib import Path

from backend.celery_task.celery_app import celery_app
from backend.services import ai_usage_observability_service as usage


ROOT = Path(__file__).resolve().parents[1]


def test_retired_independent_agent_modules_are_absent():
    retired = (
        "macro_ai_agent", "market_ai_agent", "technical_ai_agent",
        "score_ai_agent", "strategy_ai_agent", "report_ai_agent",
        "weekly_report_agent", "monthly_report_agent", "quarterly_report_agent",
    )
    assert all(not (ROOT / "ai_agents" / f"{name}.py").exists() for name in retired)


def test_high_frequency_jobs_do_not_invoke_background_ai():
    bot_source = (ROOT / "celery_task" / "trading_bot_task.py").read_text()
    market_source = (ROOT / "celery_task" / "market_task.py").read_text()
    market_ingest = market_source.split("def fetch_market_indicators", 1)[1]
    assert "run_daily_strategy_snapshot" not in bot_source
    assert "run_market_agent" not in market_ingest
    assert "run_market_agent_daily" not in market_source


def test_bot_uses_saved_strategy_and_measured_match_instead_of_ai_snapshot():
    source = (ROOT / "ai_agents" / "trading_bot_agent.py").read_text()
    assert "_get_saved_strategy_plan(" in source
    assert "snapshot = _get_saved_strategy_plan(" in source
    assert "snapshot = _get_active_strategy_snapshot(" not in source


def test_independent_ai_agent_schedules_are_retired():
    schedule = celery_app.conf.beat_schedule
    assert {"macro_ai", "market_ai", "technical_ai", "dispatch_strategy_snapshot",
            "run_master_score_ai"}.isdisjoint(schedule)
    assert "dispatch_finn_daily_report" in schedule
    assert "dispatch_regime_memory" in schedule


def test_deploy_does_not_run_agents_for_a_hardcoded_user():
    source = (ROOT / "deploy-backend.sh").read_text()
    assert "UID = 30" not in source
    assert "from ai_agents." not in source


def test_reuse_telemetry_records_zero_cost_and_saved_estimate(monkeypatch):
    captured = {}
    monkeypatch.setattr(usage, "estimate_blocked_cost", lambda **_kwargs: 0.0123)
    monkeypatch.setattr(usage, "get_user_email_snapshot", lambda _user_id: "user@example.com")
    monkeypatch.setattr(usage, "log_ai_usage_sync", lambda **kwargs: captured.update(kwargs))

    usage.log_background_ai_skip(
        user_id=7,
        symbol="BTC",
        purpose="setup_analysis",
        entry_point="setup_ai_agent:run_setup_agent",
    )

    assert captured["status"] == "input_unchanged"
    assert captured["prompt_tokens"] == 0
    assert captured["completion_tokens"] == 0
    assert captured["cost"] == 0.0
    assert captured["estimated_cost_if_full"] == 0.0123
    assert captured["symbol"] == "BTC"
    assert captured["request_source"] == "background_job"


def test_admin_telemetry_exposes_full_ai_and_background_reuse_comparison():
    service_source = (ROOT / "services" / "admin_ai_service.py").read_text()
    schema_source = (ROOT / "schemas" / "admin_schema.py").read_text()

    assert "status = 'input_unchanged'" in service_source
    assert '"full_ai_requests"' in service_source
    assert '"reuse_hits"' in service_source
    assert '"reuse_savings"' in service_source
    assert '"reuse_hit_rate"' in service_source
    assert "reuse_savings_month_eur" in schema_source
