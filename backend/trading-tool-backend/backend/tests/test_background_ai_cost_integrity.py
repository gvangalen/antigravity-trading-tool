from datetime import date
from pathlib import Path

from backend.ai_agents.score_ai_agent import fetch_today_insights
from backend.ai_agents.setup_ai_agent import (
    _reuse_or_generate_explanation,
    _setup_input_hash,
)
from backend.celery_task.strategy_task import (
    input_is_unchanged,
    stable_input_hash,
)
from backend.services import ai_usage_observability_service as usage


ROOT = Path(__file__).resolve().parents[1]


def test_unchanged_setup_input_never_evaluates_ai_generator():
    calls = []

    def generate():
        calls.append("called")
        return "new explanation"

    explanation, reused = _reuse_or_generate_explanation("stored explanation", generate)

    assert explanation == "stored explanation"
    assert reused is True
    assert calls == []


def test_setup_hash_ignores_small_score_noise_but_changes_materially():
    base = {
        "setup_id": 9,
        "name": "Swing",
        "setup_type": "trade",
        "score": 41,
        "components": {"m": 41, "mk": 51, "t": 61},
    }
    noisy = {**base, "score": 42, "components": {"m": 42, "mk": 52, "t": 62}}
    changed = {**base, "score": 47}

    assert _setup_input_hash("BTC", base) == _setup_input_hash("BTC", noisy)
    assert _setup_input_hash("BTC", base) != _setup_input_hash("BTC", changed)


def test_strategy_hash_is_stable_and_reuse_decision_is_deterministic():
    left = {"setup": {"id": 1}, "scores": {"market": 40, "macro": 35}}
    right = {"scores": {"macro": 35, "market": 40}, "setup": {"id": 1}}
    current = stable_input_hash(left)

    assert current == stable_input_hash(right)
    assert input_is_unchanged(current, current) is True
    assert input_is_unchanged(None, current) is False
    assert input_is_unchanged(current, stable_input_hash({**left, "setup": {"id": 2}})) is False


def test_high_frequency_jobs_do_not_invoke_background_ai():
    bot_source = (ROOT / "celery_task" / "trading_bot_task.py").read_text()
    market_source = (ROOT / "celery_task" / "market_task.py").read_text()
    market_ingest = market_source.split("def fetch_market_indicators", 1)[1]

    assert "run_daily_strategy_snapshot" not in bot_source
    assert "run_market_agent(user_id=user_id)" not in market_ingest
    assert "run_market_agent_daily" in market_source


def test_strategy_snapshot_reuses_first_ai_response_for_explanation():
    source = (ROOT / "celery_task" / "strategy_task.py").read_text()

    assert "analyze_strategy.delay(" not in source
    assert "analysis[\"input_hash\"] = input_hash" in source
    assert "input_is_unchanged(previous_input_hash, input_hash)" in source


class _InsightCursor:
    def __init__(self):
        self.params = None
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params):
        self.calls.append((query, params))
        self.params = params

    def fetchone(self):
        category, _user_id, selected_date, symbol, _preferred = self.params
        return (category, 42, "stable", "neutral", "low", "summary", [], selected_date, symbol)


class _InsightConnection:
    def __init__(self):
        self.cursor_instance = _InsightCursor()

    def cursor(self):
        return self.cursor_instance


def test_master_inputs_are_selected_for_requested_asset_without_btc_fallback():
    conn = _InsightConnection()

    insights = fetch_today_insights(conn, user_id=7, symbol="eth")

    assert set(insights) == {"macro", "market", "technical", "setup", "strategy"}
    assert all(item[1][3] == "ETH" for item in conn.cursor_instance.calls)
    assert all("symbol IN (%s, 'GLOBAL')" in item[0] for item in conn.cursor_instance.calls)
    assert all(value["symbol"] == "ETH" for value in insights.values())


def test_master_writer_and_reader_share_asset_scoped_contract():
    agent_source = (ROOT / "ai_agents" / "score_ai_agent.py").read_text()
    repository_source = (ROOT / "infrastructure" / "repositories" / "score_repository.py").read_text()
    migration_source = (ROOT / "scripts" / "migrations" / "2026_07_20_asset_scoped_ai_insights.py").read_text()

    assert "ON CONFLICT (user_id, category, symbol, date)" in agent_source
    assert "AiCategoryInsight.symbol == symbol" in repository_source
    assert "uq_ai_category_insights_user_category_symbol_date" in migration_source


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
