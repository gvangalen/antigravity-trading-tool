"""Historical EUR candles with explicit provenance and coverage checks."""

from datetime import timedelta
from decimal import Decimal

from backend.schemas.market_provider_schema import AssetRecord
from backend.services.asset_catalog_service import DEFAULT_ASSET_CATALOG
from backend.services.providers.binance_market_data_adapter import BinanceMarketDataAdapter


async def historical_eur_chart(review: dict) -> tuple[dict | None, str]:
    symbol = str(review["symbol"]).upper()
    catalog = DEFAULT_ASSET_CATALOG.get(symbol)
    if not catalog or catalog.get("asset_class") != "crypto" or not symbol.isalpha():
        return None, "Geen verifieerbare EUR-candlebron voor dit instrument"
    start, end = review["entry_at"], review["exit_at"]
    duration = end - start
    if duration < timedelta(0) or duration > timedelta(days=900):
        return None, "De tradeperiode valt buiten het ondersteunde chartbereik"
    timeframe = "1h" if duration <= timedelta(days=35) else "1d"
    pad = max(timedelta(hours=2), min(timedelta(days=2), duration / 10))
    asset = AssetRecord(
        symbol=symbol, display_name=symbol, asset_class="crypto",
        provider="binance", primary_provider="binance", provider_symbol=f"{symbol}EUR",
        quote_currency="EUR", exchange="BINANCE",
    )
    try:
        candles = await BinanceMarketDataAdapter().fetch_candles(
            asset, timeframe, start - pad, end + pad, limit=1000,
        )
    except Exception:
        return None, "Tijdelijk: historische EUR-candles zijn momenteel niet beschikbaar"
    if not candles or not any(c.period_start <= start <= c.period_end for c in candles) or not any(c.period_start <= end <= c.period_end for c in candles):
        return None, "De candlebron dekt entry en exit niet volledig"
    return {
        "source": "Binance spot", "provider_symbol": f"{symbol}EUR", "quote_currency": "EUR",
        "timeframe": timeframe, "coverage_start": candles[0].period_start.isoformat(),
        "coverage_end": candles[-1].period_end.isoformat(),
        "candles": [{"at": c.period_start.isoformat(), "end": c.period_end.isoformat(),
                     "open": c.open, "high": c.high, "low": c.low, "close": c.close}
                    for c in candles],
        "markers": [{"at": fill["at"], "price_eur": fill["price_eur"] or str(Decimal(fill["cash_eur"]) / Decimal(fill["qty"])),
                     "side": fill["side"], "ledger_id": fill["ledger_id"]}
                    for fill in review["fills"]],
    }, ""
