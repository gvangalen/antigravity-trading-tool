from backend.services.providers.twelve_data_macro_provider import TwelveDataMacroProvider


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_provider_supports_validated_macro_symbols():
    provider = TwelveDataMacroProvider(api_key="test-key")

    assert provider.supports_indicator("sp500") is True
    assert provider.supports_indicator("vix") is True
    assert provider.supports_indicator("dxy") is True
    assert provider.supports_indicator("gold_price") is True
    assert provider.supports_indicator("oil_price") is False


def test_provider_fetches_quote_value(monkeypatch):
    def fake_get(url, params=None, timeout=10, headers=None):
        assert params["symbol"] == "SPX"
        assert params["apikey"] == "test-key"
        return _Response({"close": "7751.90"})

    monkeypatch.setattr("backend.services.providers.twelve_data_macro_provider.requests.get", fake_get)

    provider = TwelveDataMacroProvider(api_key="test-key")

    assert provider.fetch_latest_value("sp500") == 7751.9
