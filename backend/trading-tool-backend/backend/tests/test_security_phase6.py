from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend" / "trading-tool-backend" / "backend"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_assistant_execute_route_has_dedicated_rate_limit_and_reasoning_redaction():
    source = _read(BACKEND_ROOT / "api" / "ai_assistant_api.py")

    assert "execute_rate_limiter = InMemoryRateLimiter" in source
    assert "def _apply_assistant_execute_rate_limit" in source
    assert "def _redact_assistant_reasoning" in source
    assert 'payload["reasoning"] = None' in source
    assert "_apply_assistant_execute_rate_limit(user_id=user_id, raw_request=request)" in source
    assert "reasoning = None" in source


def test_sensitive_manual_order_routes_have_rate_limits():
    source = _read(BACKEND_ROOT / "api" / "bot_api.py")

    assert "order_rate_limiter = InMemoryRateLimiter" in source
    assert "def _apply_sensitive_order_rate_limit" in source
    assert 'action_key="manual_order"' in source
    assert 'action_key="manual_order_preflight"' in source


def test_finn_replay_paths_return_explicit_replayed_flag():
    source = _read(BACKEND_ROOT / "services" / "finn_plan_service.py")

    assert 'return {**result, "replayed": True}' in source
