from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
from fastapi import Request

from backend.api import finn_v2_api
from backend.main import app
from backend.schemas.finn_v2_schema import AgentRunStatusEnvelope


def test_authenticated_run_creation_uses_the_injected_database_session_for_runtime_contract(monkeypatch):
    """Exercise POST through FastAPI so an undefined endpoint-local DB name regresses."""

    injected_db = object()
    captured = {"dispatches": 0, "repository_session": None}
    now = datetime.now(timezone.utc)
    run = SimpleNamespace(
        id="finn-v2-run-route-1",
        conversation_id="finn-v2-conversation-route-1",
        status="queued",
    )

    class _Gateway:
        async def run_foundation_now(self, **kwargs):
            assert kwargs["user_id"] == 351
            captured["dispatches"] += 1
            return run.id

        async def get_run(self, *, run_id, user_id):
            assert run_id == run.id
            assert user_id == 351
            return run

    class _RunService:
        async def envelope_from_run(self, observed_run):
            assert observed_run is run
            return AgentRunStatusEnvelope(
                run_id=run.id,
                conversation_id=run.conversation_id,
                status="queued",
                visibility="visible",
                created_at=now,
                updated_at=now,
            )

    class _RuntimeContracts:
        def __init__(self, session):
            captured["repository_session"] = session

        async def get_for_run(self, *, run_id):
            assert run_id == run.id
            return SimpleNamespace(
                contract_id="finn-v2-contract-route-1",
                contract_version="2026-09-04.runtime-contract.v1",
                revision=0,
            )

    async def _current_user(request: Request):
        assert request.headers["authorization"] == "Bearer qa-route-token"
        return {"id": 351, "role": "user"}

    async def _db():
        yield injected_db

    app.dependency_overrides[finn_v2_api.get_current_user] = _current_user
    app.dependency_overrides[finn_v2_api.get_db] = _db
    app.dependency_overrides[finn_v2_api.get_gateway_service] = lambda: _Gateway()
    app.dependency_overrides[finn_v2_api.get_run_service] = lambda: _RunService()
    monkeypatch.setattr(finn_v2_api, "FinnV2RuntimeContractRepository", _RuntimeContracts)

    async def exercise():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/api/assistant/v2/runs",
                headers={"Authorization": "Bearer qa-route-token"},
                json={"message": "Wat kun je voor mij doen?", "transport": "chat"},
            )

    try:
        response = asyncio.run(exercise())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == run.id
    assert payload["runtime_trace"]["contract"]["contract_id"] == "finn-v2-contract-route-1"
    assert payload["runtime_trace"]["contract"]["run_id"] == run.id
    assert captured["repository_session"] is injected_db
    assert captured["dispatches"] == 1
