import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.domain.asset_benchmark_weights import asset_benchmark_weights
from backend.services.asset_benchmark_copy_service import AssetBenchmarkCopyService
from backend.services.pair_benchmark_service import save_asset_benchmark_weights
from backend.api.workspace_api import AssetBenchmarkCopyWrite, post_asset_benchmark_copy


WEIGHTS = {"market": 0.5, "macro": 0.3, "technical": 0.2}


def test_asset_weights_override_global_only_for_the_selected_symbol():
    preferences = {"intelligence_weights": {"market": 0.2, "macro": 0.4, "technical": 0.4},
                   "asset_benchmark_weights": {"AAPL": WEIGHTS}}
    aapl, source = asset_benchmark_weights(preferences, "AAPL")
    spy, other_source = asset_benchmark_weights(preferences, "SPY")
    assert source == "asset"
    assert aapl == {"market_score": 0.5, "macro_score": 0.3, "technical_score": 0.2}
    assert other_source == "user_preferences"
    assert spy == {"market_score": 0.2, "macro_score": 0.4, "technical_score": 0.4}


def test_asset_weights_save_preserves_global_and_other_asset_settings():
    user = SimpleNamespace(ai_preferences={"intelligence_weights": {"market": 1},
                                            "asset_benchmark_weights": {"SPY": WEIGHTS}})
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
        scalar_one_or_none=lambda: user)), flush=AsyncMock(), commit=AsyncMock())
    original = deepcopy(user.ai_preferences)
    asyncio.run(save_asset_benchmark_weights(session, 7, "aapl", WEIGHTS))
    assert user.ai_preferences["intelligence_weights"] == original["intelligence_weights"]
    assert user.ai_preferences["asset_benchmark_weights"]["SPY"] == WEIGHTS
    assert user.ai_preferences["asset_benchmark_weights"]["AAPL"] == WEIGHTS
    session.commit.assert_awaited_once()


def test_cross_class_preview_keeps_compatible_indicators_and_explains_skips():
    service = object.__new__(AssetBenchmarkCopyService)
    source = {"key": "market:42", "symbol": "BTC", "market_id": 42,
              "asset_class": "crypto", "label": "BTC/USDT"}
    target = {"key": "asset:AAPL", "symbol": "AAPL", "market_id": None,
              "asset_class": "stock", "label": "AAPL"}
    service._scope = AsyncMock(side_effect=[source, target])
    source_items = {
        ("technical", "rsi"): {"category": "technical", "indicator": "rsi", "weight": 1,
                               "score_mode": "standard", "rules": []},
        ("macro", "etf_bitcoin_inflow"): {"category": "macro", "indicator": "etf_bitcoin_inflow",
                                          "weight": 1, "score_mode": "standard", "rules": []},
    }
    service._state = AsyncMock(side_effect=[(source_items, WEIGHTS), ({}, WEIGHTS)])
    service._unsupported_reason = AsyncMock(side_effect=["btc_only_source", None])
    preview = asyncio.run(service.preview(7, "market:42", "asset:AAPL"))
    assert preview["source_pair"] == "BTC/USDT"
    assert preview["target_pair"] == "AAPL"
    assert [item["indicator"] for item in preview["indicators"]] == ["rsi"]
    assert preview["unsupported"] == [{"indicator": "macro:etf_bitcoin_inflow", "reason": "btc_only_source"}]
    assert len(preview["revision"]) == 64


def test_pair_source_cannot_overwrite_the_base_configuration_it_inherits():
    service = object.__new__(AssetBenchmarkCopyService)
    service._scope = AsyncMock(side_effect=[
        {"key": "market:42", "symbol": "BTC", "market_id": 42},
        {"key": "asset:BTC", "symbol": "BTC", "market_id": None},
    ])
    service._state = AsyncMock()
    with pytest.raises(ValueError, match="source_pair_inherits_target_asset"):
        asyncio.run(service.preview(7, "market:42", "asset:BTC"))
    service._state.assert_not_awaited()


def test_cross_class_compatibility_uses_catalog_and_requires_review_of_custom_rules():
    service = object.__new__(AssetBenchmarkCopyService)
    rules = AsyncMock(return_value=[object()] * 5)
    service.indicators = SimpleNamespace(repository=SimpleNamespace(get_system_indicator_rules=rules),
                                         _has_complete_rules=lambda rows: len(rows) == 5)
    source = {"symbol": "BTC", "asset_class": "crypto"}
    target = {"symbol": "AAPL", "asset_class": "stock"}
    standard_rsi = {"category": "technical", "indicator": "rsi", "weight": 1,
                    "score_mode": "standard", "rules": []}
    assert asyncio.run(service._unsupported_reason(standard_rsi, source, target)) is None
    assert asyncio.run(service._unsupported_reason({**standard_rsi, "score_mode": "custom"}, source, target)) == "custom_rules_need_review"
    btc_inflow = {**standard_rsi, "category": "macro", "indicator": "etf_bitcoin_inflow"}
    assert asyncio.run(service._unsupported_reason(btc_inflow, source, target)) == "btc_only_source"
    rules.assert_awaited_once_with("technical", "rsi")


def test_cross_class_apply_rejects_changed_preview_before_any_config_write():
    session = SimpleNamespace(execute=AsyncMock(), add=AsyncMock(), commit=AsyncMock())
    service = object.__new__(AssetBenchmarkCopyService)
    service.session = session
    service.preview = AsyncMock(return_value={"revision": "a" * 64, "indicators": [{"indicator": "rsi"}]})
    with pytest.raises(ValueError, match="benchmark_preview_changed"):
        asyncio.run(service.apply(7, "market:42", "asset:AAPL", "b" * 64))
    session.add.assert_not_awaited()
    session.commit.assert_not_awaited()


