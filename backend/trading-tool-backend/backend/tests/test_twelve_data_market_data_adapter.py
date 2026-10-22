import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import httpx

from backend.schemas.market_provider_schema import AssetRecord
from backend.services.providers.twelve_data_market_data_adapter import TwelveDataMarketDataAdapter, _parse_datetime
from backend.services.providers.twelve_data_response_cache import TwelveDataResponseCache
from backend.services.providers.twelve_data_technical_indicator_adapter import TwelveDataTechnicalIndicatorAdapter
from backend.services.providers.binance_market_data_adapter import BinanceMarketDataAdapter


@pytest.fixture(autouse=True)
def clear_twelve_data_response_cache():
    TwelveDataResponseCache.clear_for_testing()


def test_twelve_data_quote_without_configuration_is_typed_unavailable():
    adapter = TwelveDataMarketDataAdapter(api_key="")
    asset = AssetRecord(
        symbol="AAPL",
        display_name="Apple Inc.",
        asset_class="equity",
        provider="twelve_data",
        quote_currency="USD",
        primary_provider="twelve_data",
        provider_symbol="AAPL",
    )

    with pytest.raises(ValueError, match="twelve_data_not_configured"):
        asyncio.run(adapter.fetch_latest_snapshot(asset))


def test_twelve_data_quote_is_normalized_for_persistent_market_snapshots(monkeypatch):
    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "close": "221.40",
                "open": "219.10",
                "high": "222.20",
                "low": "218.50",
                "previous_close": "220.01",
                "change": "1.39",
                "percent_change": "0.63",
                "volume": "1234567",
                "datetime": "2026-10-22 14:33:00",
                "timestamp": 1792693980,
                "currency": "USD",
                "exchange": "NASDAQ",
            }

    class _Client:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, url, params):
            assert url.endswith("/quote")
            assert params["symbol"] == "AAPL"
            assert params["apikey"] == "test-key"
            return _Response()

    monkeypatch.setattr(
        "backend.services.providers.twelve_data_market_data_adapter.httpx.AsyncClient",
        _Client,
    )
    adapter = TwelveDataMarketDataAdapter(api_key="test-key")
    asset = AssetRecord(
        symbol="AAPL",
        display_name="Apple Inc.",
        asset_class="stock",
        provider="twelve_data",
        quote_currency="USD",
        primary_provider="twelve_data",
        provider_symbol="AAPL",
        timezone="America/New_York",
    )

    snapshot = asyncio.run(adapter.fetch_latest_snapshot(asset))

    assert snapshot.symbol == "AAPL"
    assert snapshot.provider == "twelve_data"
    assert snapshot.price == 221.40
    assert snapshot.change_percent == 0.63
    assert snapshot.volume == 1234567.0
    assert snapshot.observed_at.isoformat() == "2026-10-22T18:33:00+00:00"


def test_twelve_data_quote_without_epoch_uses_exchange_timezone(monkeypatch):
    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"close": "346.08", "datetime": "2026-10-22 14:33:00", "currency": "USD"}

    class _Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, *_args, **_kwargs):
            return _Response()

    monkeypatch.setattr(
        "backend.services.providers.twelve_data_market_data_adapter.httpx.AsyncClient", _Client
    )
    asset = AssetRecord(
        symbol="AAPL", display_name="Apple Inc.", asset_class="stock",
        provider="twelve_data", quote_currency="USD", provider_symbol="AAPL",
        timezone="America/New_York",
    )

    snapshot = asyncio.run(TwelveDataMarketDataAdapter(api_key="test-key").fetch_latest_snapshot(asset))
    assert snapshot.observed_at.isoformat() == "2026-10-22T18:33:00+00:00"


def test_twelve_data_exchange_time_conversion_tracks_daylight_saving():
    assert _parse_datetime("2026-10-22 14:33:00", "America/New_York").isoformat() == "2026-10-22T18:33:00+00:00"
    assert _parse_datetime("2026-11-02 14:33:00", "America/New_York").isoformat() == "2026-11-02T19:33:00+00:00"


