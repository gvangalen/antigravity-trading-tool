import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request

from backend.utils import auth_utils


class _Result:
    def __init__(self, user):
        self.user = user

    def scalar_one_or_none(self):
        return self.user


class _Session:
    def __init__(self, user):
        self.user = user

    async def execute(self, _query):
        if "finn_v2_proposals" in str(_query):
            return _Result(self.user.proposal)
        return _Result(self.user)


def _request(method, path):
    return Request({"type": "http", "method": method, "path": path,
                    "query_string": b"", "headers": []})


def test_temporary_qa_bearer_restricts_routes_and_revokes_immediately(monkeypatch):
    namespace = "qa-123-1-aabbccdd-eeff0011"
    lease = "private-lease"
    user = SimpleNamespace(
        id=42, role="user", is_active=True,
        ai_preferences={"qa_fixture": auth_utils.FINN_TEMP_QA_KIND,
                        "finn_temp_qa": {"namespace": namespace, "lease": lease,
                                         "status": "active",
                                         "expires_at": (datetime.now(timezone.utc)
                                                        + timedelta(minutes=45)).isoformat()}},
    )
    user.proposal = SimpleNamespace(operation_type="create_manual_trade_plan")

    @asynccontextmanager
    async def session_factory():
        yield _Session(user)

    monkeypatch.setattr(auth_utils, "async_session_factory", session_factory, raising=False)
    # The validator imports the DB factory lazily; patch that module too.
    from backend.infrastructure import database
    monkeypatch.setattr(database, "async_session_factory", session_factory)
    token = auth_utils.create_token(
        {"sub": "42", "role": "user", "finn_temp_qa": {
            "kind": auth_utils.FINN_TEMP_QA_KIND, "namespace": namespace,
            "lease": lease}}, timedelta(minutes=40), "access")

    with pytest.raises(ValueError):
        auth_utils.decode_token(token)

    async def authenticate(method, path, *, cookie=None, bearer=token):
        return await auth_utils.get_current_user(
            _request(method, path), access_token=cookie,
            authorization=f"Bearer {bearer}")

    assert asyncio.run(authenticate("POST", "/api/assistant/v2/runs")) == {
        "id": 42, "role": "user"}
    assert asyncio.run(authenticate(
        "POST", "/api/assistant/v2/proposals/proposal-1/execute")) == {
            "id": 42, "role": "user"}
    user.proposal.operation_type = "create_bot"
    with pytest.raises(HTTPException) as blocked:
        asyncio.run(authenticate(
            "POST", "/api/assistant/v2/proposals/proposal-1/execute"))
    assert blocked.value.status_code == 403
    user.proposal.operation_type = "create_manual_trade_plan"
    for method, path in (("GET", "/api/bot/orders"),
                         ("POST", "/api/auth/refresh"),
                         ("DELETE", "/api/assistant/v2/proposals/proposal-1"),
                         ("GET", "/api/assistant/v2/proposals/../../auth/me")):
        with pytest.raises(HTTPException) as blocked:
            asyncio.run(authenticate(method, path))
        assert blocked.value.status_code == 403
    with pytest.raises(HTTPException) as blocked:
        asyncio.run(authenticate("POST", "/api/assistant/v2/runs",
                                 cookie=token, bearer="other-token"))
    assert blocked.value.status_code == 403

    user.is_active = False
    with pytest.raises(HTTPException) as blocked:
        asyncio.run(authenticate("GET", "/api/auth/me"))
    assert blocked.value.status_code == 401


def test_temporary_qa_issuer_uses_real_jwt_ttl_and_requires_private_scope(monkeypatch, capsys):
    from backend.scripts import qa_issue_finn_token as issuer
    from types import SimpleNamespace
    namespace = "qa-123-1-aabbccdd-eeff0011"
    user = SimpleNamespace(
        id=42, email="finn-qa@example.invalid", first_name="FINN QA",
        role="user", is_active=True,
        ai_preferences={"qa_fixture": auth_utils.FINN_TEMP_QA_KIND,
                        "finn_temp_qa": {"namespace": namespace, "lease": "private-lease",
                                         "status": "active",
                                         "expires_at": (datetime.now(timezone.utc)
                                                        + timedelta(minutes=45)).isoformat()}},
    )
    async def find_user(**_kwargs):
        return user
    monkeypatch.setattr(issuer, "_find_user", find_user)
    monkeypatch.setattr(issuer, "_parse_args", lambda: SimpleNamespace(
        user_id=42, email=None, minutes=40))
    monkeypatch.delenv("FINN_QA_TEMP_CHILD_RUN", raising=False)
    assert asyncio.run(issuer._run()) == 1
    assert "temporary_token_scope_missing" in capsys.readouterr().out
    monkeypatch.setenv("FINN_QA_TEMP_CHILD_RUN", "1")
    assert asyncio.run(issuer._run()) == 0
    import json
    payload = json.loads(capsys.readouterr().out)
    claims = auth_utils.decode_token(payload["access_token"], allow_finn_temp_qa=True)
    assert claims["exp"] - claims["iat"] == 40 * 60
    assert claims["finn_temp_qa"]["namespace"] == namespace