def test_cross_class_apply_replaces_only_target_configs_and_saves_target_weights():
    old_target = SimpleNamespace(category="market", indicator="volume", enabled=True,
                                 config_json={"score_mode": "standard"}, priority=100)
    added = []
    calls = 0

    async def execute(_statement, parameters=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            assert parameters == {"user_id": 7}
            return SimpleNamespace()
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [old_target]))

    session = SimpleNamespace(execute=execute, add=added.append, commit=AsyncMock())
    service = object.__new__(AssetBenchmarkCopyService)
    service.session = session
    service.preview = AsyncMock(return_value={
        "revision": "a" * 64,
        "indicators": [{"category": "technical", "indicator": "rsi", "weight": 0.8,
                        "score_mode": "standard", "rules": []}],
        "unsupported": [{"indicator": "macro:etf_bitcoin_inflow", "reason": "btc_only_source"}],
        "source_weights": WEIGHTS,
    })
    service._scope = AsyncMock(return_value={"key": "asset:AAPL", "symbol": "AAPL",
                                            "market_id": None, "asset_class": "stock"})
    with patch("backend.services.asset_benchmark_copy_service.save_asset_benchmark_weights",
               new_callable=AsyncMock) as save_weights:
        result = asyncio.run(service.apply(7, "market:42", "asset:AAPL", "a" * 64))

    assert old_target.enabled is False
    assert len(added) == 1
    assert added[0].symbol == "AAPL" and added[0].market_id is None
    assert added[0].indicator == "rsi" and added[0].enabled is True
    assert result["copied"] == 1 and result["skipped"][0]["reason"] == "btc_only_source"
    save_weights.assert_awaited_once_with(session, 7, "AAPL", WEIGHTS, commit=False)
    session.commit.assert_awaited_once()


def test_copy_source_list_reads_only_the_owner_and_excludes_the_target():
    calls = []
    inherited_market = SimpleNamespace(id=43, asset_symbol="BTC")
    isolated_market = SimpleNamespace(id=44, asset_symbol="BTC")
    inherited_row = SimpleNamespace(user_id=7, market_id=None, category="technical",
                                    indicator="rsi", enabled=True)

    async def execute(_statement, parameters=None):
        calls.append(parameters)
        if len(calls) == 1:
            return SimpleNamespace(all=lambda: [("BTC", 42), ("BTC", None), ("AAPL", None)])
        if len(calls) == 2:
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [inherited_market, isolated_market]))
        return SimpleNamespace(all=lambda: [(42,)])

    service = object.__new__(AssetBenchmarkCopyService)
    service.session = SimpleNamespace(execute=execute)
    service.pairs = SimpleNamespace(rows=AsyncMock(side_effect=[[inherited_row], []]))

    async def scope(key):
        return {"key": key, "label": {"market:42": "BTC/USDT", "market:43": "BTC/EUR", "asset:BTC": "BTC"}.get(key, "AAPL"),
                "asset_class": "crypto" if key.startswith("market:") or key == "asset:BTC" else "stock",
                "market_id": 42 if key == "market:42" else 43 if key == "market:43" else None,
                "symbol": "BTC" if key.startswith("market:") or key == "asset:BTC" else "AAPL"}

    service._scope = scope
    sources = asyncio.run(service.sources(7, "asset:AAPL"))
    assert sources == [
        {"key": "asset:BTC", "label": "BTC", "asset_class": "crypto"},
        {"key": "market:43", "label": "BTC/EUR", "asset_class": "crypto"},
        {"key": "market:42", "label": "BTC/USDT", "asset_class": "crypto"},
    ]
    assert service.pairs.rows.await_args_list[0].args == (7, inherited_market)
    assert service.pairs.rows.await_args_list[1].args == (7, isolated_market)
    assert calls[2] == {"user_id": 7}


def test_copied_asset_refresh_queues_score_after_materialization():
    from backend.celery_task import market_task

    def complete_without_provider_calls(coroutine):
        coroutine.close()
        return {"market": "complete"}

    with (patch.object(market_task, "run_celery_coroutine", side_effect=complete_without_provider_calls) as materialize,
          patch("backend.celery_task.store_daily_scores_task.store_daily_scores_task.apply_async") as score):
        result = market_task.materialize_asset_benchmark.run(7, "aapl")
    assert result["status"] == "score_refresh_queued"
    assert result["symbol"] == "AAPL"
    materialize.assert_called_once()
    score.assert_called_once_with(kwargs={"user_id": 7, "symbol": "AAPL"})


@pytest.mark.parametrize("target_key,market_id", [("asset:AAPL", None), ("market:42", 42)])
def test_copy_api_refreshes_only_the_confirmed_target(target_key, market_id):
    result = {"ok": True, "symbol": "AAPL" if market_id is None else "BTC",
              "market_id": market_id}
    service = SimpleNamespace(apply=AsyncMock(return_value=result))
    payload = AssetBenchmarkCopyWrite(source_key="market:41", target_key=target_key,
                                      revision="a" * 64)
    with (patch("backend.api.workspace_api.AssetBenchmarkCopyService", return_value=service),
          patch("backend.api.workspace_api.queue_asset_benchmark_materialization", return_value=True) as asset_queue,
          patch("backend.api.workspace_api.queue_exact_market_owner_repair") as market_queue):
        response = asyncio.run(post_asset_benchmark_copy(payload, {"id": 7}, SimpleNamespace()))
    assert response == result
    service.apply.assert_awaited_once_with(7, "market:41", target_key, "a" * 64)
    if market_id is None:
        asset_queue.assert_called_once_with(7, "AAPL")
        market_queue.assert_not_called()
    else:
        market_queue.assert_called_once_with(7, 42)
        asset_queue.assert_not_called()
