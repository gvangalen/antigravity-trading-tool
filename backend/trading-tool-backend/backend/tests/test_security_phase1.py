import importlib
import os
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend" / "trading-tool-backend" / "backend"
FRONTEND_ROOT = REPO_ROOT / "frontend" / "trading-tool-frontend"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_jwt_secret_has_no_hardcoded_default():
    source = _read(BACKEND_ROOT / "utils" / "auth_utils.py")

    assert 'os.getenv("JWT_SECRET_KEY", ' not in source
    assert '_require_secret("JWT_SECRET_KEY")' in source
    assert 'SECRET_KEY = os.getenv("JWT_SECRET_KEY"' not in source


def test_jwt_secret_fails_hard_when_missing(monkeypatch):
    import backend.utils.auth_utils as auth_utils

    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        importlib.reload(auth_utils)

    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-key-for-platform-security-tests-123")
    importlib.reload(auth_utils)


def test_encryption_secret_fails_hard_when_missing_at_use():
    source = _read(BACKEND_ROOT / "utils" / "encryption_utils.py")

    assert "ENCRYPTION_KEY is required" in source
    assert "RuntimeError" in source


def test_assistant_execute_rejects_arbitrary_client_action_payloads():
    api_source = _read(BACKEND_ROOT / "api" / "ai_assistant_api.py")
    frontend_source = _read(FRONTEND_ROOT / "lib" / "api" / "ai.js")

    assert 'payload.get("action")' not in api_source
    assert "execute_issued_action" in api_source
    assert "issue_response_actions" in api_source
    assert "body: JSON.stringify({ action_id: action.action_id })" in frontend_source
    assert "body: JSON.stringify({ action })" not in frontend_source


def test_finn_actions_are_issued_and_user_bound_before_execution():
    source = _read(BACKEND_ROOT / "services" / "finn_plan_service.py")

    assert "issue_response_actions" in source
    assert "_issue_pending_action" in source
    assert "issued_by" in source
    assert "execute_issued_action" in source
    assert "WHERE id = :id AND user_id = :user_id" in source
    assert "status = 'pending'" in source


def test_mission_control_endpoint_also_issues_server_side_action_ids():
    api_source = _read(BACKEND_ROOT / "api" / "ai_assistant_api.py")
    service_source = _read(BACKEND_ROOT / "services" / "finn_plan_service.py")

    assert '"/assistant/mission-control"' in api_source
    assert "await finn.issue_response_actions(current_user[\"id\"], response)" in api_source
    assert "def _is_server_issued_action" in service_source
    assert "resolve_mission_item" in service_source
