import pytest

from backend.utils.macro_interpreter import (
    DXY_BASE_FACTOR,
    DXY_COMPONENT_WEIGHTS,
    _fetch_dxy_from_twelve_data,
    _fred_csv_url,
    fetch_macro_value,
)


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _ResponseText:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


def test_sp500_fred_returns_last_csv_value(monkeypatch):
    def fake_fetch_text(url, timeout=20):
        assert url == _fred_csv_url("SP500")
        return "observation_date,SP500\n2026-08-05,7721.70\n2026-08-06,7733.85\n"

    monkeypatch.setattr("backend.utils.macro_interpreter._fetch_text", fake_fetch_text)

    result = fetch_macro_value(
        "sp500",
        source="fred",
        link="fred:SP500",
    )

    assert result == {"value": 7733.85}


def test_sp500_legacy_fred_json_url_returns_last_value(monkeypatch):
    def fake_fetch_text(url, timeout=20):
        assert url == _fred_csv_url("SP500")
        return "observation_date,SP500\n2026-08-05,7723.55\n2026-08-06,7709.96\n"

    monkeypatch.setattr("backend.utils.macro_interpreter._fetch_text", fake_fetch_text)

    result = fetch_macro_value(
        "sp500",
        source="fred",
        link="https://api.stlouisfed.org/fred/series/observations?series_id=SP500&api_key=old-key&file_type=json",
    )

    assert result == {"value": 7709.96}


def test_vix_fred_skips_blank_rows(monkeypatch):
    def fake_fetch_text(url, timeout=20):
        assert url == _fred_csv_url("VIXCLS")
        return "observation_date,VIXCLS\n2026-08-05,15.81\n2026-08-06,.\n2026-08-07,15.15\n"

    monkeypatch.setattr("backend.utils.macro_interpreter._fetch_text", fake_fetch_text)

    result = fetch_macro_value(
        "vix",
        source="fred",
        link="fred:VIXCLS",
    )

    assert result == {"value": 15.15}


def test_inflation_rate_uses_cpi_year_over_year(monkeypatch):
    def fake_fetch_text(url, timeout=20):
        assert url == _fred_csv_url("CPIAUCSL")
        return (
            "observation_date,CPIAUCSL\n"
            "2025-06-01,320.000\n"
            "2025-07-01,321.000\n"
            "2025-08-01,322.000\n"
            "2025-09-01,323.000\n"
            "2025-10-01,324.000\n"
            "2025-11-01,325.000\n"
            "2025-12-01,326.000\n"
            "2026-01-01,327.000\n"
            "2026-02-01,328.000\n"
            "2026-03-01,329.000\n"
            "2026-04-01,330.000\n"
            "2026-05-01,331.000\n"
            "2026-06-01,332.568\n"
        )

    monkeypatch.setattr("backend.utils.macro_interpreter._fetch_text", fake_fetch_text)

    result = fetch_macro_value(
        "inflation_rate",
        source="fred",
        link="fred:CPIAUCSL",
    )

    assert result == {"value": pytest.approx(((332.568 / 320.0) - 1.0) * 100.0)}


def test_inflation_rate_legacy_fred_json_url_uses_year_over_year(monkeypatch):
    def fake_fetch_text(url, timeout=20):
        assert url == _fred_csv_url("CPIAUCSL")
        return (
            "observation_date,CPIAUCSL\n"
            "2025-06-01,320.000\n"
            "2025-07-01,321.000\n"
            "2025-08-01,322.000\n"
            "2025-09-01,323.000\n"
            "2025-10-01,324.000\n"
            "2025-11-01,325.000\n"
            "2025-12-01,326.000\n"
            "2026-01-01,327.000\n"
            "2026-02-01,328.000\n"
            "2026-03-01,329.000\n"
            "2026-04-01,330.000\n"
            "2026-05-01,331.000\n"
            "2026-06-01,332.568\n"
        )

    monkeypatch.setattr("backend.utils.macro_interpreter._fetch_text", fake_fetch_text)

    result = fetch_macro_value(
        "inflation_rate",
        source="fred",
        link="https://api.stlouisfed.org/fred/series/observations?series_id=CPIAUCSL&api_key=old-key&file_type=json",
    )

    assert result == {"value": pytest.approx(((332.568 / 320.0) - 1.0) * 100.0)}


