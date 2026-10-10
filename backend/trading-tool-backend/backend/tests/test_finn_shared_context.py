import asyncio
import json
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services.finn_shared_context_service import FinnSharedContextService
from backend.services import finn_unified_report_service as reports
from backend.schemas.finn_v2_evidence_schema import IndicatorConfigurationData, IndicatorConfigurationItem
from backend.celery_task import daily_report_task
from backend.services.finn_plan_service import FinnPlanService
from backend.services import finn_plan_service as finn_plan_module
from backend.services.finn_v2_tool_adapters.score_tool_adapter import ScoreToolAdapter


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


def test_shared_context_reads_twenty_owner_assets_without_turning_missing_scores_into_zero():
    symbols = [f"ASSET{i:02}" for i in range(20)]

    class _Session:
        async def execute(self, _query, params):
            assert params == {"user_id": 7}
            return _Rows([(symbol,) for symbol in symbols])

    service = FinnSharedContextService(_Session())
    service.users.get_by_id = AsyncMock(return_value=SimpleNamespace(ai_preferences={"locale": "nl"}))
    service.setups.get_all_setups = AsyncMock(return_value=[])
    service.strategies.query_strategies = AsyncMock(return_value=[])
    service.bots.get_bot_configs = AsyncMock(return_value=[])
    service.benchmark_for_asset = AsyncMock(side_effect=lambda user_id, asset, **_: {
        "symbol": asset, "source_status": "missing_scores", "benchmark_score": None,
        "reported_scores": {"market_score": None, "macro_score": None, "technical_score": None},
        "matches": [],
    })
    service.indicators.execute = AsyncMock(return_value={
        "data": SimpleNamespace(model_dump=lambda **_: {"market": [], "macro": [], "technical": []}),
    })

    snapshot = asyncio.run(service.for_user(7))

    assert len(snapshot["assets"]) == 20
    assert {item["symbol"] for item in snapshot["assets"]} == set(symbols)
    assert all(item["benchmark"]["benchmark_score"] is None for item in snapshot["assets"])
    assert all(item["indicator_lookup_status"] == "available" for item in snapshot["assets"])
    assert service.benchmark_for_asset.await_count == 20


def test_shared_context_keeps_failed_indicator_lookup_unknown():
    class _Session:
        async def execute(self, _query, _params):
            raise AssertionError("explicit asset must not query watchlist")

    service = FinnSharedContextService(_Session())
    service.users.get_by_id = AsyncMock(return_value=SimpleNamespace(ai_preferences={"locale": "de"}))
    service.setups.get_all_setups = AsyncMock(return_value=[])
    service.strategies.query_strategies = AsyncMock(return_value=[])
    service.bots.get_bot_configs = AsyncMock(return_value=[])
    service.benchmark_for_asset = AsyncMock(return_value={
        "source_status": "missing_scores", "benchmark_score": None, "matches": [],
    })
    service.indicators.execute = AsyncMock(side_effect=RuntimeError("provider unavailable"))

    snapshot = asyncio.run(service.for_user(7, symbol="ETH"))

    assert snapshot["assets"][0]["indicator_configuration"] is None
    assert snapshot["assets"][0]["indicator_lookup_status"] == "unknown"
    assert snapshot["assets"][0]["benchmark"]["benchmark_score"] is None


def test_shared_context_serializes_real_indicator_schema_without_losing_configuration():
    class _Session:
        async def execute(self, _query, _params):
            raise AssertionError("explicit asset must not query watchlist")

    service = FinnSharedContextService(_Session())
    service.users.get_by_id = AsyncMock(return_value=SimpleNamespace(ai_preferences={"locale": "nl"}))
    service.setups.get_all_setups = AsyncMock(return_value=[])
    service.strategies.query_strategies = AsyncMock(return_value=[])
    service.bots.get_bot_configs = AsyncMock(return_value=[])
    service.benchmark_for_asset = AsyncMock(return_value={
        "source_status": "missing_scores", "benchmark_score": None, "matches": [],
    })
    service.indicators.execute = AsyncMock(return_value={"data": IndicatorConfigurationData(
        symbol="ETH", market=[IndicatorConfigurationItem(indicator="Price", category="market")],
        macro=[IndicatorConfigurationItem(indicator="DXY", category="macro")],
        technical=[IndicatorConfigurationItem(indicator="RSI", category="technical")],
    )})

    snapshot = asyncio.run(service.for_user(7, symbol="ETH"))
    asset = snapshot["assets"][0]
    assert asset["indicator_lookup_status"] == "available"
    assert [asset["indicator_configuration"][category][0]["indicator"]
            for category in ("market", "macro", "technical")] == ["Price", "DXY", "RSI"]


