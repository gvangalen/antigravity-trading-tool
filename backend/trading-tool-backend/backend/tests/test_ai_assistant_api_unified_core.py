import asyncio
import json
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks
from starlette.requests import Request

from backend.api.ai_assistant_api import (
    assistant_chat,
    assistant_chat_stream,
    _finalize_finn_response,
    _prepare_finn_envelope,
    _build_finn_core_rescue_envelope,
    _audit_context_summary,
    _attach_trader_profile_metadata,
    _trader_profile_event_metadata,
    _record_behavioral_response_events,
    _legacy_response_is_generic_failure,
    _legacy_response_needs_finn_rescue,
    _infer_response_source,
    get_finn_mission_control,
)
from backend.schemas.assistant_schema import AssistantChatRequest
from backend.infrastructure.repositories.conversation_state_repository import ConversationStateRepository
from backend.services.finn_plan_service import FinnPlanService


def _finn():
    return FinnPlanService(db_session=None)


PRODUCTION_FINN_QUESTION_CONTRACTS = [
    (
        "A1",
        "Bekijk mijn BTC-profiel, indicatoren, setup, strategie en gekoppelde bot. Wat is volgens jou op dit moment het belangrijkste ontbrekende onderdeel van mijn plan? Geef één concrete observatie en één vervolgstap.",
        "build_portfolio_intelligence_response",
        "portfolio_intelligence",
        "plan_review",
    ),
    (
        "A2",
        "Past mijn huidige BTC-strategie bij mijn risicoprofiel en tradingstijl? Noem één goede aansluiting en één mogelijk conflict.",
        "build_decision_review_response",
        "decision_review",
        "market_review",
    ),
    (
        "A3",
        "Welke indicatoren gebruik ik momenteel voor BTC, en welk belangrijk perspectief ontbreekt mogelijk nog in mijn analyse?",
        "build_indicator_insight_response",
        "indicator_insight",
        "fact_lookup",
    ),
    (
        "B1",
        "Wat is mijn actieve BTC-setup en op welke timeframes is deze gebaseerd?",
        "build_context_explain_response",
        "context_explain",
        "fact_lookup",
    ),
    (
        "B2",
        "Welke belangrijkste entryvoorwaarde uit mijn BTC-strategie moet bevestigd zijn voordat mijn plan een entry toestaat?",
        "build_context_explain_response",
        "context_explain",
        "fact_lookup",
    ),
    (
        "B3",
        "Welke bot is aan mijn BTC-strategie gekoppeld, en staat deze bot momenteel live?",
        "build_context_explain_response",
        "context_explain",
        "fact_lookup",
    ),
    (
        "B4",
        "Waarom heeft mijn gekoppelde BTC-bot nu geen positie geopend? Scheid wat je zeker weet van wat nog niet bevestigd kan worden.",
        "build_context_explain_response",
        "context_explain",
        "fact_lookup",
    ),
]


def _raw_request():
    return Request({"type": "http", "headers": [], "client": ("127.0.0.1", 12345)})


async def _stream_request():
    return None


def _build_canonical_runtime_context(context):
    return {
        **(context or {}),
        "user_id": 30,
        "page": "/bot",
        "page_type": "bot",
        "symbol": "BTC",
        "asset": "BTC",
        "asset_source": "workspace_state",
        "asset_confidence": "high",
        "asset_user_scoped": True,
        "setup_id": 501,
        "strategy_id": 701,
        "bot_id": 901,
        "missing_context": [],
        "entity_confidence": {
            "asset": "high",
            "setup": "high",
            "strategy": "high",
            "bot": "high",
        },
        "context_builder": "assistant_context_repository.build_canonical_context_graph",
        "canonical_context_graph": {
            "user_id": 30,
            "asset": "BTC",
            "missing_context": [],
            "entity_confidence": {
                "asset": "high",
                "setup": "high",
                "strategy": "high",
                "bot": "high",
            },
            "setup": {"id": 501, "name": "BTC setup", "timeframe": "4H", "symbol": "BTC"},
            "strategy": {"id": 701, "setup_id": 501, "name": "BTC strategy"},
            "bot": {"id": 901, "strategy_id": 701, "name": "BTC bot", "is_live": False},
        },
    }


def _patch_canonical_endpoint_runtime(monkeypatch, *, case_id, expected_builder, expected_flow):
    finn = _finn()
    finn.issue_response_actions = AsyncMock()
    finn.persist_response_state = AsyncMock()

    async def fake_apply_context_graph(*, db, user_id, query, context_payload):
        return _build_canonical_runtime_context(context_payload)

    async def fake_localize(payload, **kwargs):
        return payload

    async def fake_no_disconnect():
        return False

    def payload():
        return {
            "response": f"{case_id} response",
            "intent": expected_flow,
            "flow": expected_flow,
            "state": {
                "current_flow": expected_flow,
            },
            "reasoning": {
                "confidence_score": 0.91,
                "risk_detected": False,
                "reasons": [f"{case_id} contract"],
                "coaching_level": "standard",
            },
        }

    builder_names = [
        "build_portfolio_intelligence_response",
        "build_decision_review_response",
        "build_indicator_insight_response",
        "build_context_explain_response",
    ]
    for builder_name in builder_names:
        setattr(finn, builder_name, AsyncMock(side_effect=lambda *args, _builder=builder_name, **kwargs: payload()))

    monkeypatch.setattr("backend.api.ai_assistant_api._new_finn_plan_service", lambda db, trace_id=None: finn)
    monkeypatch.setattr("backend.api.ai_assistant_api._apply_canonical_finn_context_graph", fake_apply_context_graph)
    monkeypatch.setattr("backend.api.ai_assistant_api._enrich_with_trader_profile", AsyncMock(side_effect=lambda db, user_id, payload=None, query=None: dict(payload or {})))
    monkeypatch.setattr("backend.api.ai_assistant_api._apply_assistant_rate_limit", lambda **kwargs: None)
    monkeypatch.setattr("backend.api.ai_assistant_api._record_finn_product_event", lambda **kwargs: {})
    monkeypatch.setattr("backend.api.ai_assistant_api._localize_finn_response_payload", fake_localize)
    monkeypatch.setattr("backend.api.ai_assistant_api.get_ai_availability", lambda: {"available": True, "mode": "full", "reason": None})
    monkeypatch.setattr("backend.services.finn_response_trace_service.get_ai_availability", lambda: {"available": True, "mode": "full", "reason": None})

    service = SimpleNamespace(
        state_repo=SimpleNamespace(get_state=AsyncMock(return_value=None)),
        get_chat_response=AsyncMock(),
        _classify_intent=lambda query: "general_help",
    )
    raw_stream_request = SimpleNamespace(is_disconnected=AsyncMock(side_effect=fake_no_disconnect))
    return finn, service, raw_stream_request


