from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
from fastapi import Request
from sqlalchemy.dialects import postgresql

from backend.api import finn_v2_api
from backend.main import app


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows

    def scalar_one_or_none(self):
        return self.rows[0] if self.rows else None


def test_v2_history_is_owner_scoped_and_restores_only_visible_text():
    now = datetime.now(timezone.utc)
    conversation = SimpleNamespace(
        id="finn-v2-conv-owned", user_id=351, title="FINN Core V2 shadow conversation",
        updated_at=now,
    )
    runs = [
        SimpleNamespace(message="Welke setup heb ik?", response_json={"content": "Je BTC-setup."}),
        SimpleNamespace(message="Maak een voorstel", response_json={
            "content": "Dit is het voorstel.", "proposal_id": "old-proposal-secret",
        }),
    ]

    class _Db:
        async def execute(self, statement):
            sql = str(statement.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True},
            ))
            assert "user_id = 351" in sql
            if "FROM finn_v2_conversations" in sql:
                return _Rows([conversation] if "finn-v2-conv-other" not in sql else [])
            assert "visibility = 'visible'" in sql
            if "finn_v2_runs.message" in sql and "finn_v2_runs.id" not in sql:
                return _Rows([runs[0].message])
            return _Rows(runs)

    async def _current_user(request: Request):
        assert request.headers["authorization"] == "Bearer history-test"
        return {"id": 351, "role": "user"}

    async def _db():
        yield _Db()

    app.dependency_overrides[finn_v2_api.get_current_user] = _current_user
    app.dependency_overrides[finn_v2_api.get_db] = _db

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver",
        ) as client:
            headers = {"Authorization": "Bearer history-test"}
            listing = await client.get("/api/assistant/v2/conversations", headers=headers)
            detail = await client.get("/api/assistant/v2/conversations/finn-v2-conv-owned", headers=headers)
            foreign = await client.get("/api/assistant/v2/conversations/finn-v2-conv-other", headers=headers)
            return listing, detail, foreign

    try:
        listing, detail, foreign = asyncio.run(exercise())
    finally:
        app.dependency_overrides.clear()

    assert listing.status_code == 200
    assert listing.json()[0]["title"] == "Welke setup heb ik?"
    assert detail.status_code == 200
    assert detail.json()["messages"] == [
        {"role": "user", "content": "Welke setup heb ik?"},
        {"role": "assistant", "content": "Je BTC-setup."},
        {"role": "user", "content": "Maak een voorstel"},
        {"role": "assistant", "content": "Dit is het voorstel."},
    ]
    assert foreign.status_code == 404
