import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from starlette.requests import Request

from backend.api.ai_assistant_api import assistant_chat, _audit_context_summary, get_finn_mission_control, router
from backend.schemas.assistant_schema import AssistantChatRequest
from backend.infrastructure.repositories.conversation_state_repository import ConversationStateRepository


def test_finn_routes_retire_the_separate_insight_endpoint():
    paths = {route.path for route in router.routes}
    assert "/assistant/chat" in paths
    assert "/assistant/mission-control" in paths
    assert "/assistant/insight" not in paths

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

def test_assistant_chat_defers_profile_context_until_after_run_selection(monkeypatch):
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

    async def fake_try_v2_visible_delivery(**kwargs):
        captured["context"] = kwargs["context_payload"]
        return {
            "response": "V2 antwoord",
            "intent": "fact",
            "state": {"current_flow": "finn_v2_visible"},
            "response_trace": {"pipeline_version": "finn_v2"},
        }

    monkeypatch.setattr("backend.api.ai_assistant_api._enrich_with_trader_profile", fake_enrich_with_trader_profile)
    monkeypatch.setattr("backend.api.ai_assistant_api._apply_assistant_rate_limit", lambda **kwargs: None)
    monkeypatch.setattr("backend.api.ai_assistant_api._record_finn_product_event", lambda **kwargs: {})
    monkeypatch.setattr("backend.api.ai_assistant_api._try_v2_visible_delivery", fake_try_v2_visible_delivery)

    raw_request = Request({"type": "http", "headers": [], "client": ("127.0.0.1", 12345)})

    response = asyncio.run(
        assistant_chat(
            AssistantChatRequest(query="vrije vraag", history=[], context={"page": "/dashboard"}, session_id="sess-legacy"),
            raw_request,
            None,
            {"id": 30},
            None,
        )
    )

    assert captured["context"] == {"page": "/dashboard", "session_id": "sess-legacy"}
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

    async def fake_try_v2_visible_delivery(**kwargs):
        return {
            "response": (
                "Ik help je hier vooral met uitleg, coaching en review in assistant rond BTC.\n\n"
                "Voor jouw profiel geldt nu: wacht bij BTC eerst op bevestiging en laat haast of fear of missing out je timing niet overnemen."
            ),
            "intent": "evaluation",
            "state": {"current_flow": "finn_v2_visible"},
            "response_trace": {"pipeline_version": "finn_v2"},
        }

    monkeypatch.setattr("backend.api.ai_assistant_api._enrich_with_trader_profile", fake_enrich_with_trader_profile)
    monkeypatch.setattr("backend.api.ai_assistant_api._apply_assistant_rate_limit", lambda **kwargs: None)
    monkeypatch.setattr("backend.api.ai_assistant_api._record_finn_product_event", lambda **kwargs: {})
    monkeypatch.setattr("backend.api.ai_assistant_api._try_v2_visible_delivery", fake_try_v2_visible_delivery)

    raw_request = Request({"type": "http", "headers": [], "client": ("127.0.0.1", 12345)})

    response = asyncio.run(
        assistant_chat(
            AssistantChatRequest(query="legacy check", history=[], context={"page": "/assistant"}, session_id="sess-legacy"),
            raw_request,
            None,
            {"id": 30},
            None,
        )
    )

    assert "fear of missing out" in response.response

def test_get_finn_mission_control_survives_non_database_action_failures(monkeypatch):
    db = SimpleNamespace(rollback=AsyncMock())
    captured = {}

    class VisibleService:
        async def deliver_mission_control(self, **kwargs):
            captured.update(kwargs)
            return {
                "greeting": "Today with FINN",
                "finn_briefing": {"summary": "Ready", "suggested_actions": []},
                "generation_status": "completed",
                "response_trace": {"pipeline_version": "finn_v2"},
                "first_dashboard_context": {"generation_status": "ready"},
            }

    monkeypatch.setattr("backend.api.ai_assistant_api.FinnV2VisibleDeliveryService", lambda db_session: VisibleService())

    request = Request({"type": "http", "headers": [], "client": ("127.0.0.1", 12345)})
    request.state.trace_id = "trace-mission-control"

    response = asyncio.run(
        get_finn_mission_control(
            symbol="aapl",
            current_user={"id": 30},
            db=db,
            request=request,
        )
    )

    db.rollback.assert_not_awaited()
    assert response["first_dashboard_context"]["generation_status"] == "ready"
    assert captured["context_payload"]["symbol"] == "AAPL"

def test_get_finn_mission_control_returns_owner_scoped_fallback_after_enrichment_failure(monkeypatch):
    db = SimpleNamespace(rollback=AsyncMock())

    class VisibleService:
        async def deliver_mission_control(self, **kwargs):
            raise RuntimeError("live mission control exploded")

        async def deliver_mission_control_fallback(self, **kwargs):
            return {
                "finn_briefing": {
                    "summary": "Je hebt 2 opgeslagen setups: BTC Base, BTC Breakout.",
                    "suggested_actions": [],
                },
                "generation_status": "degraded",
                "response_trace": {
                    "pipeline_version": "finn_v2",
                    "response_source": "owner_scoped_deterministic_fallback",
                },
            }

    monkeypatch.setattr("backend.api.ai_assistant_api.FinnV2VisibleDeliveryService", lambda db_session: VisibleService())

    request = Request({"type": "http", "headers": [], "client": ("127.0.0.1", 12345)})
    request.state.trace_id = "trace-mission-control-fallback"

    response = asyncio.run(
        get_finn_mission_control(
            current_user={"id": 30},
            db=db,
            request=request,
        )
    )

    db.rollback.assert_not_awaited()
    assert response["generation_status"] == "degraded"
    assert response["response_trace"]["pipeline_version"] == "finn_v2"
    assert response["response_trace"]["response_source"] == "owner_scoped_deterministic_fallback"
    assert "BTC Base" in response["finn_briefing"]["summary"]

def test_get_finn_mission_control_bounds_enrichment_and_returns_owner_fallback(monkeypatch):
    db = SimpleNamespace(rollback=AsyncMock())

    class VisibleService:
        async def deliver_mission_control(self, **kwargs):
            return {"generation_status": "completed"}

        async def deliver_mission_control_fallback(self, **kwargs):
            return {"generation_status": "degraded", "finn_briefing": {"summary": "Persisted owner state"}}

    async def timeout_wait_for(awaitable, *, timeout):
        awaitable.close()
        assert timeout == 8.0
        raise asyncio.TimeoutError

    monkeypatch.setattr("backend.api.ai_assistant_api.FinnV2VisibleDeliveryService", lambda _db: VisibleService())
    monkeypatch.setattr("backend.api.ai_assistant_api.asyncio.wait_for", timeout_wait_for)
    request = Request({"type": "http", "headers": [], "client": ("127.0.0.1", 12345)})
    request.state.trace_id = "trace-timeout"

    response = asyncio.run(get_finn_mission_control(current_user={"id": 30}, db=db, request=request))

    assert response["generation_status"] == "degraded"
    assert response["finn_briefing"]["summary"] == "Persisted owner state"

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
