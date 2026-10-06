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

    assert "options.forceFresh || method !== \"GET\"" in source
    assert "forceFresh?: boolean" in source
    assert 'const cacheMode = (options as any)?.cache ?? "no-store"' not in source
    assert "Cache-Control" in source


def test_active_asset_workspace_polling_uses_visibility_and_shared_request_cache():
    source = (FRONTEND_ROOT / "hooks" / "useAssetWorkspaceData.js").read_text()
    cache = (FRONTEND_ROOT / "lib" / "clientDataCache.js").read_text()

    assert "useVisibilityPolling" in source
    assert "backgroundIntervalMs: 300_000" in source
    assert "if (!forceFresh && entry.inflight)" in cache


def test_my_plan_refreshes_setup_matches_only_while_visible():
    source = (FRONTEND_ROOT / "components" / "workflows" / "MyPlanWorkflow.jsx").read_text()

    assert 'document.visibilityState !== "visible"' in source
    assert 'document.addEventListener("visibilitychange", refreshIfVisible)' in source
    assert "fetchSetupMarketMatches()" in source


def test_market_live_price_fetch_dedupes_same_symbol_requests():
    source = (FRONTEND_ROOT / "lib" / "api" / "market.js").read_text()

    assert "const inflightLatestPriceRequests = new Map();" in source
    assert "inflightLatestPriceRequests.get(requestKey)" in source
    assert "inflightLatestPriceRequests.set(requestKey, request);" in source
    assert "inflightLatestPriceRequests.delete(requestKey);" in source
