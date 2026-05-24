from backend.services.dashboard_service import DashboardService


def test_mobile_overview_cache_disabled_by_default(monkeypatch):
    monkeypatch.delenv("DASHBOARD_OVERVIEW_CACHE_ENABLED", raising=False)

    assert DashboardService.mobile_overview_cache_enabled() is False


def test_mobile_overview_cache_can_be_enabled_explicitly(monkeypatch):
    for value in ["1", "true", "yes", "on"]:
        monkeypatch.setenv("DASHBOARD_OVERVIEW_CACHE_ENABLED", value)

        assert DashboardService.mobile_overview_cache_enabled() is True


def test_mobile_overview_cache_rejects_unknown_values(monkeypatch):
    monkeypatch.setenv("DASHBOARD_OVERVIEW_CACHE_ENABLED", "maybe")

    assert DashboardService.mobile_overview_cache_enabled() is False
