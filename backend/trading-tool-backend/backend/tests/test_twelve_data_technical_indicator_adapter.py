import logging

import pytest

from backend.schemas.market_provider_schema import AssetRecord
from backend.services.providers.twelve_data_technical_indicator_adapter import (
    TwelveDataTechnicalIndicatorAdapter,
)
from backend.services.providers.twelve_data_response_cache import TwelveDataResponseCache


@pytest.fixture(autouse=True)
def clear_twelve_data_response_cache():
    TwelveDataResponseCache.clear_for_testing()


def _asset(symbol: str = "BTC", provider_symbol: str = "BTCUSDT", asset_class: str = "crypto") -> AssetRecord:
    return AssetRecord(
        symbol=symbol,
        display_name=symbol,
        asset_class=asset_class,
        market="CRYPTO",
        provider="binance",
        provider_symbol=provider_symbol,
    )


def test_provider_symbol_normalizes_crypto_pairs_for_twelve_data():
    adapter = TwelveDataTechnicalIndicatorAdapter(api_key="test-key")

    assert adapter._provider_symbol(_asset(provider_symbol="BTCUSDT")) == "BTC/USD"
    assert adapter._provider_symbol(_asset(provider_symbol="ETHUSD")) == "ETH/USD"
    assert adapter._provider_symbol(_asset(symbol="AAPL", provider_symbol="AAPL", asset_class="stock")) == "AAPL"


def test_twelve_data_transport_does_not_log_query_parameter_credentials():
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING


def test_crypto_indicator_falls_back_to_binance_without_twelve_data_key():
    adapter = TwelveDataTechnicalIndicatorAdapter(api_key="")
    adapter.api_key = ""
    candles = []
    for day in range(1, 301):
        close = 100.0 + day
        candles.append(
            {
                "open": close - 1.0,
                "high": close + 2.0,
                "low": close - 2.0,
                "close": close,
                "volume": 1000.0 + day,
            }
        )

    async def run():
        adapter._binance_candle_cache["BTCUSDT"] = candles
        value = await adapter.fetch_indicator_value(_asset(provider_symbol="BTCUSDT"), "ma_50")
        assert value > 1.0

        rsi_value = await adapter.fetch_indicator_value(_asset(provider_symbol="BTCUSDT"), "rsi")
        assert 0.0 <= rsi_value <= 100.0

    import asyncio

    asyncio.run(run())


def test_crypto_indicator_prefers_exchange_history_before_configured_twelve_data():
    adapter = TwelveDataTechnicalIndicatorAdapter(api_key="test-key")
    calls = []

    async def configured_provider(_asset, indicator):
        raise AssertionError("Twelve Data must not be charged while exchange history is available")

    async def exchange_history(_asset, indicator):
        calls.append(("binance", indicator))
        return 55.0

    async def run():
        adapter._fetch_twelve_data_indicator = configured_provider
        adapter._fetch_without_api_key = exchange_history
        assert await adapter.fetch_indicator_value(_asset(), "rsi") == 55.0

    import asyncio

    asyncio.run(run())
    assert calls == [("binance", "rsi")]


def test_crypto_indicator_uses_configured_twelve_data_when_exchange_history_is_unavailable():
    adapter = TwelveDataTechnicalIndicatorAdapter(api_key="test-key")

    async def unavailable_exchange(_asset, _indicator):
        raise ValueError("exchange_unavailable")

    async def configured_provider(_asset, _indicator):
        return 44.0

    async def run():
        adapter._fetch_without_api_key = unavailable_exchange
        adapter._fetch_twelve_data_indicator = configured_provider
        assert await adapter.fetch_indicator_value(_asset(), "rsi") == 44.0

    import asyncio

    asyncio.run(run())


def test_provider_symbol_maps_stablecoin_crypto_pairs_to_usd():
    adapter = TwelveDataTechnicalIndicatorAdapter(api_key="test-key")

    assert adapter._provider_symbol(_asset(provider_symbol="BTCUSDT")) == "BTC/USD"
    assert adapter._provider_symbol(_asset(provider_symbol="ETHUSDC")) == "ETH/USD"


def test_twelve_data_reuses_one_successful_response_for_identical_technical_read(monkeypatch):
    calls = []
    values = [
        {
            "datetime": f"2026-01-{day:02d}",
            "close": str(100 + day),
            "high": str(101 + day),
            "low": str(99 + day),
        }
        for day in range(1, 20)
    ]

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"values": values}

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
        "backend.services.providers.twelve_data_technical_indicator_adapter.httpx.AsyncClient",
        _Client,
    )
    first_adapter = TwelveDataTechnicalIndicatorAdapter(api_key="test-key")
    second_adapter = TwelveDataTechnicalIndicatorAdapter(api_key="test-key")

    async def run():
        asset = _asset(symbol="AAPL", provider_symbol="AAPL", asset_class="stock")
        assert 0.0 <= await first_adapter.fetch_indicator_value(asset, "rsi") <= 100.0
        assert 0.0 <= await second_adapter.fetch_indicator_value(asset, "rsi") <= 100.0

    import asyncio

    asyncio.run(run())
    assert len(calls) == 1


def test_stock_rsi_and_ma200_share_one_cached_history_request(monkeypatch):
    calls = []
    # Twelve Data returns newest daily candles first. The adapter must restore
    # chronological order before calculating any technical value.
    values = [
        {
            "datetime": f"2026-01-{day:03d}",
            "close": str(100 + day),
            "high": str(101 + day),
            "low": str(99 + day),
        }
        for day in range(300, 0, -1)
    ]

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"values": values}

    class _Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, url, params):
            calls.append((url, params))
            return _Response()

    monkeypatch.setattr(
        "backend.services.providers.twelve_data_technical_indicator_adapter.httpx.AsyncClient",
        _Client,
    )
    adapter = TwelveDataTechnicalIndicatorAdapter(api_key="test-key")
    asset = _asset(symbol="AAPL", provider_symbol="AAPL", asset_class="stock")

    async def run():
        assert 0.0 <= await adapter.fetch_indicator_value(asset, "rsi") <= 100.0
        assert await adapter.fetch_indicator_value(asset, "ma_200") > 1.0

    import asyncio

    asyncio.run(run())
    assert len(calls) == 1
    assert calls[0][0].endswith("/time_series")
    assert calls[0][1]["outputsize"] == 300
