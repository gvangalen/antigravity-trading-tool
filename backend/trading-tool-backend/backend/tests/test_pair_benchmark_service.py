import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.pair_benchmark_service import (
    PairBenchmarkCopyService, benchmark_weights, save_benchmark_weights,
)
from backend.engine.trading_bot_execution import _get_current_benchmark_weights


def test_pair_weights_override_legacy_user_weights():
    queries = []

    async def execute(statement, parameters):
        queries.append((str(statement), parameters))
        return SimpleNamespace(first=lambda: ({"market": 0.6, "macro": 0.3, "technical": 0.1},))

    weights, source = asyncio.run(benchmark_weights(SimpleNamespace(execute=execute), 7, 41))
    assert weights == {"market_score": 0.6, "macro_score": 0.3, "technical_score": 0.1}
    assert source == "market"
    assert len(queries) == 1
    assert queries[0][1] == {"user_id": 7, "market_id": 41}


def test_new_pair_weights_do_not_follow_later_global_preference_changes():
    queries = []

    async def execute(statement, parameters):
        queries.append(str(statement))
        return SimpleNamespace(first=lambda: None)

    weights, source = asyncio.run(benchmark_weights(SimpleNamespace(execute=execute), 7, 99))
    assert source == "equal_default"
    assert all(abs(value - 1 / 3) < 1e-9 for value in weights.values())
    assert len(queries) == 1


def test_invalid_category_weights_cannot_be_saved():
    session = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())
    with pytest.raises(ValueError, match="invalid_benchmark_weights"):
        asyncio.run(save_benchmark_weights(session, 7, 41,
                                           {"market": 1, "macro": 0, "technical": 0, "extra": 1}))
    session.execute.assert_not_awaited()


def test_copy_replaces_target_settings_without_copying_scores_or_changing_source():
    source = SimpleNamespace(id=41, asset_symbol="BTC", quote_currency="EUR")
    target = SimpleNamespace(id=42, asset_symbol="BTC", quote_currency="USDT")
    selected = {
        ("technical", "rsi"): {"category": "technical", "indicator": "rsi",
                               "weight": 1.4, "score_mode": "custom",
                               "rules": [{"range_min": low, "range_max": low + 20, "score": 90}
                                         for low in (0, 20, 40, 60, 80)]},
    }
    previous = {
        ("market", "price"): {"category": "market", "indicator": "price",
                              "weight": 1, "score_mode": "standard", "rules": []},
    }
    source_weights = {"market": 0.5, "macro": 0.3, "technical": 0.2}
    target_weights = {"market": 1 / 3, "macro": 1 / 3, "technical": 1 / 3}
    added = []

    async def execute(statement, _parameters=None):
        if "FROM user_indicator_configs" in str(statement):
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))
        return SimpleNamespace()

    session = SimpleNamespace(execute=execute, add=added.append, commit=AsyncMock())
    service = PairBenchmarkCopyService(session)
    service.configs.market = AsyncMock(side_effect=lambda market_id: {41: source, 42: target}[market_id])
    service._state = AsyncMock(side_effect=lambda _owner, market: (
        (selected, source_weights) if market.id == 41 else (previous, target_weights)))

    async def run():
        preview = await service.preview(7, 41, 42)
        assert preview["replace"] == ["market:price"]
        result = await service.apply(7, 41, 42, preview["revision"])
        return result

    result = asyncio.run(run())
    assert result["copied"] == 1
    assert {(row.category, row.indicator, row.enabled) for row in added} == {
        ("technical", "rsi", True), ("market", "price", False),
    }
    assert next(row for row in added if row.indicator == "rsi").config_json["weight"] == 1.4
    assert selected[("technical", "rsi")]["rules"][0]["score"] == 90
    session.commit.assert_awaited_once()


def test_copy_rejects_changed_preview():
    session = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())
    service = PairBenchmarkCopyService(session)
    service.preview = AsyncMock(return_value={"revision": "different"})
    with pytest.raises(ValueError, match="benchmark_preview_changed"):
        asyncio.run(service.apply(7, 41, 42, "old"))
    session.commit.assert_not_awaited()


def test_bot_reads_weights_for_its_exact_pair_and_owner():
    commands = []

    class Cursor:
        def execute(self, sql, parameters):
            commands.append((sql, parameters))

        def fetchone(self):
            return ({"market": 0.2, "macro": 0.3, "technical": 0.5},)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

    weights, source = _get_current_benchmark_weights(
        SimpleNamespace(cursor=lambda: Cursor()), 7, "BTC", 42)
    assert source == "market"
    assert weights == {"market_score": 0.2, "macro_score": 0.3, "technical_score": 0.5}
    assert len(commands) == 1
    assert commands[0][1] == (7, 42)
