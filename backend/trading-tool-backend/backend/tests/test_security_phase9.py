from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend" / "trading-tool-backend" / "backend"
FRONTEND_ROOT = REPO_ROOT / "frontend" / "trading-tool-frontend"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_auth_api_issues_and_clears_csrf_cookie_for_web_sessions():
    source = _read(BACKEND_ROOT / "api" / "auth_api.py")

    assert 'CSRF_COOKIE_NAME = "csrf_token"' in source
    assert "CSRF_COOKIE_SETTINGS = dict(" in source
    assert "httponly=False" in source
    assert "def _issue_csrf_cookie" in source
    assert "_issue_csrf_cookie(response)" in source
    assert "_issue_csrf_cookie(resp)" in source
    assert 'for cookie_name in ["access_token", "refresh_token", CSRF_COOKIE_NAME]' in source
    assert "if not csrf_token:" in source


def test_main_enforces_csrf_for_cookie_authenticated_unsafe_api_requests():
    source = _read(BACKEND_ROOT / "main.py")

    assert 'UNSAFE_HTTP_METHODS = {"POST", "PUT", "PATCH", "DELETE"}' in source
    assert "async def csrf_protect_cookie_auth_middleware" in source
    assert "CSRF_EXEMPT_PATHS = {" in source
    assert '"/api/auth/login"' in source
    assert '"/api/auth/register"' in source
    assert 'request.url.path.startswith("/api/")' in source
    assert 'request.cookies.get("access_token") or request.cookies.get("refresh_token")' in source
    assert 'request.headers.get(CSRF_HEADER_NAME)' in source
    assert 'detail": "CSRF validation failed."' in source


def test_frontend_web_requests_send_csrf_header_on_unsafe_methods():
    auth_source = _read(FRONTEND_ROOT / "lib" / "api" / "auth.ts")
    provider_source = _read(FRONTEND_ROOT / "components" / "auth" / "AuthProvider.tsx")
    api_client_source = _read(FRONTEND_ROOT / "lib" / "api" / "apiClient.ts")

    assert "export function getCsrfToken()" in auth_source
    assert 'document.cookie.match(/(?:^|; )csrf_token=([^;]+)/)' in auth_source
    assert '["POST", "PUT", "PATCH", "DELETE"].includes(normalizedMethod)' in auth_source
    assert 'merged.set("X-CSRF-Token", csrfToken)' in auth_source
    assert "buildAuthHeaders(options.headers, method)" in auth_source
    assert 'buildAuthHeaders(undefined, "POST")' in auth_source
    assert 'buildAuthHeaders(undefined, "GET")' in auth_source
    assert "buildAuthHeaders({" in provider_source and "}, method).entries()" in provider_source
    assert 'buildJsonHeaders("POST", init, cacheMode)' in api_client_source
    assert 'buildJsonHeaders("PUT", init, cacheMode)' in api_client_source
    assert 'buildJsonHeaders("DELETE", init, cacheMode)' in api_client_source