async def _collect_stream_envelope(response):
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    payload = "".join(chunks)
    for block in payload.split("\n\n"):
        if block.startswith("event: envelope\n"):
            data = block.split("data: ", 1)[1]
            return json.loads(data)
    raise AssertionError(f"No envelope event found in stream payload: {payload}")


def test_legacy_response_source_is_fallback_when_ai_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        "backend.api.ai_assistant_api.get_ai_availability",
        lambda: {"available": False, "reason": "ai_unavailable_budget"},
    )

    source = _infer_response_source({}, route_source="legacy_assistant")

    assert source == "fallback"


def test_legacy_response_source_is_openai_when_ai_is_available(monkeypatch):
    monkeypatch.setattr(
        "backend.api.ai_assistant_api.get_ai_availability",
        lambda: {"available": True, "reason": None},
    )

    source = _infer_response_source({}, route_source="legacy_assistant")

    assert source == "openai"


def test_audit_context_summary_includes_profile_match_metadata():
    summary = _audit_context_summary(
        {
            "page": "/dashboard",
            "symbol": "BTC",
            "trader_profile_used": True,
            "trader_profile_summary": "investor | 1w",
            "profile_match_mode": "direct_match",
            "profile_match_reason": "Stored trader profile aligns directly.",
            "profile_conflict_detected": False,
        }
    )

    assert summary["trader_profile_used"] is True
    assert summary["profile_match_mode"] == "direct_match"
    assert "aligns directly" in summary["profile_match_reason"]


def test_attach_trader_profile_metadata_adds_conflict_fields():
    payload = _attach_trader_profile_metadata(
        {"analysis": {}},
        {
            "trader_profile_used": True,
            "trader_profile_summary": "investor | 1w",
            "profile_match_mode": "mixed_profile_page_context_priority",
            "profile_match_reason": "Current intraday context gets priority.",
            "profile_conflict_detected": True,
        },
    )

    assert payload["analysis"]["trader_profile_used"] is True
    assert payload["analysis"]["profile_match_mode"] == "mixed_profile_page_context_priority"
    assert payload["analysis"]["profile_conflict_detected"] is True


def test_trader_profile_event_metadata_includes_behavior_flags():
    metadata = _trader_profile_event_metadata(
        {
            "trader_profile_used": True,
            "trader_profile_summary": "swing_trader | 4h",
            "trader_profile": {
                "behavior_flags": ["fomo", "overtrades"],
            },
        }
    )

    assert metadata["trader_profile_used"] is True
    assert metadata["behavior_flags"] == ["fomo", "overtrades"]
    assert metadata["behavior_flag"] == "fomo"


def test_record_behavioral_response_events_tracks_profile_guidance_and_friction(monkeypatch):
    recorded = []

    def fake_record_event(*, user_id, event):
        recorded.append((user_id, event))
        return event

    monkeypatch.setattr("backend.api.ai_assistant_api.finn_product_analytics.record_event", fake_record_event)

    _record_behavioral_response_events(
        user_id=30,
        response={
            "intent": "priority_engine",
            "flow": "priority_engine",
            "next_best_action": "Review BTC setup",
            "analysis": {
                "profile_guidance": "Voor jouw profiel telt vooral discipline.",
                "profile_habit_alignment": {
                    "primary_alignment": {
                        "flag": "fomo",
                        "label": "FOMO / najagen",
                        "summary": "Je profiel noemt FOMO en je recente usage bevestigt datzelfde patroon.",
                        "evidence_strength": "high",
                        "matched_sources": ["memory_v2", "outcome_memory"],
                    }
                },
            },
            "state": {
                "current_flow": "priority_engine",
                "pending_behavioral_memory_friction": {
                    "type": "profile_fomo",
                    "message": "Je profiel en recente evidence bevestigen FOMO als actief patroon.",
                    "requires_ack": True,
                    "source": "profile_habit_alignment",
                },
            },
        },
        context_payload={
            "session_id": "sess-1",
            "page": "/report",
            "symbol": "BTC",
            "trader_profile_used": True,
            "trader_profile_summary": "swing_trader | 4h | behavior:fomo",
            "trader_profile": {"behavior_flags": ["fomo"]},
        },
        route_source="finn",
        trace_id="trace-1",
    )

    assert len(recorded) == 3
    assert all(event["event_name"] == "behavioral_intervention_seen" for _, event in recorded)
    assert recorded[0][1]["metadata"]["intervention_type"] == "profile_guidance"
    assert recorded[1][1]["metadata"]["intervention_type"] == "profile_habit_alignment"
    assert recorded[1][1]["metadata"]["matched_sources_count"] == 2
    assert recorded[2][1]["metadata"]["intervention_type"] == "pending_behavioral_memory_friction"
    assert recorded[2][1]["metadata"]["requires_ack"] is True


