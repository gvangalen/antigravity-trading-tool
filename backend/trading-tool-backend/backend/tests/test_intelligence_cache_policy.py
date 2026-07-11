from backend.services.intelligence_service import IntelligenceService


def test_intelligence_cache_enabled_by_default(monkeypatch):
    monkeypatch.delenv("MARKET_INTELLIGENCE_CACHE_TTL_SECONDS", raising=False)

    assert IntelligenceService.cache_enabled() is True
    assert IntelligenceService.cache_ttl_seconds() == 45


def test_intelligence_cache_can_be_disabled_with_zero_ttl(monkeypatch):
    monkeypatch.setenv("MARKET_INTELLIGENCE_CACHE_TTL_SECONDS", "0")

    assert IntelligenceService.cache_enabled() is False
    assert IntelligenceService.cache_ttl_seconds() == 0


def test_intelligence_cache_uses_explicit_positive_ttl(monkeypatch):
    monkeypatch.setenv("MARKET_INTELLIGENCE_CACHE_TTL_SECONDS", "120")

    assert IntelligenceService.cache_enabled() is True
    assert IntelligenceService.cache_ttl_seconds() == 120
