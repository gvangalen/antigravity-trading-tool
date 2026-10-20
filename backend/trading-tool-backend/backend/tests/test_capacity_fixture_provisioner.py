import json
import os
import stat
import asyncio
import runpy
from datetime import timedelta

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.scripts import provision_capacity_fixtures as fixtures
from backend.main import app
from backend.utils.auth_utils import CAPACITY_FIXTURE_ROUTES, create_token, decode_token, get_current_user


def test_fixture_collision_is_rejected_before_mutation():
    row = {
        "email": fixtures.fixture_email("capacity-check", 1),
        "role": "user",
        "first_name": "Capacity",
        "last_name": "Fixture",
        "ai_preferences": {"capacity_fixture": {
            "campaign": "another-run", "index": 1, "kind": fixtures.FIXTURE_KIND,
        }},
    }
    with pytest.raises(RuntimeError, match="collision"):
        fixtures.validate_fixture(row, "capacity-check", 1)


def test_token_file_is_private_outside_repo_and_cannot_be_replaced(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    output = directory / "fixtures.json"
    path = fixtures.private_output_path(output)
    fixtures.write_private_json(path, [{"user_id": 7, "access_token": "test-token"}])
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert json.loads(output.read_text()) == [{"user_id": 7, "access_token": "test-token"}]
    with pytest.raises(ValueError, match="already exists"):
        fixtures.private_output_path(output)
    with pytest.raises(FileExistsError):
        fixtures.write_private_json(path, [{"user_id": 8, "access_token": "replacement"}])
    assert json.loads(output.read_text())[0]["user_id"] == 7


def test_token_file_rejects_world_readable_directory_and_repo_path(tmp_path):
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    os.chmod(public, 0o755)
    with pytest.raises(ValueError, match="mode 0700"):
        fixtures.private_output_path(public / "fixtures.json")
    with pytest.raises(ValueError, match="outside the repository"):
        fixtures.private_output_path(fixtures.REPO_ROOT / "fixtures.json")


def test_fixture_token_is_limited_to_load_get_routes():
    token = create_token({"sub": "42", "role": "user", "capacity_fixture": {
        "kind": fixtures.FIXTURE_KIND, "campaign": "capacity-check",
    }}, timedelta(minutes=20), "access")
    with pytest.raises(ValueError, match="not valid for this operation"):
        decode_token(token)

    def authenticate(method, path):
        request = Request({"type": "http", "method": method, "path": path,
                           "query_string": b"", "headers": []})
        return asyncio.run(get_current_user(request, access_token=None,
                                             authorization=f"Bearer {token}"))

    assert CAPACITY_FIXTURE_ROUTES == {
        "/api/auth/me", "/api/workspace/asset", "/api/assistant/v2/conversations", "/api/bot/trade-reviews",
    }
    for path in CAPACITY_FIXTURE_ROUTES:
        assert authenticate("GET", path) == {"id": 42, "role": "user"}
        with pytest.raises(HTTPException) as blocked:
            authenticate("POST", path)
        assert blocked.value.status_code == 403
    for path in ("/api/bot/orders", "/api/auth/refresh", "/api/bot/trade-reviews/7"):
        with pytest.raises(HTTPException) as blocked:
            authenticate("GET", path)
        assert blocked.value.status_code == 403


def test_capacity_load_routes_exist_and_match_token_scope():
    routes = runpy.run_path(str(fixtures.REPO_ROOT / "ops/load/active_users.py"))["ROUTES"]

    configured = {path.split("?", 1)[0] for _, method, path, _ in routes if method == "GET"}
    available = {route.path for route in app.routes if "GET" in getattr(route, "methods", ())}
    assert configured | {"/api/auth/me"} == CAPACITY_FIXTURE_ROUTES
    assert configured <= available


def test_capacity_fixture_email_is_accepted_by_auth_response_schema():
    from pydantic import EmailStr, parse_obj_as

    email = fixtures.fixture_email("capacity-check", 1)
    assert parse_obj_as(EmailStr, email) == email


def test_capacity_load_origin_rejects_unapproved_token_destinations():
    validate = runpy.run_path(str(fixtures.REPO_ROOT / "ops/load/active_users.py"))["validate_base_url"]
    assert validate("http://127.0.0.1:8000", allow_production=False) == "http://127.0.0.1:8000"
    assert validate("https://tradamind.com/", allow_production=True) == "https://tradamind.com"
    for url in ("http://tradamind.com", "https://api.tradamind.com",
                "https://tradamimd.com", "https://tradamind.com.evil.test",
                "https://tradamind.com@evil.test", "https://tradamind.com/path"):
        with pytest.raises(ValueError):
            validate(url, allow_production=True)
    with pytest.raises(ValueError):
        validate("https://tradamind.com", allow_production=False)


def test_capacity_load_identity_and_error_gate():
    from types import SimpleNamespace

    harness = runpy.run_path(str(fixtures.REPO_ROOT / "ops/load/active_users.py"))
    identity_matches = harness["identity_matches"]
    fixture = {"user_id": 42, "email": "capacity+test-0042@load.example"}
    response = SimpleNamespace(status_code=200, json=lambda: {"id": 42, "email": fixture["email"]})
    assert identity_matches(response, fixture)
    assert not identity_matches(SimpleNamespace(status_code=200, json=lambda: {
        "id": 43, "email": fixture["email"],
    }), fixture)
    assert not identity_matches(SimpleNamespace(status_code=200, json=lambda: {
        "id": 42, "email": "another-user@example.test",
    }), fixture)
    summary = harness["report"]("test", {"workspace": [(200, 100), (503, 250)]})
    assert summary["workspace"]["p95_ms"] == 100
    assert summary["workspace"]["p95_all_ms"] == 250
    assert harness["stage_has_blocking_errors"](summary)
    assert harness["stage_exceeds_latency_limit"](summary, {"workspace": 200}) == ["workspace"]
    assert harness["stage_exceeds_latency_limit"](summary, {"workspace": 300}) == []
    assert harness["stage_exceeds_latency_limit"]({}, {"workspace": 200}) == ["workspace"]


def test_capacity_load_operator_gate_requires_explicit_continue(monkeypatch):
    harness = runpy.run_path(str(fixtures.REPO_ROOT / "ops/load/active_users.py"))
    monkeypatch.setattr("builtins.input", lambda prompt: "no")
    with pytest.raises(RuntimeError, match="declined"):
        harness["require_operator_continue"]("500:120")
    monkeypatch.setattr("builtins.input", lambda prompt: "CONTINUE")
    harness["require_operator_continue"]("500:120")


def test_capacity_load_rejects_nonfinite_production_latency_gate(monkeypatch):
    import sys

    harness = runpy.run_path(str(fixtures.REPO_ROOT / "ops/load/active_users.py"))
    monkeypatch.setattr(sys, "argv", [
        "active_users.py", "--base-url", "https://tradamind.com",
        "--fixtures", "/missing-private-file", "--stages", "100:1",
        "--allow-production", "--max-workspace-p95-ms", "nan",
        "--max-finn-p95-ms", "1000", "--max-reviews-p95-ms", "1000",
    ])
    with pytest.raises(SystemExit) as rejected:
        harness["main"]()
    assert rejected.value.code == 2