def test_assistant_chat_passes_enriched_profile_context_into_legacy_service(monkeypatch):
    captured = {}

    async def fake_enrich_with_trader_profile(db, user_id, payload=None, *, query=None):
        enriched = dict(payload or {})
        enriched.update({
            "page": "/dashboard",
            "symbol": "BTC",
            "trader_profile_used": True,
            "trader_profile_summary": "swing_trader | 4h | behavior:fomo",
            "trader_profile": {"trader_types": ["swing_trader"], "behavior_flags": ["fomo"]},
        })
        return enriched

    async def fake_get_chat_response(user_id, query, history, context, trace_id=None, session_id=None):
        captured["context"] = context
        return ("Legacy antwoord", None, None, {"current_flow": "free_chat"}, None, None, "sess-legacy")

    monkeypatch.setattr("backend.api.ai_assistant_api._enrich_with_trader_profile", fake_enrich_with_trader_profile)
    monkeypatch.setattr("backend.api.ai_assistant_api._apply_assistant_rate_limit", lambda **kwargs: None)
    monkeypatch.setattr("backend.api.ai_assistant_api._record_finn_product_event", lambda **kwargs: {})

    service = SimpleNamespace(
        get_chat_response=AsyncMock(side_effect=fake_get_chat_response),
        _classify_intent=lambda query: "general_help",
    )
    raw_request = Request({"type": "http", "headers": [], "client": ("127.0.0.1", 12345)})

    response = asyncio.run(
        assistant_chat(
            AssistantChatRequest(query="vrije vraag", history=[], context={"page": "/dashboard"}, session_id="sess-legacy"),
            raw_request,
            None,
            {"id": 30},
            service,
            None,
        )
    )

    assert captured["context"]["trader_profile_used"] is True
    assert captured["context"]["trader_profile"]["behavior_flags"] == ["fomo"]
    assert response.session_id == "sess-legacy"


def test_assistant_chat_returns_legacy_response_text_after_profile_overlay(monkeypatch):
    async def fake_enrich_with_trader_profile(db, user_id, payload=None, *, query=None):
        enriched = dict(payload or {})
        enriched.update({
            "page": "/assistant",
            "symbol": "BTC",
            "trader_profile_used": True,
            "trader_profile_summary": "swing_trader | 4h | behavior:fomo",
            "trader_profile": {"behavior_flags": ["fomo"]},
        })
        return enriched

    async def fake_get_chat_response(user_id, query, history, context, trace_id=None, session_id=None):
        return (
            "Ik help je hier vooral met uitleg, coaching en review in assistant rond BTC.\n\n"
            "Voor jouw profiel geldt nu: wacht bij BTC eerst op bevestiging en laat haast of fear of missing out je timing niet overnemen.",
            None,
            None,
            {"current_flow": "free_chat"},
            None,
            None,
            "sess-legacy",
        )

    monkeypatch.setattr("backend.api.ai_assistant_api._enrich_with_trader_profile", fake_enrich_with_trader_profile)
    monkeypatch.setattr("backend.api.ai_assistant_api._apply_assistant_rate_limit", lambda **kwargs: None)
    monkeypatch.setattr("backend.api.ai_assistant_api._record_finn_product_event", lambda **kwargs: {})

    service = SimpleNamespace(
        get_chat_response=AsyncMock(side_effect=fake_get_chat_response),
        _classify_intent=lambda query: "general_help",
    )
    raw_request = Request({"type": "http", "headers": [], "client": ("127.0.0.1", 12345)})

    response = asyncio.run(
        assistant_chat(
            AssistantChatRequest(query="legacy check", history=[], context={"page": "/assistant"}, session_id="sess-legacy"),
            raw_request,
            None,
            {"id": 30},
            service,
            None,
        )
    )

    assert "fear of missing out" in response.response


def test_legacy_response_is_generic_failure_detects_default_failures():
    assert _legacy_response_is_generic_failure("⚠️ Kon geen analyse ophalen. Probeer opnieuw.")
    assert _legacy_response_is_generic_failure("Interne authenticatiefout")
    assert _legacy_response_is_generic_failure("insufficient_quota")
    assert _legacy_response_is_generic_failure("AI quota bereikt")
    assert _legacy_response_is_generic_failure("")


def test_legacy_response_needs_finn_rescue_for_generic_failure_without_action_or_draft():
    finn = _finn()

    needs_rescue = _legacy_response_needs_finn_rescue(
        finn,
        "Wat is RSI in simpele taal?",
        {"page": "/dashboard", "symbol": "BTC"},
        response_text="⚠️ Kon geen analyse ophalen. Probeer opnieuw.",
        action=None,
        draft=None,
        state={"current_flow": "education"},
    )

    assert needs_rescue is True


def test_legacy_response_needs_finn_rescue_for_non_transactional_prompt_stuck_in_bot_creation():
    finn = _finn()

    needs_rescue = _legacy_response_needs_finn_rescue(
        finn,
        "Welke strategie bekijk ik nu?",
        {"page": "/strategy", "strategy_id": 257},
        response_text="Ik help je met je bot.",
        action=None,
        draft=None,
        state={"current_flow": "bot_creation"},
    )

    assert needs_rescue is True


def test_legacy_response_does_not_rescue_real_transactional_request():
    finn = _finn()

    needs_rescue = _legacy_response_needs_finn_rescue(
        finn,
        "Maak een bot voor mijn BTC setup",
        {"page": "/bot", "symbol": "BTC"},
        response_text="Ik ga je helpen een bot te maken.",
        action=None,
        draft=None,
        state={"current_flow": "bot_creation"},
    )

    assert needs_rescue is False


def test_build_finn_core_rescue_envelope_prefers_education_builder():
    finn = _finn()
    finn.build_education_response = AsyncMock(return_value={"intent": "education", "flow": "education"})

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Wat is RSI in simpele taal?",
            context_payload={"page": "/dashboard", "symbol": "BTC"},
        )
    )

    finn.build_education_response.assert_awaited_once()
    assert response["intent"] == "education"


