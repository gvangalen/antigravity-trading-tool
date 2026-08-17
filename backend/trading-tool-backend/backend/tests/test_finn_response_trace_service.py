import asyncio

import pytest
from fastapi import HTTPException

from backend.api import ai_assistant_api
from backend.services import finn_response_trace_service as trace_service


def test_database_response_trace_captures_context_memory_freshness_and_handler(monkeypatch):
    monkeypatch.setattr(
        trace_service,
        "get_ai_availability",
        lambda: {
            "available": False,
            "mode": "deterministic_only",
            "reason": "ai_unavailable_budget",
        },
    )
    trace = trace_service.build_finn_response_trace(
        trace_id="trace-123",
        response={
            "response": "stored answer",
            "intent": "outcome_memory",
            "flow": "outcome_memory",
            "state": {
                "current_flow": "outcome_memory",
                "asset": "ETH",
                "outcome_memory": {"memory_pattern": "recovery"},
            },
            "analysis": {
                "context_confidence": {"level": "high", "entity_type": "asset"},
                "freshness": {
                    "status": "fresh",
                    "source_timestamp": "2026-07-20T10:00:00Z",
                    "age_seconds": 42,
                },
                "specialists": [{"name": "memory_agent"}],
            },
        },
        context={
            "page": "/asset",
            "page_type": "analysis",
            "symbol": "ETH",
            "timeframe": "1D",
            "updated_at": "2026-07-20T10:00:30Z",
            "raw_private_value": "must-not-leak",
        },
        route_source="finn",
        response_source="memory",
        response_handler="finn_plan_service.build_outcome_memory_response",
        latency_ms=12.345,
    )

    assert trace["context"]["asset"] == "ETH"
    assert trace["context"]["timeframe"] == "1D"
    assert trace["memory"] == {"used": True, "layers": ["outcome_memory"]}
    assert trace["specialist"]["contributors"] == ["memory_agent"]
    assert trace["decision"]["selection_reason"] == "memory_flow_selected"
    assert trace["fallback"] == {"used": False, "reason": None}
    assert trace["response"]["latency_ms"] == 12.35
    assert trace["data"]["freshness"][0]["status"] == "fresh"
    assert "must-not-leak" not in str(trace)


def test_budget_fallback_trace_explains_why_openai_was_not_used(monkeypatch):
    monkeypatch.setattr(
        trace_service,
        "get_ai_availability",
        lambda: {
            "available": False,
            "mode": "deterministic_only",
            "reason": "ai_unavailable_budget",
        },
    )
    trace = trace_service.build_finn_response_trace(
        trace_id="trace-budget",
        response={"response": "fallback", "intent": "analysis", "flow": "analysis"},
        context={"symbol": "BTC", "timeframe": "1W"},
        route_source="legacy_rescue",
        response_source="fallback",
        response_handler="ai_assistant_api._build_finn_core_rescue_envelope",
        legacy_rescue_reason="ai_unavailable_budget",
    )

    assert trace["decision"]["ai_available"] is False
    assert trace["decision"]["ai_reason"] == "ai_unavailable_budget"
    assert trace["decision"]["selection_reason"] == "ai_unavailable_budget"
    assert trace["fallback"] == {"used": True, "reason": "ai_unavailable_budget"}
    assert trace["context"]["asset"] == "BTC"
    assert trace["context"]["timeframe"] == "1W"


def test_trace_includes_asset_provenance_and_context_confidence(monkeypatch):
    monkeypatch.setattr(
        trace_service,
        "get_ai_availability",
        lambda: {
            "available": True,
            "mode": "full",
            "reason": None,
        },
    )
    trace = trace_service.build_finn_response_trace(
        trace_id="trace-provenance",
        response={
            "response": "ok",
            "intent": "portfolio_intelligence",
            "flow": "portfolio_intelligence",
            "analysis": {
                "asset_source": "user_preferences",
                "asset_confidence": "medium",
                "asset_user_scoped": True,
                "profile_confidence": "high",
                "setup_confidence": "high",
                "strategy_confidence": "medium",
                "bot_confidence": "low",
                "overall_context_confidence": "medium",
            },
            "state": {"asset": "AAPL"},
        },
        context={"symbol": "AAPL"},
        route_source="finn",
        response_source="openai",
        response_handler="finn_plan_service.build_portfolio_intelligence_response",
    )

    assert trace["context"]["asset"] == "AAPL"
    assert trace["context"]["asset_source"] == "user_preferences"
    assert trace["context"]["asset_confidence"] == "medium"
    assert trace["context"]["asset_user_scoped"] is True
    assert trace["context"]["profile_confidence"] == "high"
    assert trace["context"]["setup_confidence"] == "high"
    assert trace["context"]["strategy_confidence"] == "medium"
    assert trace["context"]["bot_confidence"] == "low"
    assert trace["context"]["overall_context_confidence"] == "medium"


def test_trace_endpoint_uses_authenticated_user_scope(monkeypatch):
    captured = {}

    def fake_lookup(*, user_id, trace_id):
        captured.update(user_id=user_id, trace_id=trace_id)
        return {"trace_id": trace_id, "decision": {"response_source": "deterministic"}}

    monkeypatch.setattr(ai_assistant_api.finn_product_analytics, "get_response_trace", fake_lookup)
    result = asyncio.run(
        ai_assistant_api.get_assistant_response_trace(
            "trace-owned",
            current_user={"id": 42},
        )
    )

    assert captured == {"user_id": 42, "trace_id": "trace-owned"}
    assert result["trace_id"] == "trace-owned"


def test_trace_endpoint_returns_404_when_trace_is_not_owned_or_missing(monkeypatch):
    monkeypatch.setattr(
        ai_assistant_api.finn_product_analytics,
        "get_response_trace",
        lambda **kwargs: None,
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            ai_assistant_api.get_assistant_response_trace(
                "trace-missing",
                current_user={"id": 42},
            )
        )

    assert exc_info.value.status_code == 404
