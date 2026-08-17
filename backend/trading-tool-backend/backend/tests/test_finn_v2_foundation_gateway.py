from types import SimpleNamespace
import asyncio

import pytest
from fastapi import HTTPException

from backend.infrastructure.models import MarketData
from backend.schemas.finn_v2_schema import AgentRunRequest
from backend.services import finn_v2_gateway_service as gateway_module


class _FakeConversationRepo:
    def __init__(self, _session):
        self.rows = {}

    async def get_by_id_for_user(self, conversation_id, user_id):
        row = self.rows.get(conversation_id)
        if row and row.user_id == user_id:
            return row
        return None

    async def create(self, *, conversation_id, user_id, title=None):
        row = SimpleNamespace(id=conversation_id, user_id=user_id, title=title)
        self.rows[conversation_id] = row
        return row


class _FakeRunRepo:
    def __init__(self, _session):
        self.rows = {}

    async def get_by_idempotency_key_for_user(self, *, idempotency_key, user_id):
        row = self.rows.get((user_id, idempotency_key))
        return row

    async def get_by_id_for_user(self, *, run_id, user_id):
        for row in self.rows.values():
            if row.id == run_id and row.user_id == user_id:
                return row
        return None


class _FakeRunService:
    def __init__(self, _session):
        self.created = []

    async def create_run(self, payload):
        run = SimpleNamespace(**payload)
        self.created.append(run)
        return run


def test_gateway_autogenerates_conversation_and_redacts_hints(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 32)
    monkeypatch.setattr(gateway_module, "FinnV2ConversationRepository", _FakeConversationRepo)
    monkeypatch.setattr(gateway_module, "FinnV2RunRepository", _FakeRunRepo)
    monkeypatch.setattr(gateway_module, "FinnV2RunService", _FakeRunService)
    monkeypatch.setattr(gateway_module.run_rate_limiter, "check_rate_limit", lambda *args, **kwargs: None)

    service = gateway_module.FinnV2GatewayService(session=object())
    monkeypatch.setattr(service.flags, "resolve_mode", lambda _user_id: "shadow")
    monkeypatch.setattr(service.flags, "allows_transport", lambda _transport: True)
    monkeypatch.setattr(service.flags, "max_runs_per_minute", lambda: 20)

    run = asyncio.run(
        service.create_run(
            user_id=7,
            request=AgentRunRequest(
                message="BTC graag",
                workspace_hints={"asset": "BTC", "api_key": "secret"},
                client_context={"cookie_value": "bad"},
            ),
            request_path="/api/assistant/v2/runs",
            request_id="req-1",
            trace_id="trace-1",
            client_ip="127.0.0.1",
            user_agent="pytest",
        ),
    )

    assert run.conversation_id.startswith("finn-v2-conv-")
    assert run.idempotency_key.startswith("finn-v2-")
    assert run.workspace_hints_json["api_key"] == "[redacted]"
    assert run.client_context_json["cookie_value"] == "[redacted]"
    assert run.client_context_json["_client_ip_hash"] is not None
    assert run.client_context_json["_user_agent_hash"] is not None


def test_gateway_serializes_sqlalchemy_objects_in_hints(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 32)
    monkeypatch.setattr(gateway_module, "FinnV2ConversationRepository", _FakeConversationRepo)
    monkeypatch.setattr(gateway_module, "FinnV2RunRepository", _FakeRunRepo)
    monkeypatch.setattr(gateway_module, "FinnV2RunService", _FakeRunService)
    monkeypatch.setattr(gateway_module.run_rate_limiter, "check_rate_limit", lambda *args, **kwargs: None)

    service = gateway_module.FinnV2GatewayService(session=object())
    monkeypatch.setattr(service.flags, "resolve_mode", lambda _user_id: "visible_runtime")
    monkeypatch.setattr(service.flags, "allows_transport", lambda _transport: True)
    monkeypatch.setattr(service.flags, "max_runs_per_minute", lambda: 20)

    market_snapshot = MarketData(symbol="BTC", price=109234.12, change_24h=2.3, volume=123456.0)

    run = asyncio.run(
        service.create_run(
            user_id=7,
            request=AgentRunRequest(
                message="BTC graag",
                workspace_hints={"market_snapshot": market_snapshot},
                client_context={"market_snapshot": market_snapshot},
            ),
            request_path="/api/assistant/chat",
            request_id="req-json-safe",
            trace_id="trace-json-safe",
        ),
    )

    assert run.workspace_hints_json["market_snapshot"]["symbol"] == "BTC"
    assert run.workspace_hints_json["market_snapshot"]["price"] == 109234.12
    assert run.client_context_json["market_snapshot"]["change_24h"] == 2.3


def test_gateway_returns_existing_run_on_same_user_idempotency(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 32)
    monkeypatch.setattr(gateway_module, "FinnV2ConversationRepository", _FakeConversationRepo)
    monkeypatch.setattr(gateway_module, "FinnV2RunRepository", _FakeRunRepo)
    monkeypatch.setattr(gateway_module, "FinnV2RunService", _FakeRunService)
    monkeypatch.setattr(gateway_module.run_rate_limiter, "check_rate_limit", lambda *args, **kwargs: None)

    service = gateway_module.FinnV2GatewayService(session=object())
    monkeypatch.setattr(service.flags, "resolve_mode", lambda _user_id: "shadow")
    monkeypatch.setattr(service.flags, "allows_transport", lambda _transport: True)
    monkeypatch.setattr(service.flags, "max_runs_per_minute", lambda: 20)

    request = AgentRunRequest(message="zelfde", idempotency_key="abcdefgh")
    first = asyncio.run(service.create_run(user_id=7, request=request, request_path="/x", request_id="r1", trace_id="t1"))
    service.runs.rows[(7, "abcdefgh")] = first
    second = asyncio.run(service.create_run(user_id=7, request=request, request_path="/x", request_id="r1", trace_id="t1"))

    assert first is second


def test_gateway_owner_mismatch_returns_404(monkeypatch):
    monkeypatch.setattr(gateway_module, "FinnV2ConversationRepository", _FakeConversationRepo)
    monkeypatch.setattr(gateway_module, "FinnV2RunRepository", _FakeRunRepo)
    monkeypatch.setattr(gateway_module, "FinnV2RunService", _FakeRunService)
    monkeypatch.setattr(gateway_module.run_rate_limiter, "check_rate_limit", lambda *args, **kwargs: None)

    service = gateway_module.FinnV2GatewayService(session=object())
    monkeypatch.setattr(service.flags, "resolve_mode", lambda _user_id: "shadow")
    monkeypatch.setattr(service.flags, "allows_transport", lambda _transport: True)
    monkeypatch.setattr(service.flags, "max_runs_per_minute", lambda: 20)
    service.conversations.rows["conv-1"] = SimpleNamespace(id="conv-1", user_id=99)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            service.create_run(
                user_id=7,
                request=AgentRunRequest(message="x", conversation_id="conv-1"),
                request_path="/x",
                request_id="r2",
                trace_id="t2",
            )
        )

    assert exc.value.status_code == 404


def test_gateway_server_side_idempotency_key_is_stable():
    service = gateway_module.FinnV2GatewayService(session=object())

    first = service._resolve_idempotency_key(user_id=7, client_key=None, request_id="same-request")
    second = service._resolve_idempotency_key(user_id=7, client_key=None, request_id="same-request")
    third = service._resolve_idempotency_key(user_id=8, client_key=None, request_id="same-request")

    assert first == second
    assert first != third