def test_build_finn_core_rescue_envelope_prefers_context_explain_builder():
    finn = _finn()
    finn.build_context_explain_response = AsyncMock(return_value={"intent": "context_explain", "flow": "context_explain"})

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Leg mijn setup uit",
            context_payload={"page": "/setup", "setup_id": 62, "symbol": "BTC"},
        )
    )

    finn.build_context_explain_response.assert_awaited_once()
    assert response["intent"] == "context_explain"


def test_build_finn_core_rescue_envelope_does_not_route_cross_workspace_review_to_context_explain():
    finn = _finn()
    finn.build_context_explain_response = AsyncMock(return_value={"intent": "context_explain", "flow": "context_explain"})

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query=(
                "Bekijk mijn BTC-profiel, indicatoren, setup, strategie en gekoppelde bot. "
                "Wat is volgens jou op dit moment het belangrijkste ontbrekende onderdeel van mijn plan? "
                "Geef een concrete observatie en een vervolgstap."
            ),
            context_payload={"page": "/report", "page_type": "Reports", "symbol": "BTC", "setup_id": 262},
        )
    )

    finn.build_context_explain_response.assert_not_awaited()
    assert response["intent"] != "context_explain"
    assert response["flow"] != "context_explain"


@pytest.mark.parametrize(
    ("case_id", "query", "expected_builder", "expected_flow", "expected_family"),
    PRODUCTION_FINN_QUESTION_CONTRACTS,
)
def test_build_finn_core_rescue_envelope_routes_exact_production_questions(case_id, query, expected_builder, expected_flow, expected_family):
    finn = _finn()
    finn.issue_response_actions = AsyncMock()
    finn.persist_response_state = AsyncMock()

    builder_names = [
        "build_portfolio_intelligence_response",
        "build_decision_review_response",
        "build_indicator_insight_response",
        "build_context_explain_response",
    ]
    for builder_name in builder_names:
        setattr(
            finn,
            builder_name,
            AsyncMock(return_value={"intent": expected_flow, "flow": expected_flow, "response": case_id, "state": {"current_flow": expected_flow}}),
        )

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query=query,
            context_payload={"page": "/bot", "page_type": "Bot", "symbol": "BTC", "setup_id": 501, "strategy_id": 701, "bot_id": 901},
        )
    )

    for builder_name in builder_names:
        mock = getattr(finn, builder_name)
        if builder_name == expected_builder:
            mock.assert_awaited_once()
        else:
            mock.assert_not_awaited()

    envelope = asyncio.run(
        _prepare_finn_envelope(
            finn,
            30,
            response,
            f"trace-{case_id}",
            prompt=query,
            context_payload={"page": "/bot", "page_type": "Bot", "symbol": "BTC", "setup_id": 501, "strategy_id": 701, "bot_id": 901},
        )
    )

    assert envelope["flow"] == expected_flow
    assert envelope["response_trace"]["response"]["handler"].endswith(expected_builder)
    assert envelope["response_trace"]["routing"]["intent_family"] == expected_family


@pytest.mark.parametrize(
    ("case_id", "query", "expected_builder", "expected_flow", "expected_family"),
    PRODUCTION_FINN_QUESTION_CONTRACTS,
)
def test_canonical_chat_and_stream_endpoints_keep_production_question_contracts(
    monkeypatch,
    case_id,
    query,
    expected_builder,
    expected_flow,
    expected_family,
):
    finn, service, raw_stream_request = _patch_canonical_endpoint_runtime(
        monkeypatch,
        case_id=case_id,
        expected_builder=expected_builder,
        expected_flow=expected_flow,
    )

    chat_response = asyncio.run(
        assistant_chat(
            AssistantChatRequest(query=query, history=[], context={"page": "/bot"}, session_id=f"sess-{case_id}"),
            _raw_request(),
            None,
            {"id": 30},
            service,
            None,
        )
    )

    stream_response = asyncio.run(
        assistant_chat_stream(
            AssistantChatRequest(query=query, history=[], context={"page": "/bot"}, session_id=f"sess-{case_id}"),
            BackgroundTasks(),
            raw_stream_request,
            None,
            {"id": 30},
            service,
            None,
        )
    )
    stream_envelope = asyncio.run(_collect_stream_envelope(stream_response))

    for builder_name in [
        "build_portfolio_intelligence_response",
        "build_decision_review_response",
        "build_indicator_insight_response",
        "build_context_explain_response",
    ]:
        mock = getattr(finn, builder_name)
        if builder_name == expected_builder:
            assert mock.await_count == 2
        else:
            mock.assert_not_awaited()

    chat_trace = chat_response.response_trace
    stream_trace = stream_envelope["response_trace"]

    assert chat_response.flow == expected_flow
    assert stream_envelope["flow"] == expected_flow
    assert chat_trace["routing"]["pipeline_version"] == "v1_canonical_router"
    assert stream_trace["routing"]["pipeline_version"] == "v1_canonical_router"
    assert chat_trace["routing"]["intent_family"] == expected_family
    assert stream_trace["routing"]["intent_family"] == expected_family
    assert chat_trace["routing"]["selected_handler"].endswith(expected_builder)
    assert stream_trace["routing"]["selected_handler"].endswith(expected_builder)
    assert chat_trace["context"]["setup_id"] == 501
    assert chat_trace["context"]["strategy_id"] == 701
    assert chat_trace["context"]["bot_id"] == 901
    assert chat_trace["context"]["entity_confidence"]["bot"] == "high"
    assert chat_trace["context"]["missing_context"] == []
    assert stream_trace["context"]["setup_id"] == 501
    assert stream_trace["context"]["strategy_id"] == 701
    assert stream_trace["context"]["bot_id"] == 901
    assert stream_trace["decision"]["ai_available"] is True
    assert stream_trace["decision"]["legacy_used"] is False
    assert chat_response.response == f"{case_id} response"
    assert isinstance(chat_response.response, str) and chat_response.response
    assert isinstance(stream_envelope["response"], str) and stream_envelope["response"]


