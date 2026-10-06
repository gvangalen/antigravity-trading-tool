import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services import score_service as score_service_module
from backend.services.score_service import ScoreService


def test_daily_scores_read_does_not_initialize_or_refresh_indicators(monkeypatch):
    repository = SimpleNamespace(
        db=object(),
        fetch_daily_scores=AsyncMock(return_value=None),
    )

    with pytest.raises(LookupError):
        asyncio.run(ScoreService(repository).get_daily_scores(7, "ETH"))

    repository.fetch_daily_scores.assert_awaited_once_with(7, "ETH")


def test_daily_score_response_uses_current_match_instead_of_legacy_setup_score(monkeypatch):
    class MatchService:
        def __init__(self, _session):
            pass

        async def for_asset(self, user_id, symbol):
            assert (user_id, symbol) == (7, "BTC")
            return {"matches": [{"setup_id": 12, "name": "BTC plan", "symbol": "BTC",
                                "timeframe": "4H", "setup_type": "trade", "score": 83,
                                "is_active": True, "components": {}, "status": "matches"}],
                        "source_status": "available", "benchmark_score": 72,
                        "component_source_status": {"macro_score": "fresh", "technical_score": "fresh", "market_score": "fresh"},
                    "benchmark_weights": {"market_score": 0.5, "macro_score": 0.25,
                                          "technical_score": 0.25}}

    monkeypatch.setattr(score_service_module, "SetupMarketMatchService", MatchService)
    report_date = date(2026, 10, 3)
    repository = SimpleNamespace(
        db=object(),
        fetch_daily_scores=AsyncMock(return_value={
            "report_date": report_date,
            "macro_score": 100,
            "technical_score": 75,
            "market_score": 100,
            "setup_score": 50,
        }),
        fetch_active_setups=AsyncMock(return_value=[]),
    )

    result = asyncio.run(ScoreService(repository).get_daily_scores(7, "BTC"))

    assert result.report_date == report_date
    assert result.setup.score == 83
    assert result.benchmark_score == 72
    repository.fetch_active_setups.assert_not_awaited()


def test_daily_score_response_hides_stale_component_and_its_explanation(monkeypatch):
    class MatchService:
        def __init__(self, _session):
            pass

        async def for_asset(self, *_args):
            return {"matches": [], "source_status": "missing_scores", "benchmark_score": None,
                    "benchmark_weights": {},
                    "component_source_status": {"macro_score": "stale_source",
                                                "technical_score": "missing_score",
                                                "market_score": "fresh"}}

    monkeypatch.setattr(score_service_module, "SetupMarketMatchService", MatchService)
    repository = SimpleNamespace(db=object(), fetch_daily_scores=AsyncMock(return_value={
        "macro_score": 100, "macro_interpretation": "Strong bullish signal",
        "macro_top_contributors": ["old indicator"],
        "technical_score": None, "market_score": 70,
    }))
    result = asyncio.run(ScoreService(repository).get_daily_scores(7, "BTC"))
    assert result.macro.score is None
    assert result.macro.top_contributors == []
    assert result.macro.source_status == "stale_source"
    assert result.technical.score is None
    assert result.market.score == 70


def test_analysis_weights_ignore_historical_ai_master_weights(monkeypatch):
    class Matcher:
        def __init__(self, _session):
            pass

        async def for_asset(self, user_id, symbol, *, setups):
            assert (user_id, symbol, setups) == (7, "BTC", [])
            return {"benchmark_score": 62, "as_of": date.today(),
                    "benchmark_weights": {"market_score": 1 / 3,
                                          "macro_score": 1 / 3,
                                          "technical_score": 1 / 3}}

    monkeypatch.setattr(score_service_module, "SetupMarketMatchService", Matcher)
    repository = SimpleNamespace(db=object(), get_master_score=AsyncMock(return_value=SimpleNamespace(
        avg_score=88, trend="up", bias="bullish", risk="low", summary="old",
        date=date.today(), top_signals={"weights": {"market": 0.8, "macro": 0.1, "technical": 0.1}},
    )))
    users = SimpleNamespace(get_by_id=AsyncMock(return_value=SimpleNamespace(ai_preferences={})))
    result = asyncio.run(ScoreService(repository, users).get_master_score(7, "BTC"))
    assert result.weights == {"market": 1 / 3, "macro": 1 / 3, "technical": 1 / 3}
    assert result.master_score == 62
    repository.get_master_score.assert_not_awaited()
