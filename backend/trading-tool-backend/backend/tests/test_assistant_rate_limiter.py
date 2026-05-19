import pytest
from fastapi import HTTPException

from backend.api import ai_assistant_api


class _Client:
    host = "127.0.0.1"


class _Request:
    client = _Client()

    def __init__(self, headers=None):
        self.headers = headers or {}


def test_client_ip_prefers_forwarded_headers():
    request = _Request({"x-forwarded-for": "203.0.113.10, 127.0.0.1"})

    assert ai_assistant_api._client_ip(request) == "203.0.113.10"


def test_local_proxy_ip_does_not_share_global_ip_bucket(monkeypatch):
    calls = []

    def fake_check(identifier, *, limit=None, window_seconds=None):
        calls.append((identifier, limit, window_seconds))

    monkeypatch.setattr(ai_assistant_api.chat_rate_limiter, "check_rate_limit", fake_check)

    ip_addr, limit = ai_assistant_api._apply_assistant_rate_limit(
        user_id=42,
        raw_request=_Request(),
        query="Maak een strategie met 100 euro",
        context={"finn_draft": {"draft_kind": "strategy"}},
        endpoint="/assistant/chat",
    )

    assert ip_addr == "127.0.0.1"
    assert limit == ai_assistant_api.ASSISTANT_FINN_DRAFT_LIMIT
    assert calls == [("user_42:assistant", ai_assistant_api.ASSISTANT_FINN_DRAFT_LIMIT, None)]


def test_real_ip_gets_user_and_ip_limits(monkeypatch):
    calls = []

    def fake_check(identifier, *, limit=None, window_seconds=None):
        calls.append((identifier, limit))

    monkeypatch.setattr(ai_assistant_api.chat_rate_limiter, "check_rate_limit", fake_check)

    ai_assistant_api._apply_assistant_rate_limit(
        user_id=42,
        raw_request=_Request({"x-real-ip": "198.51.100.25"}),
        query="Wat denk je van BTC?",
        context={},
        endpoint="/assistant/chat",
    )

    assert calls == [
        ("user_42:assistant", ai_assistant_api.ASSISTANT_USER_LIMIT),
        ("ip_198.51.100.25:assistant", ai_assistant_api.ASSISTANT_IP_FALLBACK_LIMIT),
    ]


def test_limiter_returns_retry_after_header():
    limiter = ai_assistant_api.InMemoryRateLimiter(requests_limit=1, window_seconds=60)
    limiter.check_rate_limit("user_test")

    with pytest.raises(HTTPException) as exc:
        limiter.check_rate_limit("user_test")

    assert exc.value.status_code == 429
    assert int(exc.value.headers["Retry-After"]) > 0