def test_build_finn_core_rescue_envelope_prefers_product_help_builder():
    finn = _finn()
    finn.build_product_help_response = AsyncMock(return_value={"intent": "product_help", "flow": "product_help"})

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Wat kan ik hier doen?",
            context_payload={"page": "/dashboard", "page_type": "Dashboard", "symbol": "BTC"},
        )
    )

    finn.build_product_help_response.assert_awaited_once()
    assert response["intent"] == "product_help"


def test_build_finn_core_rescue_envelope_prefers_product_refresh_help_builder():
    finn = _finn()
    finn.build_product_refresh_help_response = AsyncMock(return_value={"intent": "product_help", "flow": "product_help"})

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Waarom zijn mijn scores oud?",
            context_payload={"page": "/dashboard", "page_type": "Dashboard", "symbol": "BTC"},
        )
    )

    finn.build_product_refresh_help_response.assert_awaited_once()
    assert response["intent"] == "product_help"


def test_build_finn_core_rescue_envelope_prefers_behavioral_builder():
    finn = _finn()
    finn.build_behavioral_intelligence_response = AsyncMock(
        return_value={"intent": "behavioral_intelligence", "flow": "behavioral_intelligence"}
    )

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Ik voel FOMO, wat moet ik doen?",
            context_payload={"page": "/dashboard", "symbol": "BTC"},
        )
    )

    finn.build_behavioral_intelligence_response.assert_awaited_once()
    assert response["intent"] == "behavioral_intelligence"


def test_build_finn_core_rescue_envelope_prefers_decision_review_builder():
    finn = _finn()
    finn.build_decision_review_response = AsyncMock(return_value={"intent": "decision_review", "flow": "decision_review"})

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Beoordeel deze trade",
            context_payload={"page": "/setup", "setup_id": 62, "strategy_id": 257, "symbol": "BTC"},
        )
    )

    finn.build_decision_review_response.assert_awaited_once()
    assert response["intent"] == "decision_review"


def test_build_finn_core_rescue_envelope_prefers_decision_review_for_natural_trade_prompt():
    finn = _finn()
    finn.build_decision_review_response = AsyncMock(return_value={"intent": "decision_review", "flow": "decision_review"})

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Zou jij dit doen?",
            context_payload={"page": "/setup", "page_type": "setup", "setup_id": 62, "strategy_id": 257, "symbol": "BTC"},
        )
    )

    finn.build_decision_review_response.assert_awaited_once()
    assert response["intent"] == "decision_review"


def test_build_finn_core_rescue_envelope_prefers_decision_review_for_trade_opinion_prompt():
    finn = _finn()
    finn.build_decision_review_response = AsyncMock(return_value={"intent": "decision_review", "flow": "decision_review"})

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Wat vind je van deze trade?",
            context_payload={"page": "/dashboard", "page_type": "dashboard", "symbol": "BTC"},
        )
    )

    finn.build_decision_review_response.assert_awaited_once()
    assert response["intent"] == "decision_review"


def test_build_finn_core_rescue_envelope_prefers_plan_adherence_review_builder():
    finn = _finn()
    finn.build_plan_adherence_review_response = AsyncMock(
        return_value={"intent": "plan_adherence_review", "flow": "plan_adherence_review"}
    )

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Wijk ik af van mijn plan?",
            context_payload={"page": "/strategy", "strategy_id": 257, "symbol": "BTC"},
        )
    )

    finn.build_plan_adherence_review_response.assert_awaited_once()
    assert response["intent"] == "plan_adherence_review"


def test_build_finn_core_rescue_envelope_prefers_plan_adherence_for_stop_loss_removal():
    finn = _finn()
    finn.build_plan_adherence_review_response = AsyncMock(
        return_value={"intent": "plan_adherence_review", "flow": "plan_adherence_review"}
    )

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Ik wil mijn stop-loss verwijderen",
            context_payload={"page": "/strategy", "strategy_id": 257, "symbol": "BTC"},
        )
    )

    finn.build_plan_adherence_review_response.assert_awaited_once()
    assert response["intent"] == "plan_adherence_review"


def test_build_finn_core_rescue_envelope_prefers_governed_action_review_builder():
    finn = _finn()
    finn.build_governed_action_review_response = AsyncMock(
        return_value={"intent": "governed_action_review", "flow": "governed_action_review"}
    )

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Mag FINN deze strategie activeren?",
            context_payload={"page": "/strategy", "strategy_id": 257, "symbol": "BTC"},
        )
    )

    finn.build_governed_action_review_response.assert_awaited_once()
    assert response["intent"] == "governed_action_review"


def test_build_finn_core_rescue_envelope_prefers_governed_action_review_for_trade_permission():
    finn = _finn()
    finn.build_governed_action_review_response = AsyncMock(
        return_value={"intent": "governed_action_review", "flow": "governed_action_review"}
    )

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Ik wil deze BTC trade openen, mag dat?",
            context_payload={"page": "/market/BTC", "symbol": "BTC"},
        )
    )

    finn.build_governed_action_review_response.assert_awaited_once()
    assert response["intent"] == "governed_action_review"


def test_build_finn_core_rescue_envelope_prefers_governed_action_review_for_auditability_prompt():
    finn = _finn()
    finn.build_governed_action_review_response = AsyncMock(
        return_value={"intent": "governed_action_review", "flow": "governed_action_review"}
    )

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Wat wordt hiervan gelogd?",
            context_payload={},
        )
    )

    finn.build_governed_action_review_response.assert_awaited_once()
    assert response["intent"] == "governed_action_review"


def test_build_finn_core_rescue_envelope_prefers_governed_action_review_for_prepare_trade_prompt():
    finn = _finn()
    finn.build_governed_action_review_response = AsyncMock(
        return_value={"intent": "governed_action_review", "flow": "governed_action_review"}
    )

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Bereid deze trade voor, maar voer hem nog niet uit.",
            context_payload={"symbol": "BTC"},
        )
    )

    finn.build_governed_action_review_response.assert_awaited_once()
    assert response["intent"] == "governed_action_review"


