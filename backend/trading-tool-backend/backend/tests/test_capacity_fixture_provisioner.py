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


def test_fixture_token_is_limited_to_three_get_routes():
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
        "/api/workspace/asset", "/api/assistant/v2/conversations", "/api/bot/trade-reviews",
    }
    for path in CAPACITY_FIXTURE_ROUTES:
        assert authenticate("GET", path) == {"id": 42, "role": "user"}
        with pytest.raises(HTTPException) as blocked:
            authenticate("POST", path)
        assert blocked.value.status_code == 403
    for path in ("/api/bot/orders", "/api/auth/me", "/api/bot/trade-reviews/7"):
        with pytest.raises(HTTPException) as blocked:
            authenticate("GET", path)
        assert blocked.value.status_code == 403


def test_capacity_load_routes_exist_and_match_token_scope():
    routes = runpy.run_path(str(fixtures.REPO_ROOT / "ops/load/active_users.py"))["ROUTES"]

    configured = {path.split("?", 1)[0] for _, method, path, _ in routes if method == "GET"}
    available = {route.path for route in app.routes if "GET" in getattr(route, "methods", ())}
    assert configured == CAPACITY_FIXTURE_ROUTES
    assert configured <= available
