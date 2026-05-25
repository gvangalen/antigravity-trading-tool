from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
FRONTEND_ROOT = REPO_ROOT / "frontend" / "trading-tool-frontend"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_visibility_polling_helper_exists_and_handles_background_tabs():
    source = _read(FRONTEND_ROOT / "hooks" / "useVisibilityPolling.js")

    assert "document.visibilityState" in source
    assert "visibilitychange" in source
    assert "backgroundIntervalMs" in source
    assert "waitUntilVisible" in source


def test_hotspot_polling_uses_visibility_policy_instead_of_raw_intervals():
    hotspot_files = [
        FRONTEND_ROOT / "app" / "(protected)" / "admin" / "logs" / "page.jsx",
        FRONTEND_ROOT / "hooks" / "useIntelligenceEvents.js",
        FRONTEND_ROOT / "hooks" / "useAgentData.js",
        FRONTEND_ROOT / "hooks" / "useMarketData.js",
        FRONTEND_ROOT / "components" / "market" / "MarketLiveCard.jsx",
        FRONTEND_ROOT / "components" / "bot" / "TradePanelContainer.jsx",
    ]

    for path in hotspot_files:
        source = _read(path)
        assert "useVisibilityPolling" in source, path
        assert "setInterval(" not in source, path


def test_freshness_sensitive_frontend_calls_are_explicitly_no_store():
    intelligence_source = _read(FRONTEND_ROOT / "hooks" / "useIntelligenceEvents.js")
    admin_source = _read(FRONTEND_ROOT / "app" / "(protected)" / "admin" / "logs" / "page.jsx")
    market_api_source = _read(FRONTEND_ROOT / "lib" / "api" / "market.js")
    report_page_source = _read(FRONTEND_ROOT / "app" / "(protected)" / "report" / "page.jsx")
    report_hook_source = _read(FRONTEND_ROOT / "hooks" / "useReportData.js")

    assert 'apiGet("/api/assistant/events", { forceFresh: true })' in intelligence_source
    assert "fetchAdminLogs(filters, { forceFresh: true })" in admin_source
    assert 'cache: "no-store"' in market_api_source
    assert "waitUntilVisible()" in report_page_source
    assert "waitUntilVisible()" in report_hook_source
    assert "forceFresh: true" in report_page_source
    assert "forceFresh: true" in report_hook_source
