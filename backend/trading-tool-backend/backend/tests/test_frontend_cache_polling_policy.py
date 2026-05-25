from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
FRONTEND_ROOT = REPO_ROOT / "frontend" / "trading-tool-frontend"


def test_api_client_get_no_longer_forces_no_store_by_default():
    source = (FRONTEND_ROOT / "lib" / "api" / "apiClient.ts").read_text()

    assert 'method !== "GET"' in source
    assert 'return "default"' in source
    assert 'cache: "no-store"' not in source
    assert "forceFresh" in source


def test_fetch_auth_uses_method_aware_cache_policy():
    source = (FRONTEND_ROOT / "lib" / "api" / "auth.ts").read_text()

    assert 'method === "GET" ? "default" : "no-store"' in source
    assert 'const cacheMode = (options as any)?.cache ?? "no-store"' not in source
    assert "Cache-Control" in source


def test_dashboard_polling_is_visibility_aware_and_single_flight():
    source = (FRONTEND_ROOT / "hooks" / "useDashboardData.js").read_text()

    assert "FOREGROUND_POLL_INTERVAL_MS = 120000" in source
    assert "BACKGROUND_POLL_INTERVAL_MS = 300000" in source
    assert "document.visibilityState" in source
    assert "visibilitychange" in source
    assert "loadingRef.current" in source
    assert "setInterval(load, 60000)" not in source
