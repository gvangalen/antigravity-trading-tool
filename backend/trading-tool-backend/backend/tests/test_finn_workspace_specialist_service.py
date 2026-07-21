import asyncio
from unittest.mock import AsyncMock

import backend.services.finn_workspace_specialist_service as specialist_module
from backend.services.finn_workspace_specialist_service import FinnWorkspaceSpecialistService


def _detail(subject_type="setup", symbol="BTC", subject_id=12):
    return {
        "subject_type": subject_type,
        "subject_id": subject_id,
        "symbol": symbol,
        "source": f"{subject_type}_records",
        "as_of": "2026-07-21T08:00:00+00:00",
        "readiness": {"ready": True, "missing": []},
        "facts": {"name": "Test", "status": "ready"},
    }


def _service(detail):
    service = object.__new__(FinnWorkspaceSpecialistService)
    service.session = None
    service._detail = AsyncMock(return_value=detail)
    return service


def _explain(service, **overrides):
    payload = {
        "user_id": 7,
        "subject_type": "setup",
        "subject_id": 12,
        "symbol": "BTC",
        "timeframe": "1D",
        "period": "day",
        "locale": "nl",
    }
    payload.update(overrides)
    return asyncio.run(service.explain(**payload))


def test_budget_unavailable_keeps_facts_and_never_calls_model(monkeypatch):
    ask = AsyncMock()
    monkeypatch.setattr(specialist_module, "ask_gpt_json_async", ask)
    monkeypatch.setattr(specialist_module, "_cache_get_sync", lambda key: None)
    monkeypatch.setattr(
        specialist_module,
        "get_ai_availability",
        lambda: {"available": False, "reason": "ai_unavailable_budget", "mode": "deterministic_only"},
    )

    result = _explain(_service(_detail()))

    assert result["status"] == "unavailable"
    assert result["reason"] == "ai_unavailable_budget"
    assert result["detail"]["facts"]["status"] == "ready"
    assert result["trace"]["context"]["asset"] == "BTC"
    assert result["ai_calls"] == 0
    ask.assert_not_awaited()


def test_successful_workspace_context_is_reused_from_cache(monkeypatch):
    cache = {}
    ask = AsyncMock(
        return_value={
            "summary": "The setup is complete.",
            "findings": ["All required rules are present."],
            "risks": [],
            "next_step": "Validate it against the current market context.",
        }
    )
    monkeypatch.setattr(specialist_module, "ask_gpt_json_async", ask)
    monkeypatch.setattr(specialist_module, "get_ai_availability", lambda: {"available": True, "mode": "ai_enabled"})
    monkeypatch.setattr(specialist_module, "_cache_get_sync", lambda key: cache.get(key))
    monkeypatch.setattr(specialist_module, "_cache_set_sync", lambda key, value: cache.__setitem__(key, value))
    service = _service(_detail())

    first = _explain(service, locale="en")
    second = _explain(service, locale="en")

    assert first["source"] == "openai"
    assert first["ai_calls"] == 1
    assert second["source"] == "cache"
    assert second["ai_calls"] == 0
    assert first["input_hash"] == second["input_hash"]
    ask.assert_awaited_once()


def test_hash_is_scoped_by_specialist_asset_and_period(monkeypatch):
    monkeypatch.setattr(specialist_module, "_cache_get_sync", lambda key: None)
    monkeypatch.setattr(
        specialist_module,
        "get_ai_availability",
        lambda: {"available": False, "reason": "ai_unavailable_budget", "mode": "deterministic_only"},
    )

    setup = _explain(_service(_detail("setup", "BTC")))
    strategy = _explain(
        _service(_detail("strategy", "BTC")),
        subject_type="strategy",
    )
    eth = _explain(_service(_detail("setup", "ETH")), symbol="ETH")
    weekly = _explain(_service(_detail("setup", "BTC")), period="week")

    assert len({setup["input_hash"], strategy["input_hash"], eth["input_hash"], weekly["input_hash"]}) == 4
