import pytest

from backend.services.providers.twelve_data_macro_provider import (
    DXY_BASE_FACTOR,
    DXY_COMPONENT_WEIGHTS,
    TwelveDataMacroProvider,
)


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_provider_supports_validated_macro_symbols():
    provider = TwelveDataMacroProvider(api_key="test-key")

    assert provider.supports_indicator("sp500") is False
    assert provider.supports_indicator("vix") is False
    assert provider.supports_indicator("dxy") is False
    assert provider.supports_indicator("gold_price") is True
    assert provider.supports_indicator("oil_price") is False
    assert provider.supports_indicator("us10y") is False
    assert provider.supports_indicator("us02y") is False


def test_provider_fetches_quote_value(monkeypatch):
    def fake_get(url, params=None, timeout=10, headers=None):
        assert params["symbol"] == "XAU/USD"
        assert params["apikey"] == "test-key"
        return _Response({"close": "4333.46"})

    monkeypatch.setattr("backend.services.providers.twelve_data_macro_provider.requests.get", fake_get)

    provider = TwelveDataMacroProvider(api_key="test-key")

    assert provider.fetch_latest_value("gold_price") == pytest.approx(4333.46)


def test_provider_returns_none_for_non_twelve_data_macro():
    provider = TwelveDataMacroProvider(api_key="test-key")

    assert provider.fetch_latest_value("sp500") is None


def test_provider_can_build_exact_derived_dxy(monkeypatch):
    quotes = {
        "EUR/USD": 1.16,
        "USD/JPY": 157.0,
        "GBP/USD": 1.34,
        "USD/CAD": 1.35,
        "USD/SEK": 10.4,
        "USD/CHF": 0.82,
    }

    provider = TwelveDataMacroProvider(api_key="test-key")
    monkeypatch.setattr(
        provider,
        "fetch_quote_value",
        lambda provider_symbol: quotes[provider_symbol],
    )

    value = provider.fetch_derived_dxy()
    expected = DXY_BASE_FACTOR
    for provider_symbol, (_, exponent) in DXY_COMPONENT_WEIGHTS.items():
        expected *= quotes[provider_symbol] ** exponent

    assert value is not None
    assert value == pytest.approx(expected)
