from backend.services.intelligence_service import IntelligenceService


def test_intelligence_cache_disabled_by_default(monkeypatch):
    monkeypatch.delenv("INTELLIGENCE_SERVICE_CACHE_ENABLED", raising=False)

    assert IntelligenceService.cache_enabled() is False


def test_intelligence_cache_enabled_only_by_explicit_truthy_values(monkeypatch):
    for value in ("1", "true", "yes", "on"):
        monkeypatch.setenv("INTELLIGENCE_SERVICE_CACHE_ENABLED", value)

        assert IntelligenceService.cache_enabled() is False


def test_intelligence_cache_rejects_unknown_values(monkeypatch):
    monkeypatch.setenv("INTELLIGENCE_SERVICE_CACHE_ENABLED", "enabled")

    assert IntelligenceService.cache_enabled() is False