def test_gold_prefers_twelve_data_when_configured(monkeypatch):
    class FakeProvider:
        def supports_indicator(self, indicator_name):
            return indicator_name == "gold_price"

        def fetch_latest_value(self, indicator_name):
            assert indicator_name == "gold_price"
            return 4333.46

    monkeypatch.setattr("backend.utils.macro_interpreter.TwelveDataMacroProvider", lambda: FakeProvider())

    result = fetch_macro_value(
        "gold_price",
        source="twelve_data",
        link="twelve_data:XAU/USD",
    )

    assert result == {"value": 4333.46}


def test_google_trends_returns_latest_interest_value(monkeypatch):
    class FakeResponse:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    class FakeSession:
        def __init__(self):
            self.headers = {}

        def get(self, url, params=None, timeout=20):
            if "explore" in url:
                return FakeResponse(
                    """)]}'
{"widgets":[{"id":"TIMESERIES","token":"abc123","request":{"time":"2026-05-07 2026-08-07"}}]}"""
                )
            return FakeResponse(
                """)]}'
{"default":{"timelineData":[{"value":[42]},{"value":[55]}]}}"""
            )

    monkeypatch.setattr("backend.utils.macro_interpreter.requests.Session", FakeSession)

    result = fetch_macro_value(
        "google_trends",
        source="custom",
        link="https://trends.google.com/trends/api/widgetdata/multiline",
    )

    assert result == {"value": 55.0}


def test_etf_bitcoin_inflow_returns_latest_total_from_bitbo_table(monkeypatch):
    def fake_fetch_text(url, timeout=20):
        assert "bitbo.io/treasuries/etf-flows/" in url
        return """
        <table class="stats-table larger-table">
          <tbody>
            <tr>
              <th><span>Date</span></th>
              <th><span>IBIT</span></th>
              <th><span>Totals</span></th>
            </tr>
            <tr>
              <td class="cell right-align"><span>Aug 05, 2026</span></td>
              <td class="cell right-align green"><span>196.2</span></td>
              <td class="cell right-align green"><span>274.3</span></td>
            </tr>
          </tbody>
        </table>
        """

    monkeypatch.setattr("backend.utils.macro_interpreter._fetch_text", fake_fetch_text)

    result = fetch_macro_value(
        "etf_bitcoin_inflow",
        source="custom",
        link="https://api.farside.co.uk/v1/etf/btc/latest",
    )

    assert result == {"value": 274.3}


def test_dxy_derived_uses_twelve_data_before_other_routes(monkeypatch):
    class FakeProvider:
        def fetch_derived_dxy(self):
            return 99.86

    monkeypatch.setattr("backend.utils.macro_interpreter.TwelveDataMacroProvider", lambda: FakeProvider())

    result = fetch_macro_value(
        "dxy",
        source="derived",
        link="derived:dxy",
    )

    assert result == {"value": 99.86}


def test_dxy_formula_matches_exact_weighted_basket(monkeypatch):
    class FakeProvider:
        def fetch_derived_dxy(self):
            rates = {
                "EUR/USD": 1.16,
                "USD/JPY": 157.0,
                "GBP/USD": 1.34,
                "USD/CAD": 1.35,
                "USD/SEK": 10.4,
                "USD/CHF": 0.82,
            }
            value = DXY_BASE_FACTOR
            for provider_symbol, (weight_key, exponent) in DXY_COMPONENT_WEIGHTS.items():
                assert weight_key
                value *= rates[provider_symbol] ** exponent
            return value

    expected = (
        DXY_BASE_FACTOR
        * (1.16 ** DXY_COMPONENT_WEIGHTS["EUR/USD"][1])
        * (157.0 ** DXY_COMPONENT_WEIGHTS["USD/JPY"][1])
        * (1.34 ** DXY_COMPONENT_WEIGHTS["GBP/USD"][1])
        * (1.35 ** DXY_COMPONENT_WEIGHTS["USD/CAD"][1])
        * (10.4 ** DXY_COMPONENT_WEIGHTS["USD/SEK"][1])
        * (0.82 ** DXY_COMPONENT_WEIGHTS["USD/CHF"][1])
    )

    assert _fetch_dxy_from_twelve_data(FakeProvider()) == pytest.approx(expected)