def test_build_finn_core_rescue_envelope_prefers_outcome_tracking_builder():
    finn = _finn()
    finn.build_outcome_tracking_response = AsyncMock(
        return_value={"intent": "outcome_tracking", "flow": "outcome_tracking"}
    )

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Wat leert Finn van mijn uitkomsten?",
            context_payload={"page": "/dashboard", "symbol": "BTC"},
        )
    )

    finn.build_outcome_tracking_response.assert_awaited_once()
    assert response["intent"] == "outcome_tracking"


def test_build_finn_core_rescue_envelope_prefers_outcome_tracking_for_explicit_fomo_history():
    finn = _finn()
    finn.build_outcome_tracking_response = AsyncMock(
        return_value={"intent": "outcome_tracking", "flow": "outcome_tracking"}
    )

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="De laatste 8 FOMO trades: 6 verlies, 2 winst. Wat zegt dat?",
            context_payload={"page": "/dashboard", "symbol": "BTC"},
        )
    )

    finn.build_outcome_tracking_response.assert_awaited_once()
    assert response["intent"] == "outcome_tracking"


def test_build_finn_core_rescue_envelope_prefers_outcome_memory_builder():
    finn = FinnPlanService(db_session=object())
    finn.build_outcome_memory_response = AsyncMock(
        return_value={"intent": "outcome_memory", "flow": "outcome_memory"}
    )

    response = asyncio.run(_build_finn_core_rescue_envelope(
        finn=finn,
        user_id=30,
        query="Wat onthoudt Finn van mijn uitkomsten?",
        context_payload={},
    ))

    finn.build_outcome_memory_response.assert_awaited_once()
    assert response["intent"] == "outcome_memory"


def test_build_finn_core_rescue_envelope_prefers_personal_performance_builder():
    finn = FinnPlanService(db_session=object())
    finn.build_personal_performance_response = AsyncMock(
        return_value={"intent": "personal_performance", "flow": "personal_performance"}
    )

    response = asyncio.run(_build_finn_core_rescue_envelope(
        finn=finn,
        user_id=30,
        query="Geef mijn performance score",
        context_payload={},
    ))

    finn.build_personal_performance_response.assert_awaited_once()
    assert response["intent"] == "personal_performance"


def test_build_finn_core_rescue_envelope_prefers_trade_journal_intelligence_builder():
    finn = FinnPlanService(db_session=object())
    finn.build_trade_journal_intelligence_response = AsyncMock(
        return_value={"intent": "trade_journal_intelligence", "flow": "trade_journal_intelligence"}
    )

    response = asyncio.run(_build_finn_core_rescue_envelope(
        finn=finn,
        user_id=30,
        query="Wat leert mijn trade journal?",
        context_payload={},
    ))

    finn.build_trade_journal_intelligence_response.assert_awaited_once()
    assert response["intent"] == "trade_journal_intelligence"


def test_build_finn_core_rescue_envelope_prefers_personal_coach_builder():
    finn = FinnPlanService(db_session=object())
    finn.build_personal_coach_response = AsyncMock(
        return_value={"intent": "personal_coach", "flow": "personal_coach"}
    )

    response = asyncio.run(_build_finn_core_rescue_envelope(
        finn=finn,
        user_id=30,
        query="Coach me op basis van mijn laatste fouten",
        context_payload={},
    ))

    finn.build_personal_coach_response.assert_awaited_once()
    assert response["intent"] == "personal_coach"


def test_build_finn_core_rescue_envelope_prefers_behavioral_intelligence_for_overtrading():
    finn = FinnPlanService(db_session=object())
    finn.build_behavioral_intelligence_response = AsyncMock(
        return_value={"intent": "behavioral_intelligence", "flow": "behavioral_intelligence"}
    )

    response = asyncio.run(_build_finn_core_rescue_envelope(
        finn=finn,
        user_id=30,
        query="Overtrade ik?",
        context_payload={},
    ))

    finn.build_behavioral_intelligence_response.assert_awaited_once()
    assert response["intent"] == "behavioral_intelligence"


def test_build_finn_core_rescue_envelope_prefers_personal_coach_for_growth_direction_prompt():
    finn = FinnPlanService(db_session=object())
    finn.build_personal_coach_response = AsyncMock(
        return_value={"intent": "personal_coach", "flow": "personal_coach"}
    )
    finn.build_personal_performance_response = AsyncMock(
        return_value={"intent": "personal_performance", "flow": "personal_performance"}
    )

    response = asyncio.run(_build_finn_core_rescue_envelope(
        finn=finn,
        user_id=30,
        query="Word ik beter of slechter als trader?",
        context_payload={},
    ))

    finn.build_personal_coach_response.assert_awaited_once()
    finn.build_personal_performance_response.assert_not_awaited()
    assert response["intent"] == "personal_coach"


def test_build_finn_core_rescue_envelope_prefers_portfolio_intelligence_builder():
    finn = _finn()
    finn.build_portfolio_intelligence_response = AsyncMock(
        return_value={"intent": "portfolio_intelligence", "flow": "portfolio_intelligence"}
    )

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Heb ik te veel exposure?",
            context_payload={"page": "/dashboard", "symbol": "BTC"},
        )
    )

    finn.build_portfolio_intelligence_response.assert_awaited_once()
    assert response["intent"] == "portfolio_intelligence"


def test_build_finn_core_rescue_envelope_prefers_portfolio_intelligence_for_explicit_mix():
    finn = _finn()
    finn.build_portfolio_intelligence_response = AsyncMock(
        return_value={"intent": "portfolio_intelligence", "flow": "portfolio_intelligence"}
    )

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Ik heb 70% BTC / 20% ETH / 10% cash, kan ik nog een BTC long openen?",
            context_payload={"page": "/dashboard", "symbol": "BTC"},
        )
    )

    finn.build_portfolio_intelligence_response.assert_awaited_once()
    assert response["intent"] == "portfolio_intelligence"


