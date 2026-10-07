import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services.finn_shared_context_service import FinnSharedContextService
from backend.services import finn_unified_report_service as reports


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