def test_unified_report_uses_shared_benchmark_and_does_not_claim_missing_score(monkeypatch):
    context = {
        "locale": "nl", "profile": {}, "observed_at": "2026-10-07T12:00:00+00:00",
        "assets": [{
            "symbol": "BTC", "setups": [], "strategies": [], "bots": [],
            "benchmark": {
                "source_status": "missing_scores", "benchmark_score": None,
                "reported_scores": {"market_score": None, "macro_score": None, "technical_score": None},
                "matches": [],
            },
        }],
    }

    async def _load(_user_id):
        return context

    monkeypatch.setattr(reports, "_load_context", _load)
    monkeypatch.setattr(reports, "ask_gpt_json", lambda **_: {"error": "provider_unavailable"})

    result = reports.generate_unified_daily_report_sections(7)

    assert result["market_score"] is None
    assert result["setup_score"] is None
    assert "geen bevestigde setupmatch" in result["setup_validation"]
    assert result["watchlist"][0]["benchmark"]["benchmark_score"] is None
    assert result["meta"]["source"] == "finn_shared_context.v1"


def test_chat_today_and_report_project_the_same_verified_score_snapshot(monkeypatch):
    assessment = {
        "symbol": "ETH", "as_of": "2026-10-10", "source_status": "available",
        "benchmark_score": 70,
        "benchmark_weights": {"market_score": 1 / 3, "macro_score": 1 / 3, "technical_score": 1 / 3},
        "reported_scores": {"market_score": 80, "macro_score": 70, "technical_score": 60},
        "component_source_status": {
            "market_score": "fresh", "macro_score": "fresh", "technical_score": "fresh",
        },
        "matches": [{"setup_id": 9, "name": "ETH Plan", "symbol": "ETH",
                     "status": "matches", "score": 80, "is_active": True,
                     "components": {}}],
    }
    context = {
        "locale": "nl", "profile": {}, "assets": [{
            "symbol": "ETH", "benchmark": assessment,
            "setups": [{"id": 9, "name": "ETH Plan", "symbol": "ETH", "timeframe": "1D"}],
            "strategies": [{"id": 10, "setup_id": 9, "name": "ETH Strategy"}],
            "bots": [], "indicator_lookup_status": "available",
            "indicator_configuration": {"market": [], "macro": [], "technical": []},
        }],
    }
    source = SimpleNamespace(benchmark_for_asset=AsyncMock(return_value=assessment))
    chat_adapter = ScoreToolAdapter(object())
    chat_adapter.context = source
    chat = asyncio.run(chat_adapter.execute(user_id=7, asset="ETH"))["data"]

    monkeypatch.setattr(finn_plan_module, "FinnSharedContextService", lambda _session: source)
    today = asyncio.run(FinnPlanService(db_session=object())._first_dashboard_latest_analysis(
        7, asset="ETH", asset_analysis={"setup": {"id": 9}}, has_scores=True,
    ))
    monkeypatch.setattr(reports, "_load_context", lambda _id: asyncio.sleep(0, result=context))
    monkeypatch.setattr(reports, "ask_gpt_json", lambda **_: {"error": "provider_unavailable"})
    report = reports.generate_unified_daily_report_sections(7)

    assert chat.benchmark_score == today["benchmark_score"] == report["watchlist"][0]["benchmark"]["benchmark_score"] == 70
    assert chat.reported_scores["market_score"] == today["reported_scores"]["market_score"] == report["watchlist"][0]["benchmark"]["reported_scores"]["market_score"] == 80
    assert today["setup_match_score"] == report["setup_score"] == 80
    assert report["active_strategy"]["setup_name"] == "ETH Strategy"


def test_period_report_uses_dated_owner_facts_and_does_not_count_planned_decision_as_trade(monkeypatch):
    captured = {}
    context = {
        "period": "weekly", "period_start": "2026-10-05", "period_end": "2026-10-07",
        "shared": {"locale": "nl", "assets": [{"symbol": "BTC", "bots": [],
            "benchmark": {"source_status": "missing_scores", "matches": []}}]},
        "dated_scores": [],
        "bot_decisions": [{"action": "buy", "status": "planned", "amount_eur": 100}],
        "daily_report_summaries": [],
    }

    async def _load(user_id, period):
        assert (user_id, period) == (7, "weekly")
        return context

    def _provider(**kwargs):
        captured.update(kwargs)
        return {"error": "provider_unavailable"}

    monkeypatch.setattr(reports, "_load_period_context", _load)
    monkeypatch.setattr(reports, "ask_gpt_json", _provider)
    result = reports.generate_weekly_report_sections(7)
    assert result["meta"]["source"] == "finn_shared_context.v1"
    assert result["macro_score"] is None
    assert "geen bevestigde setupmatch" in result["setup_performance"]
    assert "not an executed trade" in captured["system_role"]
    assert captured["model_override"] == "gpt-6-luna"
    assert captured["reasoning_effort"] == "none"