def test_build_finn_core_rescue_envelope_prefers_governance_for_extra_btc_risk_prompt():
    finn = _finn()
    finn.build_governed_action_review_response = AsyncMock(
        return_value={"intent": "governed_action_review", "flow": "governed_action_review"}
    )

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Mag ik extra BTC risico toevoegen?",
            context_payload={"page": "/dashboard", "symbol": "BTC"},
        )
    )

    finn.build_governed_action_review_response.assert_awaited_once()
    assert response["intent"] == "governed_action_review"


def test_build_finn_core_rescue_envelope_prefers_priority_engine_builder():
    finn = _finn()
    finn.build_priority_engine_response = AsyncMock(
        return_value={"intent": "priority_engine", "flow": "priority_engine"}
    )

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Wat is vandaag mijn hoogste prioriteit?",
            context_payload={"page": "mission_control", "scope": "mission_control"},
        )
    )

    finn.build_priority_engine_response.assert_awaited_once()
    assert response["intent"] == "priority_engine"


def test_build_finn_core_rescue_envelope_prefers_priority_engine_for_generic_what_now_prompt():
    finn = _finn()
    finn.build_priority_engine_response = AsyncMock(
        return_value={"intent": "priority_engine", "flow": "priority_engine"}
    )

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Wat moet ik nu eerst doen?",
            context_payload={"page": "/dashboard", "symbol": "BTC"},
        )
    )

    finn.build_priority_engine_response.assert_awaited_once()
    assert response["intent"] == "priority_engine"


def test_build_finn_core_rescue_envelope_prefers_priority_engine_for_focus_prompt():
    finn = _finn()
    finn.build_priority_engine_response = AsyncMock(
        return_value={"intent": "priority_engine", "flow": "priority_engine"}
    )

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Waar moet ik vandaag op focussen?",
            context_payload={"page": "/dashboard", "symbol": "BTC"},
        )
    )

    finn.build_priority_engine_response.assert_awaited_once()
    assert response["intent"] == "priority_engine"


def test_build_finn_core_rescue_envelope_prefers_priority_engine_for_top3_prompt():
    finn = _finn()
    finn.build_priority_engine_response = AsyncMock(
        return_value={"intent": "priority_engine", "flow": "priority_engine"}
    )

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Wat zijn vandaag mijn 3 belangrijkste acties?",
            context_payload={"page": "/dashboard", "symbol": "BTC"},
        )
    )

    finn.build_priority_engine_response.assert_awaited_once()
    assert response["intent"] == "priority_engine"


def test_build_finn_core_rescue_envelope_prefers_priority_engine_for_what_not_to_do_prompt():
    finn = _finn()
    finn.build_priority_engine_response = AsyncMock(
        return_value={"intent": "priority_engine", "flow": "priority_engine"}
    )

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Wat moet ik juist niet doen?",
            context_payload={"page": "/dashboard", "symbol": "BTC"},
        )
    )

    finn.build_priority_engine_response.assert_awaited_once()
    assert response["intent"] == "priority_engine"


def test_build_finn_core_rescue_envelope_prefers_portfolio_operating_system_builder():
    finn = _finn()
    finn.build_portfolio_operating_system_response = AsyncMock(
        return_value={"intent": "portfolio_operating_system", "flow": "portfolio_operating_system"}
    )

    response = asyncio.run(
        _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=30,
            query="Geef mijn portfolio operating system",
            context_payload={"page": "mission_control"},
        )
    )

    finn.build_portfolio_operating_system_response.assert_awaited_once()
    assert response["intent"] == "portfolio_operating_system"


def test_finalize_finn_response_persists_read_only_state_by_default():
    finn = _finn()
    finn.issue_response_actions = AsyncMock()
    finn.persist_response_state = AsyncMock()

    response = asyncio.run(
        _finalize_finn_response(
            finn,
            30,
            {"intent": "context_explain", "flow": "context_explain", "response": "ok", "state": {"current_flow": "context_explain"}},
            "trace-1",
            prompt="Welke strategie bekijk ik nu?",
            context_payload={"page": "/dashboard", "page_type": "Dashboard", "symbol": "BTC"},
        )
    )

    finn.persist_response_state.assert_awaited_once()
    assert response.intent == "context_explain"
    assert response.response_trace["trace_id"] == "trace-1"
    assert response.response_trace["context"]["asset"] == "BTC"
    assert response.response_trace["response"]["handler"] == "finn_plan_service.build_context_explain_response"


def test_prepare_finn_envelope_persists_read_only_state_by_default():
    finn = _finn()
    finn.issue_response_actions = AsyncMock()
    finn.persist_response_state = AsyncMock()

    envelope = asyncio.run(
        _prepare_finn_envelope(
            finn,
            30,
            {"intent": "behavioral_intelligence", "flow": "behavioral_intelligence", "response": "ok", "state": {"current_flow": "behavioral_intelligence"}},
            "trace-2",
            prompt="Ik voel FOMO, wat moet ik doen?",
            context_payload={},
        )
    )

    finn.persist_response_state.assert_awaited_once()
    assert envelope["intent"] == "behavioral_intelligence"
    assert envelope["response_trace"]["trace_id"] == "trace-2"
    assert set(envelope["response_trace"]) == {
        "schema_version",
        "trace_id",
        "recorded_at",
        "routing",
        "context",
        "data",
        "memory",
        "specialist",
        "decision",
        "fallback",
        "response",
    }


