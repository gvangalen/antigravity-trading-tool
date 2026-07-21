import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import backend.services.finn_specialist_service as specialist_module
from backend.services.finn_specialist_service import FinnSpecialistService


def _detail(symbol="BTC", value=54.0):
    return {
        "symbol": symbol,
        "category": "technical",
        "period": "day",
        "indicator": {
            "name": "rsi",
            "indicator_key": "rsi",
            "value": value,
            "score": 50.0,
            "period": "day",
            "source": "technical_indicators",
            "freshness": {"as_of": "2026-07-21T08:00:00+00:00", "stale": False},
            "score_contribution": {"weight": 0.5, "weighted_points": 25.0},
        },
        "category_score": {"score": 60.0, "period": "day"},
        "category_freshness": {"as_of": "2026-07-21T08:00:00+00:00", "stale": False},
        "ai_calls": 0,
    }


def _service(detail):
    service = object.__new__(FinnSpecialistService)
    service.workspace = SimpleNamespace(get_indicator_detail=AsyncMock(return_value=detail))
    return service


def test_budget_unavailable_returns_deterministic_detail_without_model_attempt(monkeypatch):
    ask = AsyncMock()
    monkeypatch.setattr(specialist_module, "ask_gpt_json_async", ask)
    monkeypatch.setattr(specialist_module, "_cache_get_sync", lambda key: None)
    monkeypatch.setattr(
        specialist_module,
        "get_ai_availability",
        lambda: {"available": False, "reason": "ai_unavailable_budget", "mode": "deterministic_only"},
    )

    result = asyncio.run(
        _service(_detail()).explain_indicator(
            user_id=7,
            symbol="BTC",
            category="technical",
            indicator="rsi",
            period="day",
            timeframe="1D",
            locale="nl",
        )
    )

    assert result["status"] == "unavailable"
    assert result["reason"] == "ai_unavailable_budget"
    assert result["detail"]["indicator"]["value"] == 54.0
    assert result["ai_calls"] == 0
    ask.assert_not_awaited()


def test_successful_specialist_result_is_cached_by_scoped_input_hash(monkeypatch):
    cache = {}
    ask = AsyncMock(
        return_value={
            "summary": "RSI is neutral.",
            "why_it_counts": "It contributes half of the technical average.",
            "confirmation": "Monitor momentum and price structure.",
            "conflicts": [],
        }
    )
    monkeypatch.setattr(specialist_module, "ask_gpt_json_async", ask)
    monkeypatch.setattr(specialist_module, "get_ai_availability", lambda: {"available": True, "mode": "ai_enabled"})
    monkeypatch.setattr(specialist_module, "_cache_get_sync", lambda key: cache.get(key))
    monkeypatch.setattr(specialist_module, "_cache_set_sync", lambda key, value: cache.__setitem__(key, value))
    service = _service(_detail())

    first = asyncio.run(
        service.explain_indicator(
            user_id=7,
            symbol="BTC",
            category="technical",
            indicator="rsi",
            period="day",
            timeframe="1D",
            locale="en",
        )
    )
    second = asyncio.run(
        service.explain_indicator(
            user_id=7,
            symbol="BTC",
            category="technical",
            indicator="rsi",
            period="day",
            timeframe="1D",
            locale="en",
        )
    )

    assert first["source"] == "openai"
    assert first["ai_calls"] == 1
    assert second["source"] == "cache"
    assert second["ai_calls"] == 0
    assert first["input_hash"] == second["input_hash"]
    ask.assert_awaited_once()


def test_input_hash_changes_with_asset_scope(monkeypatch):
    monkeypatch.setattr(specialist_module, "_cache_get_sync", lambda key: None)
    monkeypatch.setattr(
        specialist_module,
        "get_ai_availability",
        lambda: {"available": False, "reason": "ai_unavailable_budget"},
    )
    btc = asyncio.run(
        _service(_detail("BTC")).explain_indicator(
            user_id=7, symbol="BTC", category="technical", indicator="rsi", period="day", timeframe="1D", locale="nl"
        )
    )
    eth = asyncio.run(
        _service(_detail("ETH")).explain_indicator(
            user_id=7, symbol="ETH", category="technical", indicator="rsi", period="day", timeframe="1D", locale="nl"
        )
    )

    assert btc["input_hash"] != eth["input_hash"]
