from fastapi import HTTPException

from backend.api import auth_api


class _Client:
    def __init__(self, host="127.0.0.1"):
        self.host = host


class _Request:
    def __init__(self, headers=None, host="127.0.0.1"):
        self.headers = headers or {}
        self.client = _Client(host=host)


def test_web_login_response_omits_tokens():
    payload = auth_api._login_response_payload(
        {
            "access_token": "access-secret",
            "refresh_token": "refresh-secret",
            "user": type("User", (), {"dict": lambda self: {"id": 1, "email": "henk@example.com"}})(),
        },
        "web",
    )

    assert payload["success"] is True
    assert payload["token_transport"] == "cookie"
    assert "access_token" not in payload
    assert "refresh_token" not in payload


def test_mobile_login_response_keeps_tokens():
    payload = auth_api._login_response_payload(
        {
            "access_token": "access-secret",
            "refresh_token": "refresh-secret",
            "user": type("User", (), {"dict": lambda self: {"id": 1, "email": "henk@example.com"}})(),
        },
        "mobile",
    )

    assert payload["token_transport"] == "body+cookie"
    assert payload["access_token"] == "access-secret"
    assert payload["refresh_token"] == "refresh-secret"


def test_client_mode_detects_mobile_header():
    assert auth_api._auth_client_mode("mobile-expo") == "mobile"
    assert auth_api._auth_client_mode("MOBILE") == "mobile"
    assert auth_api._auth_client_mode(None) == "web"


def test_auth_login_rate_limit_returns_retry_after():
    limiter = auth_api.InMemoryRateLimiter(requests_limit=1, window_seconds=60)
    limiter.check_rate_limit("auth_login_email:test@example.com")

    try:
        limiter.check_rate_limit("auth_login_email:test@example.com")
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 429
        assert int(exc.headers["Retry-After"]) > 0


def test_auth_login_rate_limit_applies_per_email_and_ip(monkeypatch):
    calls = []

    def fake_check(identifier, *, limit=None, window_seconds=None, detail=None):
        calls.append((identifier, limit, detail))

    monkeypatch.setattr(auth_api, "auth_rate_limiter", type("Limiter", (), {"check_rate_limit": staticmethod(fake_check)})())

    auth_api._apply_auth_login_rate_limit(
        _Request({"x-forwarded-for": "203.0.113.10, 127.0.0.1"}),
        "henk@example.com",
    )

    assert calls == [
        (
            "auth_login_email:henk@example.com",
            auth_api.AUTH_LOGIN_EMAIL_LIMIT,
            "Te veel loginpogingen. Wacht kort en probeer opnieuw.",
        ),
        (
            "auth_login_ip:203.0.113.10",
            auth_api.AUTH_LOGIN_IP_LIMIT,
            "Te veel loginpogingen vanaf dit IP-adres. Wacht kort en probeer opnieuw.",
        ),
    ]


def test_auth_refresh_rate_limit_applies_per_ip(monkeypatch):
    calls = []

    def fake_check(identifier, *, limit=None, window_seconds=None, detail=None):
        calls.append((identifier, limit, detail))

    monkeypatch.setattr(auth_api, "auth_rate_limiter", type("Limiter", (), {"check_rate_limit": staticmethod(fake_check)})())

    auth_api._apply_auth_refresh_rate_limit(_Request({"x-real-ip": "198.51.100.7"}))

    assert calls == [
        (
            "auth_refresh_ip:198.51.100.7",
            auth_api.AUTH_REFRESH_IP_LIMIT,
            "Te veel refresh-verzoeken. Wacht kort en probeer opnieuw.",
        )
    ]