def test_get_finn_mission_control_survives_non_database_action_failures(monkeypatch):
    db = SimpleNamespace(rollback=AsyncMock())
    stored = {}
    finn = SimpleNamespace(
        build_mission_control_response=AsyncMock(
            return_value={"first_dashboard_context": {"generation_status": "ready"}}
        ),
        issue_response_actions=AsyncMock(side_effect=RuntimeError("issue actions failed")),
    )

    monkeypatch.setattr("backend.api.ai_assistant_api._get_cached_mission_control", lambda user_id: None)
    monkeypatch.setattr(
        "backend.api.ai_assistant_api._store_cached_mission_control",
        lambda user_id, payload: stored.update({"user_id": user_id, "payload": payload}),
    )
    monkeypatch.setattr("backend.api.ai_assistant_api._new_finn_plan_service", lambda db_session, trace_id=None: finn)

    async def fake_enrich(db_session, user_id, payload=None, *, query=None):
        return payload or {}

    monkeypatch.setattr("backend.api.ai_assistant_api._enrich_with_trader_profile", fake_enrich)

    request = Request({"type": "http", "headers": [], "client": ("127.0.0.1", 12345)})
    request.state.trace_id = "trace-mission-control"

    response = asyncio.run(
        get_finn_mission_control(
            current_user={"id": 30},
            db=db,
            request=request,
        )
    )

    finn.build_mission_control_response.assert_awaited_once()
    finn.issue_response_actions.assert_awaited_once()
    db.rollback.assert_awaited_once()
    assert response["first_dashboard_context"]["generation_status"] == "ready"
    assert stored["user_id"] == 30
    assert stored["payload"]["first_dashboard_context"]["generation_status"] == "ready"


def test_get_finn_mission_control_returns_fallback_when_build_fails(monkeypatch):
    db = SimpleNamespace(rollback=AsyncMock())
    stored = {}
    finn = SimpleNamespace(
        trace_id="trace-mission-control-fallback",
        build_mission_control_response=AsyncMock(side_effect=RuntimeError("live mission control exploded")),
        issue_response_actions=AsyncMock(return_value={}),
        _first_dashboard_error_context=lambda analysis, *, error: {
            "is_first_dashboard": True,
            "asset": "BTC",
            "headline": "FINN is reviewing your plan",
            "observation": "Mission Control stays available while the first dashboard review retries safely.",
            "reasoning": "A recoverable mission-control build failure occurred.",
            "next_action": {"label": "Continue in Mission Control", "question": "Would you like to continue?"},
            "review_state": "not_reviewed_yet",
            "review_label": "Not reviewed yet",
            "response_source": "briefing_error",
            "generation_status": "error",
            "evidence_refs": ["asset.symbol"],
            "error": error,
        },
        _mission_workqueue_from_first_dashboard_context=lambda context: {
            "id": "first_dashboard:BTC",
            "type": "first_dashboard_review",
            "priority": "medium",
            "priority_rank": 4,
            "sort_rank": 4,
            "status": "not_reviewed_yet",
            "resolve_state": "not_reviewed_yet",
            "asset": "BTC",
            "title": "Continue in Mission Control",
            "reason": context["observation"],
            "next_best_action": {
                "type": "chat_prompt",
                "label": "Continue in Mission Control",
                "prompt": "Would you like to continue?",
                "handoff": "daily_coach",
                "requires_confirmation": False,
            },
            "resolve_action": None,
            "freshness": {"status": "unknown"},
            "source_ids": {"asset": "BTC"},
        },
        _mission_workqueue_groups=lambda items: {"review_now": items},
        _flatten_mission_workqueue_groups=lambda groups: list(groups.get("review_now") or []),
    )

    monkeypatch.setattr("backend.api.ai_assistant_api._get_cached_mission_control", lambda user_id: None)
    monkeypatch.setattr(
        "backend.api.ai_assistant_api._store_cached_mission_control",
        lambda user_id, payload: stored.update({"user_id": user_id, "payload": payload}),
    )
    monkeypatch.setattr("backend.api.ai_assistant_api._new_finn_plan_service", lambda db_session, trace_id=None: finn)

    async def fake_enrich(db_session, user_id, payload=None, *, query=None):
        enriched = dict(payload or {})
        enriched["trader_profile_used"] = True
        return enriched

    monkeypatch.setattr("backend.api.ai_assistant_api._enrich_with_trader_profile", fake_enrich)

    request = Request({"type": "http", "headers": [], "client": ("127.0.0.1", 12345)})
    request.state.trace_id = "trace-mission-control-fallback"

    response = asyncio.run(
        get_finn_mission_control(
            current_user={"id": 30},
            db=db,
            request=request,
        )
    )

    finn.build_mission_control_response.assert_awaited_once()
    finn.issue_response_actions.assert_awaited_once()
    assert response["first_dashboard_context"]["generation_status"] == "error"
    assert response["first_dashboard_context"]["response_source"] == "briefing_error"
    assert response["summary"]["first_dashboard_response_source"] == "briefing_error"
    assert response["workqueue"][0]["type"] == "first_dashboard_review"
    assert response["trader_profile_used"] is True
    assert stored["user_id"] == 30
    assert stored["payload"]["first_dashboard_context"]["generation_status"] == "error"


def test_conversation_state_repository_serializes_date_values():
    class _Session:
        def __init__(self):
            self.execute = AsyncMock()
            self.commit = AsyncMock()

    session = _Session()
    repo = ConversationStateRepository(session)

    asyncio.run(
        repo.save_state(
            30,
            "context_explain",
            "BTC",
            {"analysis": {"report_date": date(2026, 5, 31)}},
        )
    )

    assert session.execute.await_count == 1
    payload = session.execute.await_args.args[1]
    assert '"report_date": "2026-05-31"' in payload["slots"]


def test_conversation_state_repository_serializes_decimal_values():
    class _Session:
        def __init__(self):
            self.execute = AsyncMock()
            self.commit = AsyncMock()

    session = _Session()
    repo = ConversationStateRepository(session)

    asyncio.run(
        repo.save_state(
            30,
            "context_explain",
            "BTC",
            {"analysis": {"score": Decimal("42.5")}},
        )
    )

    payload = session.execute.await_args.args[1]
    assert '"score": 42.5' in payload["slots"]