@pytest.mark.parametrize("time_fields,expected_error", [
    ({}, "twelve_data_snapshot_missing_time"),
    ({"timestamp": "future"}, "twelve_data_snapshot_missing_time"),
    ({"timestamp": int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp())},
     "twelve_data_snapshot_future_time"),
])
def test_twelve_data_quote_rejects_unverified_or_future_source_time(monkeypatch, time_fields, expected_error):
    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"close": "346.08", "currency": "USD", **time_fields}

    class _Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, *_args, **_kwargs):
            return _Response()

    monkeypatch.setattr(
        "backend.services.providers.twelve_data_market_data_adapter.httpx.AsyncClient", _Client
    )
    asset = AssetRecord(symbol="AAPL", display_name="Apple Inc.", asset_class="stock",
                        provider="twelve_data", quote_currency="USD", provider_symbol="AAPL",
                        timezone="America/New_York")

    with pytest.raises(ValueError, match=expected_error):
        asyncio.run(TwelveDataMarketDataAdapter(api_key="test-key").fetch_latest_snapshot(asset))


def test_binance_snapshot_uses_provider_close_time_not_receipt_time(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"lastPrice": "100", "closeTime": 1790985600000}

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr("backend.services.providers.binance_market_data_adapter.httpx.AsyncClient", Client)
    asset = AssetRecord(symbol="BTC", display_name="Bitcoin", asset_class="crypto", provider="binance",
                        provider_symbol="BTCUSDT")
    snapshot = asyncio.run(BinanceMarketDataAdapter().fetch_latest_snapshot(asset))
    assert snapshot.observed_at.timestamp() == 1790985600


def test_twelve_data_rate_limit_is_a_typed_safe_provider_failure(monkeypatch):
    class _Response:
        def raise_for_status(self):
            request = httpx.Request("GET", "https://api.twelvedata.com/quote")
            response = httpx.Response(429, request=request)
            raise httpx.HTTPStatusError("rate limited", request=request, response=response)

    class _Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, *_args, **_kwargs):
            return _Response()

    monkeypatch.setattr(
        "backend.services.providers.twelve_data_market_data_adapter.httpx.AsyncClient",
        _Client,
    )
    adapter = TwelveDataMarketDataAdapter(api_key="test-key")
    asset = AssetRecord(
        symbol="AAPL",
        display_name="Apple Inc.",
        asset_class="stock",
        provider="twelve_data",
        quote_currency="USD",
        primary_provider="twelve_data",
        provider_symbol="AAPL",
    )

    with pytest.raises(ValueError, match="^twelve_data_unavailable:http_429$"):
        asyncio.run(adapter.fetch_latest_snapshot(asset))


def test_quote_is_shared_between_snapshot_and_technical_calculation(monkeypatch):
    calls = []

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"close": "221.40", "datetime": "2026-10-21 14:30:00"}

    class _Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, _url, params):
            calls.append(params)
            return _Response()

    monkeypatch.setattr(
        "backend.services.providers.twelve_data_market_data_adapter.httpx.AsyncClient",
        _Client,
    )
    market = TwelveDataMarketDataAdapter(api_key="test-key")
    technical = TwelveDataTechnicalIndicatorAdapter(api_key="test-key")
    asset = AssetRecord(
        symbol="AAPL",
        display_name="Apple Inc.",
        asset_class="stock",
        provider="twelve_data",
        quote_currency="USD",
        primary_provider="twelve_data",
        provider_symbol="AAPL",
    )

    async def run():
        snapshot = await market.fetch_latest_snapshot(asset)
        assert snapshot.price == 221.40
        assert await technical._get_quote("AAPL") == {"close": "221.40", "datetime": "2026-10-21 14:30:00"}

    asyncio.run(run())
    assert len(calls) == 1
