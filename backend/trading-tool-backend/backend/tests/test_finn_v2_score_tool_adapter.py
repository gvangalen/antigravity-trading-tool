from __future__ import annotations

import asyncio
from datetime import date

from backend.services.finn_v2_tool_adapters.score_tool_adapter import ScoreToolAdapter


def test_score_adapter_exposes_only_current_verified_components_and_benchmark():
    class SharedContext:
        async def benchmark_for_asset(self, user_id, asset, *, setups):
            assert (user_id, asset, setups) == (17, "BTC", [])
            return {
                "symbol": "BTC",
                "as_of": date.today(),
                "source_status": "stale_sources",
                "benchmark_score": None,
                "benchmark_weights": {"market_score": 0.4, "macro_score": 0.3, "technical_score": 0.3},
                "reported_scores": {"market_score": 30, "macro_score": None, "technical_score": 50},
                "component_source_status": {
                    "market_score": "fresh", "macro_score": "stale_source", "technical_score": "fresh",
                },
                "matches": [],
            }

    adapter = object.__new__(ScoreToolAdapter)
    adapter.context = SharedContext()

    result = asyncio.run(adapter.execute(user_id=17, asset="BTC"))

    assert result["source"] == "daily_scores_and_source_indicators"
    assert result["data"].reported_scores == {
        "market_score": 30, "macro_score": None, "technical_score": 50,
    }
    assert result["data"].benchmark_score is None
    assert result["data"].component_source_status["macro_score"] == "stale_source"
    assert "daily_scores" not in result["data"].dict()
    assert "master_score" not in result["data"].dict()


def test_score_adapter_returns_weighted_total_only_when_shared_context_proves_it():
    class SharedContext:
        async def benchmark_for_asset(self, user_id, asset, *, setups):
            assert (user_id, asset, setups) == (17, "ETH", [])
            return {
                "symbol": "ETH", "as_of": date.today(), "source_status": "available",
                "benchmark_score": 72,
                "benchmark_weights": {"market_score": 0.4, "macro_score": 0.3, "technical_score": 0.3},
                "reported_scores": {"market_score": 75, "macro_score": 70, "technical_score": 70},
                "component_source_status": {
                    "market_score": "fresh", "macro_score": "fresh", "technical_score": "fresh",
                },
                "matches": [],
            }

    adapter = object.__new__(ScoreToolAdapter)
    adapter.context = SharedContext()
    result = asyncio.run(adapter.execute(user_id=17, asset="ETH"))

    assert result["data"].benchmark_score == 72
    assert result["data"].source_status == "available"


def test_score_adapter_presents_component_source_times_without_milliseconds():
    class SharedContext:
        async def benchmark_for_asset(self, user_id, asset, *, setups):
            return {
                "symbol": asset,
                "as_of": date.today(),
                "source_status": "available",
                "benchmark_score": 40,
                "benchmark_weights": None,
                "reported_scores": {"market_score": 40},
                "component_source_status": {"market_score": "fresh"},
                "component_source_observed_at": {
                    "market": {"price": "2026-10-10T04:20:11.926000+00:00"},
                },
            }

    adapter = object.__new__(ScoreToolAdapter)
    adapter.context = SharedContext()
    result = asyncio.run(adapter.execute(user_id=17, asset="ETH"))

    assert result["data"].component_source_observed_at == {
        "market": {"price": "2026-10-10T04:20:11+00:00"},
    }
