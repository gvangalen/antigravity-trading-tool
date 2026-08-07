from backend.utils.macro_interpreter import fetch_macro_value


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_sp500_yahoo_falls_back_to_gspc_when_primary_response_has_no_value(monkeypatch):
    responses = [
        _Response({"chart": {"result": [{"meta": {"regularMarketPrice": None}, "indicators": {"quote": [{"close": [None]}]}}]}}),
        _Response({"chart": {"result": [{"meta": {"regularMarketPrice": 7751.9}}]}}),
    ]

    def fake_get(url, timeout=10, headers=None):
        return responses.pop(0)

    monkeypatch.setattr("backend.utils.macro_interpreter._http_get", fake_get)

    result = fetch_macro_value(
        "sp500",
        source="yahoo",
        link="https://query1.finance.yahoo.com/v8/finance/chart/%5ESPX",
    )

    assert result == {"value": 7751.9}


def test_sp500_yahoo_returns_primary_value_when_available(monkeypatch):
    def fake_get(url, timeout=10, headers=None):
        return _Response({"chart": {"result": [{"meta": {"regularMarketPrice": 7743.16}}]}})

    monkeypatch.setattr("backend.utils.macro_interpreter._http_get", fake_get)

    result = fetch_macro_value(
        "sp500",
        source="yahoo",
        link="https://query1.finance.yahoo.com/v8/finance/chart/%5ESPX",
    )

    assert result == {"value": 7743.16}


def test_sp500_prefers_twelve_data_when_api_key_is_available(monkeypatch):
    class FakeProvider:
        def supports_indicator(self, indicator_name):
            return indicator_name == "sp500"

        def fetch_latest_value(self, indicator_name):
            assert indicator_name == "sp500"
            return 7755.25

    monkeypatch.setattr("backend.utils.macro_interpreter.TwelveDataMacroProvider", lambda: FakeProvider())

    result = fetch_macro_value(
        "sp500",
        source="yahoo",
        link="https://query1.finance.yahoo.com/v8/finance/chart/%5ESPX",
    )

    assert result == {"value": 7755.25}


def test_sp500_falls_back_to_yahoo_when_twelve_data_has_no_value(monkeypatch):
    class FakeProvider:
        def supports_indicator(self, indicator_name):
            return indicator_name == "sp500"

        def fetch_latest_value(self, indicator_name):
            return None

    monkeypatch.setattr("backend.utils.macro_interpreter.TwelveDataMacroProvider", lambda: FakeProvider())
    monkeypatch.setattr(
        "backend.utils.macro_interpreter._http_get",
        lambda url, timeout=10: _Response({"chart": {"result": [{"meta": {"regularMarketPrice": 7743.16}}]}}),
    )

    result = fetch_macro_value(
        "sp500",
        source="yahoo",
        link="https://query1.finance.yahoo.com/v8/finance/chart/%5ESPX",
    )

    assert result == {"value": 7743.16}
