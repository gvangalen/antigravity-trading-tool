from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
FRONTEND_ROOT = REPO_ROOT / "frontend" / "trading-tool-frontend"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_auth_client_clears_local_user_and_tokens_on_logout_or_failed_refresh():
    auth_source = _read(FRONTEND_ROOT / "lib" / "api" / "auth.ts")
    user_source = _read(FRONTEND_ROOT / "lib" / "api" / "user.ts")

    assert "export function clearStoredAuth()" in auth_source
    assert "clearTokenLocal();" in auth_source
    assert "clearUserLocal();" in auth_source
    assert "clearStoredAuth();" in auth_source
    assert 'window.location.href = "/login";' in auth_source
    assert "localStorage.removeItem(LOCAL_USER_KEY)" in user_source
    assert "localStorage.removeItem(LOCAL_ACCESS_TOKEN_KEY)" in user_source
    assert "localStorage.removeItem(LOCAL_REFRESH_TOKEN_KEY)" in user_source


def test_auth_login_overwrites_local_user_and_authenticated_fetch_stays_cookie_scoped():
    auth_source = _read(FRONTEND_ROOT / "lib" / "api" / "auth.ts")

    assert "saveUserLocal(user);" in auth_source
    assert "credentials: \"include\"" in auth_source
    assert "buildAuthHeaders" in auth_source
    assert 'forceFresh || method !== "GET" ? "no-store" : "default"' in auth_source
    assert "withCacheBust(" in auth_source
    assert "Date.now()" in auth_source
