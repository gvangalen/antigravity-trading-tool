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

    assert adapter._provider_symbol(_asset(provider_symbol="BTCUSDT")) == "BTC/USDT"
    assert adapter._provider_symbol(_asset(provider_symbol="ETHUSD")) == "ETH/USD"
    assert adapter._provider_symbol(_asset(symbol="AAPL", provider_symbol="AAPL", asset_class="stock")) == "AAPL"