def test_daily_report_keeps_saved_plan_and_unscored_indicators_without_stale_scores(monkeypatch):
    """New-user report must agree with Analyse and the saved plan after persistence."""
    context = {
        "locale": "nl", "profile": {}, "observed_at": "2026-10-08T08:00:00+00:00",
        "assets": [{
            "symbol": "ETH",
            "setups": [{"id": 8, "name": "ETH maandelijkse DCA", "setup_type": "dca"}],
            "strategies": [{"id": 9, "setup_id": 8, "name": "ETH DCA strategie",
                            "setup_name": "ETH maandelijkse DCA", "symbol": "ETH",
                            "timeframe": "1D", "entry": None, "base_amount": 120}],
            "bots": [{"id": 10, "name": "ETH Paper", "is_live": False}],
            "indicator_lookup_status": "available",
            "indicator_configuration": {
                "market": [{"indicator": "Price", "enabled": True}],
                "macro": [{"indicator": "DXY", "enabled": True}],
                "technical": [{"indicator": "RSI", "enabled": True}],
            },
            "benchmark": {
                "source_status": "stale_sources", "benchmark_score": None,
                "reported_scores": {"market_score": 10, "macro_score": None,
                                    "technical_score": 50},
                "component_source_status": {"market_score": "stale_source",
                                            "macro_score": "missing_score",
                                            "technical_score": "stale_source"},
                "matches": [],
            },
        }],
    }
    captured = {}

    async def _load(_user_id):
        return context

    def _provider(**kwargs):
        captured.update(kwargs)
        return {key: "Actuele marktscore 10/100; technische score 50/100. Geen strategie."
                for key in reports.REPORT_SECTIONS}

    monkeypatch.setattr(reports, "_load_context", _load)
    monkeypatch.setattr(reports, "ask_gpt_json", _provider)
    result = reports.generate_unified_daily_report_sections(7)
    for key in ("executive_summary", "market_analysis", "macro_context",
                "technical_analysis", "setup_validation", "strategy_implication", "bot_strategy"):
        assert "10/100" not in result[key]
        assert "50/100" not in result[key]
        assert "Geen strategie" not in result[key]
    assert "ETH DCA strategie" in result["strategy_implication"]
    assert "Price" in result["market_analysis"]
    assert "DXY" in result["macro_context"]
    assert "RSI" in result["technical_analysis"]
    assert result["active_strategy"]["setup_name"] == "ETH maandelijkse DCA"
    assert result["macro_indicator_highlights"] == [{"indicator": "DXY", "symbol": "ETH"}]
    assert result["watchlist"][0]["benchmark"]["reported_scores"] == {
        "market_score": None, "macro_score": None, "technical_score": None,
    }
    sent = json.loads(captured["prompt"])["context"]["assets"][0]
    assert sent["scores"] == {"market_score": None, "macro_score": None,
                              "technical_score": None}
    assert "reported_scores" not in sent


def test_daily_report_task_persists_typed_report_facts(monkeypatch):
    """The Celery writer must not drop the facts before the saved report is read."""
    captured = {}

    class _DB:
        def commit(self):
            captured["committed"] = True

        def rollback(self):
            raise AssertionError("unexpected rollback")

        def close(self):
            pass

    class _Writer:
        def __init__(self, _db):
            pass

        def upsert_daily_report(self, **kwargs):
            captured["write"] = kwargs

    monkeypatch.setattr(daily_report_task, "SessionLocal", _DB)
    monkeypatch.setattr(daily_report_task, "DailyReportWriteRepository", _Writer)
    monkeypatch.setattr(daily_report_task, "get_user_email_snapshot", lambda _id: None)
    monkeypatch.setattr(daily_report_task, "ai_usage_context", lambda **_: nullcontext())
    monkeypatch.setattr(daily_report_task, "create_report_snapshot", lambda **_: (1, "local"))
    monkeypatch.setattr(daily_report_task, "generate_unified_daily_report_sections", lambda **_: {
        "executive_summary": "ETH plan opgeslagen; actuele benchmark onvolledig.",
        "market_analysis": "ETH: Price ingesteld; geen bruikbare actuele score.",
        "strategy_implication": "Opgeslagen strategieën: ETH DCA strategie.",
        "active_strategy": {"setup_name": "ETH maandelijkse DCA", "symbol": "ETH"},
        "market_indicator_highlights": [{"indicator": "Price", "symbol": "ETH"}],
        "macro_indicator_highlights": [{"indicator": "DXY", "symbol": "ETH"}],
        "technical_indicator_highlights": [{"indicator": "RSI", "symbol": "ETH"}],
        "market_score": None, "macro_score": None, "technical_score": None,
    })

    daily_report_task.generate_daily_report.run(7)

    saved = captured["write"]
    assert captured["committed"] is True
    assert saved["market_score"] is None
    assert saved["sections"]["active_strategy"]["setup_name"] == "ETH maandelijkse DCA"
    assert saved["sections"]["macro_indicator_highlights"] == [
        {"indicator": "DXY", "symbol": "ETH"}]
