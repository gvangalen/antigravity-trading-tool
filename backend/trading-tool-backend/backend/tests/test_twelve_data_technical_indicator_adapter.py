from backend.schemas.market_provider_schema import AssetRecord
from backend.services.providers.twelve_data_technical_indicator_adapter import (
    TwelveDataTechnicalIndicatorAdapter,
)


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


def test_provider_symbol_maps_stablecoin_crypto_pairs_to_usd():
    adapter = TwelveDataTechnicalIndicatorAdapter(api_key="test-key")

    assert adapter._provider_symbol(_asset(provider_symbol="BTCUSDT")) == "BTC/USD"
    assert adapter._provider_symbol(_asset(provider_symbol="ETHUSDC")) == "ETH/USD"
