from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.asset_catalog_repository import AssetCatalogRepository

logger = logging.getLogger(__name__)


def _search_score(asset: dict[str, Any], query: str) -> tuple[int, str]:
    symbol = str(asset.get("symbol") or "").upper()
    display_name = str(asset.get("display_name") or "")
    normalized_query = str(query or "").strip().upper()
    query_lower = normalized_query.lower()
    display_lower = display_name.lower()

    if symbol == normalized_query:
        return (0, symbol)
    if symbol.startswith(normalized_query):
        return (1, symbol)
    if display_lower.startswith(query_lower):
        return (2, symbol)
    if normalized_query in symbol:
        return (3, symbol)
    if query_lower in display_lower:
        return (4, symbol)
    return (5, symbol)


def _default_logo_url(symbol: str, asset_class: str) -> str | None:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return None
    if asset_class == "crypto":
        return f"https://assets.coincap.io/assets/icons/{normalized.lower()}@2x.png"
    return None


def _asset_defaults(
    *,
    symbol: str,
    display_name: str,
    asset_class: str,
    tradingview_symbol: str | None,
    yahoo_symbol: str | None,
    primary_provider: str,
    provider_symbol: str | None,
    exchange: str | None,
    market_region: str,
    timezone: str,
    base_currency: str | None,
    quote_currency: str | None,
    coingecko_id: str | None = None,
    coincap_id: str | None = None,
    entitlement_tier: str = "internal",
    refresh_policy: str | None = None,
    aliases: tuple[str, ...] = (),
    is_delayed: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = str(symbol or "").strip().upper()
    return {
        "symbol": normalized,
        "display_name": display_name,
        "aliases": list(aliases),
        "asset_class": asset_class,
        "logo_url": _default_logo_url(normalized, asset_class),
        "tradingview_symbol": tradingview_symbol,
        "coingecko_id": coingecko_id,
        "coincap_id": coincap_id,
        "yahoo_symbol": yahoo_symbol,
        "provider": primary_provider,
        "primary_provider": primary_provider,
        "fallback_provider": None,
        "provider_symbol": provider_symbol,
        "exchange": exchange,
        "market_region": market_region,
        "timezone": timezone,
        "base_currency": base_currency,
        "quote_currency": quote_currency,
        "entitlement_tier": entitlement_tier,
        "is_delayed": is_delayed,
        "refresh_policy": refresh_policy,
        "is_active": True,
        "metadata": metadata or {},
    }


DEFAULT_ASSET_CATALOG: dict[str, dict[str, Any]] = {
    "ADA": _asset_defaults(
        symbol="ADA",
        display_name="Cardano",
        asset_class="crypto",
        tradingview_symbol="BINANCE:ADAUSDT",
        yahoo_symbol="ADA-USD",
        primary_provider="binance",
        provider_symbol="ADAUSDT",
        exchange="BINANCE",
        market_region="global",
        timezone="UTC",
        base_currency="ADA",
        quote_currency="USDT",
        coingecko_id="cardano",
        coincap_id="cardano",
        refresh_policy="crypto_live_1m",
    ),
    "AVAX": _asset_defaults(
        symbol="AVAX",
        display_name="Avalanche",
        asset_class="crypto",
        tradingview_symbol="BINANCE:AVAXUSDT",
        yahoo_symbol="AVAX-USD",
        primary_provider="binance",
        provider_symbol="AVAXUSDT",
        exchange="BINANCE",
        market_region="global",
        timezone="UTC",
        base_currency="AVAX",
        quote_currency="USDT",
        coingecko_id="avalanche-2",
        coincap_id="avalanche",
        refresh_policy="crypto_live_1m",
    ),
    "BTC": _asset_defaults(
        symbol="BTC",
        display_name="Bitcoin",
        asset_class="crypto",
        tradingview_symbol="BINANCE:BTCUSDT",
        yahoo_symbol="BTC-USD",
        primary_provider="binance",
        provider_symbol="BTCUSDT",
        exchange="BINANCE",
        market_region="global",
        timezone="UTC",
        base_currency="BTC",
        quote_currency="USDT",
        coingecko_id="bitcoin",
        coincap_id="bitcoin",
        refresh_policy="crypto_live_1m",
    ),
    "DOGE": _asset_defaults(
        symbol="DOGE",
        display_name="Dogecoin",
        asset_class="crypto",
        tradingview_symbol="BINANCE:DOGEUSDT",
        yahoo_symbol="DOGE-USD",
        primary_provider="binance",
        provider_symbol="DOGEUSDT",
        exchange="BINANCE",
        market_region="global",
        timezone="UTC",
        base_currency="DOGE",
        quote_currency="USDT",
        coingecko_id="dogecoin",
        coincap_id="dogecoin",
        refresh_policy="crypto_live_1m",
    ),
    "LTC": _asset_defaults(
        symbol="LTC",
        display_name="Litecoin",
        asset_class="crypto",
        tradingview_symbol="BINANCE:LTCUSDT",
        yahoo_symbol="LTC-USD",
        primary_provider="binance",
        provider_symbol="LTCUSDT",
        exchange="BINANCE",
        market_region="global",
        timezone="UTC",
        base_currency="LTC",
        quote_currency="USDT",
        coingecko_id="litecoin",
        coincap_id="litecoin",
        refresh_policy="crypto_live_1m",
    ),
    "DOT": _asset_defaults(
        symbol="DOT",
        display_name="Polkadot",
        asset_class="crypto",
        tradingview_symbol="BINANCE:DOTUSDT",
        yahoo_symbol="DOT-USD",
        primary_provider="binance",
        provider_symbol="DOTUSDT",
        exchange="BINANCE",
        market_region="global",
        timezone="UTC",
        base_currency="DOT",
        quote_currency="USDT",
        coingecko_id="polkadot",
        coincap_id="polkadot",
        refresh_policy="crypto_live_1m",
    ),
    "ATOM": _asset_defaults(
        symbol="ATOM",
        display_name="Cosmos",
        asset_class="crypto",
        tradingview_symbol="BINANCE:ATOMUSDT",
        yahoo_symbol="ATOM-USD",
        primary_provider="binance",
        provider_symbol="ATOMUSDT",
        exchange="BINANCE",
        market_region="global",
        timezone="UTC",
        base_currency="ATOM",
        quote_currency="USDT",
        coingecko_id="cosmos",
        refresh_policy="crypto_live_1m",
    ),
    "NEAR": _asset_defaults(
        symbol="NEAR",
        display_name="NEAR Protocol",
        asset_class="crypto",
        tradingview_symbol="BINANCE:NEARUSDT",
        yahoo_symbol="NEAR-USD",
        primary_provider="binance",
        provider_symbol="NEARUSDT",
        exchange="BINANCE",
        market_region="global",
        timezone="UTC",
        base_currency="NEAR",
        quote_currency="USDT",
        coingecko_id="near",
        aliases=("Near",),
        refresh_policy="crypto_live_1m",
    ),
    "POL": _asset_defaults(
        symbol="POL", display_name="Polygon", asset_class="crypto",
        tradingview_symbol="BINANCE:POLUSDT", yahoo_symbol="POL-USD",
        primary_provider="binance", provider_symbol="POLUSDT", exchange="BINANCE",
        market_region="global", timezone="UTC", base_currency="POL", quote_currency="USDT",
        coingecko_id="polygon-ecosystem-token", refresh_policy="crypto_live_1m",
    ),
    "UNI": _asset_defaults(
        symbol="UNI", display_name="Uniswap", asset_class="crypto",
        tradingview_symbol="BINANCE:UNIUSDT", yahoo_symbol="UNI-USD",
        primary_provider="binance", provider_symbol="UNIUSDT", exchange="BINANCE",
        market_region="global", timezone="UTC", base_currency="UNI", quote_currency="USDT",
        coingecko_id="uniswap", refresh_policy="crypto_live_1m",
    ),
    "ETH": _asset_defaults(
        symbol="ETH",
        display_name="Ethereum",
        asset_class="crypto",
        tradingview_symbol="BINANCE:ETHUSDT",
        yahoo_symbol="ETH-USD",
        primary_provider="binance",
        provider_symbol="ETHUSDT",
        exchange="BINANCE",
        market_region="global",
        timezone="UTC",
        base_currency="ETH",
        quote_currency="USDT",
        coingecko_id="ethereum",
        coincap_id="ethereum",
        aliases=("Ether",),
        refresh_policy="crypto_live_1m",
    ),
    "XLM": _asset_defaults(
        symbol="XLM",
        display_name="Stellar",
        asset_class="crypto",
        tradingview_symbol="BINANCE:XLMUSDT",
        yahoo_symbol="XLM-USD",
        primary_provider="binance",
        provider_symbol="XLMUSDT",
        exchange="BINANCE",
        market_region="global",
        timezone="UTC",
        base_currency="XLM",
        quote_currency="USDT",
        coingecko_id="stellar",
        coincap_id="stellar",
        refresh_policy="crypto_live_1m",
    ),
    "SOL": _asset_defaults(
        symbol="SOL",
        display_name="Solana",
        asset_class="crypto",
        tradingview_symbol="BINANCE:SOLUSDT",
        yahoo_symbol="SOL-USD",
        primary_provider="binance",
        provider_symbol="SOLUSDT",
        exchange="BINANCE",
        market_region="global",
        timezone="UTC",
        base_currency="SOL",
        quote_currency="USDT",
        coingecko_id="solana",
        coincap_id="solana",
        refresh_policy="crypto_live_1m",
    ),
    "XRP": _asset_defaults(
        symbol="XRP",
        display_name="XRP",
        asset_class="crypto",
        tradingview_symbol="BINANCE:XRPUSDT",
        yahoo_symbol="XRP-USD",
        primary_provider="binance",
        provider_symbol="XRPUSDT",
        exchange="BINANCE",
        market_region="global",
        timezone="UTC",
        base_currency="XRP",
        quote_currency="USDT",
        refresh_policy="crypto_live_1m",
    ),
    "LINK": _asset_defaults(
        symbol="LINK",
        display_name="Chainlink",
        asset_class="crypto",
        tradingview_symbol="BINANCE:LINKUSDT",
        yahoo_symbol="LINK-USD",
        primary_provider="binance",
        provider_symbol="LINKUSDT",
        exchange="BINANCE",
        market_region="global",
        timezone="UTC",
        base_currency="LINK",
        quote_currency="USDT",
        refresh_policy="crypto_live_1m",
    ),
    "MSTR": _asset_defaults(
        symbol="MSTR",
        display_name="Strategy Inc.",
        asset_class="stock",
        tradingview_symbol="NASDAQ:MSTR",
        yahoo_symbol="MSTR",
        primary_provider="twelve_data",
        provider_symbol="MSTR",
        exchange="NASDAQ",
        market_region="us",
        timezone="America/New_York",
        base_currency=None,
        quote_currency="USD",
        refresh_policy="securities_live_5m",
    ),
    "COIN": _asset_defaults(
        symbol="COIN",
        display_name="Coinbase Global, Inc.",
        asset_class="stock",
        tradingview_symbol="NASDAQ:COIN",
        yahoo_symbol="COIN",
        primary_provider="twelve_data",
        provider_symbol="COIN",
        exchange="NASDAQ",
        market_region="us",
        timezone="America/New_York",
        base_currency=None,
        quote_currency="USD",
        refresh_policy="securities_live_5m",
    ),
    "MARA": _asset_defaults(
        symbol="MARA",
        display_name="MARA Holdings, Inc.",
        asset_class="stock",
        tradingview_symbol="NASDAQ:MARA",
        yahoo_symbol="MARA",
        primary_provider="twelve_data",
        provider_symbol="MARA",
        exchange="NASDAQ",
        market_region="us",
        timezone="America/New_York",
        base_currency=None,
        quote_currency="USD",
        refresh_policy="securities_live_5m",
    ),
    "RIOT": _asset_defaults(
        symbol="RIOT",
        display_name="Riot Platforms, Inc.",
        asset_class="stock",
        tradingview_symbol="NASDAQ:RIOT",
        yahoo_symbol="RIOT",
        primary_provider="twelve_data",
        provider_symbol="RIOT",
        exchange="NASDAQ",
        market_region="us",
        timezone="America/New_York",
        base_currency=None,
        quote_currency="USD",
        refresh_policy="securities_live_5m",
    ),
    "CLSK": _asset_defaults(
        symbol="CLSK",
        display_name="CleanSpark, Inc.",
        asset_class="stock",
        tradingview_symbol="NASDAQ:CLSK",
        yahoo_symbol="CLSK",
        primary_provider="twelve_data",
        provider_symbol="CLSK",
        exchange="NASDAQ",
        market_region="us",
        timezone="America/New_York",
        base_currency=None,
        quote_currency="USD",
        refresh_policy="securities_live_5m",
    ),
    "HUT": _asset_defaults(
        symbol="HUT",
        display_name="Hut 8 Corp.",
        asset_class="stock",
        tradingview_symbol="NASDAQ:HUT",
        yahoo_symbol="HUT",
        primary_provider="twelve_data",
        provider_symbol="HUT",
        exchange="NASDAQ",
        market_region="us",
        timezone="America/New_York",
        base_currency=None,
        quote_currency="USD",
        refresh_policy="securities_live_5m",
    ),
    "BTDR": _asset_defaults(
        symbol="BTDR",
        display_name="Bitdeer Technologies Group",
        asset_class="stock",
        tradingview_symbol="NASDAQ:BTDR",
        yahoo_symbol="BTDR",
        primary_provider="twelve_data",
        provider_symbol="BTDR",
        exchange="NASDAQ",
        market_region="us",
        timezone="America/New_York",
        base_currency=None,
        quote_currency="USD",
        refresh_policy="securities_live_5m",
    ),
    "WULF": _asset_defaults(
        symbol="WULF",
        display_name="TeraWulf Inc.",
        asset_class="stock",
        tradingview_symbol="NASDAQ:WULF",
        yahoo_symbol="WULF",
        primary_provider="twelve_data",
        provider_symbol="WULF",
        exchange="NASDAQ",
        market_region="us",
        timezone="America/New_York",
        base_currency=None,
        quote_currency="USD",
        refresh_policy="securities_live_5m",
    ),
    "CORZ": _asset_defaults(
        symbol="CORZ",
        display_name="Core Scientific, Inc.",
        asset_class="stock",
        tradingview_symbol="NASDAQ:CORZ",
        yahoo_symbol="CORZ",
        primary_provider="twelve_data",
        provider_symbol="CORZ",
        exchange="NASDAQ",
        market_region="us",
        timezone="America/New_York",
        base_currency=None,
        quote_currency="USD",
        refresh_policy="securities_live_5m",
    ),
    "SPY": _asset_defaults(
        symbol="SPY",
        display_name="SPDR S&P 500 ETF Trust",
        asset_class="etf",
        tradingview_symbol="AMEX:SPY",
        yahoo_symbol="SPY",
        primary_provider="twelve_data",
        provider_symbol="SPY",
        exchange="AMEX",
        market_region="us",
        timezone="America/New_York",
        base_currency=None,
        quote_currency="USD",
        refresh_policy="securities_live_5m",
    ),
    "QQQ": _asset_defaults(
        symbol="QQQ",
        display_name="Invesco QQQ Trust",
        asset_class="etf",
        tradingview_symbol="NASDAQ:QQQ",
        yahoo_symbol="QQQ",
        primary_provider="twelve_data",
        provider_symbol="QQQ",
        exchange="NASDAQ",
        market_region="us",
        timezone="America/New_York",
        base_currency=None,
        quote_currency="USD",
        refresh_policy="securities_live_5m",
    ),
    "IBIT": _asset_defaults(
        symbol="IBIT",
        display_name="iShares Bitcoin Trust ETF",
        asset_class="etf",
        tradingview_symbol="NASDAQ:IBIT",
        yahoo_symbol="IBIT",
        primary_provider="twelve_data",
        provider_symbol="IBIT",
        exchange="NASDAQ",
        market_region="us",
        timezone="America/New_York",
        base_currency=None,
        quote_currency="USD",
        refresh_policy="securities_live_5m",
    ),
    "FBTC": _asset_defaults(
        symbol="FBTC",
        display_name="Fidelity Wise Origin Bitcoin Fund",
        asset_class="etf",
        tradingview_symbol="AMEX:FBTC",
        yahoo_symbol="FBTC",
        primary_provider="twelve_data",
        provider_symbol="FBTC",
        exchange="AMEX",
        market_region="us",
        timezone="America/New_York",
        base_currency=None,
        quote_currency="USD",
        refresh_policy="securities_live_5m",
    ),
    "GLD": _asset_defaults(
        symbol="GLD",
        display_name="SPDR Gold Shares",
        asset_class="etf",
        tradingview_symbol="AMEX:GLD",
        yahoo_symbol="GLD",
        primary_provider="twelve_data",
        provider_symbol="GLD",
        exchange="AMEX",
        market_region="us",
        timezone="America/New_York",
        base_currency=None,
        quote_currency="USD",
        refresh_policy="securities_live_5m",
    ),
    "XAU": _asset_defaults(
        symbol="XAU",
        display_name="Gold",
        aliases=("goud", "or", "gold spot", "xauusd", "xau/usd"),
        asset_class="commodity",
        tradingview_symbol="OANDA:XAUUSD",
        yahoo_symbol="GC=F",
        primary_provider="twelve_data",
        provider_symbol="XAU/USD",
        exchange="COMMODITY",
        market_region="global",
        timezone="UTC",
        base_currency="XAU",
        quote_currency="USD",
        refresh_policy="commodities_live_5m",
    ),
    "SPX": _asset_defaults(
        symbol="SPX",
        display_name="S&P 500 Index",
        asset_class="index",
        tradingview_symbol="SP:SPX",
        yahoo_symbol="^GSPC",
        primary_provider="twelve_data",
        provider_symbol="SPX",
        exchange="INDEX",
        market_region="us",
        timezone="America/New_York",
        base_currency=None,
        quote_currency="USD",
        refresh_policy="securities_live_5m",
        is_delayed=True,
    ),
    "NDX": _asset_defaults(
        symbol="NDX",
        display_name="Nasdaq-100 Index",
        asset_class="index",
        tradingview_symbol="NASDAQ:NDX",
        yahoo_symbol="^NDX",
        primary_provider="twelve_data",
        provider_symbol="NDX",
        exchange="INDEX",
        market_region="us",
        timezone="America/New_York",
        base_currency=None,
        quote_currency="USD",
        refresh_policy="securities_live_5m",
        is_delayed=True,
    ),
    "VIX": _asset_defaults(
        symbol="VIX",
        display_name="CBOE Volatility Index",
        asset_class="index",
        tradingview_symbol="CBOE:VIX",
        yahoo_symbol="^VIX",
        primary_provider="twelve_data",
        provider_symbol="VIX",
        exchange="CBOE",
        market_region="us",
        timezone="America/New_York",
        base_currency=None,
        quote_currency="USD",
        refresh_policy="securities_live_5m",
        is_delayed=True,
    ),
    "DXY": _asset_defaults(
        symbol="DXY",
        display_name="US Dollar Index",
        asset_class="index",
        tradingview_symbol="TVC:DXY",
        yahoo_symbol="DX-Y.NYB",
        primary_provider="twelve_data",
        provider_symbol="DXY",
        exchange="ICE",
        market_region="us",
        timezone="America/New_York",
        base_currency=None,
        quote_currency="USD",
        refresh_policy="securities_live_5m",
        is_delayed=True,
    ),
    "AAPL": _asset_defaults(
        symbol="AAPL",
        display_name="Apple Inc.",
        asset_class="stock",
        tradingview_symbol="NASDAQ:AAPL",
        yahoo_symbol="AAPL",
        primary_provider="twelve_data",
        provider_symbol="AAPL",
        exchange="NASDAQ",
        market_region="us",
        timezone="America/New_York",
        base_currency=None,
        quote_currency="USD",
        aliases=("Apple",),
        refresh_policy="securities_live_5m",
    ),
    "MSFT": _asset_defaults(
        symbol="MSFT",
        display_name="Microsoft Corporation",
        asset_class="stock",
        tradingview_symbol="NASDAQ:MSFT",
        yahoo_symbol="MSFT",
        primary_provider="twelve_data",
        provider_symbol="MSFT",
        exchange="NASDAQ",
        market_region="us",
        timezone="America/New_York",
        base_currency=None,
        quote_currency="USD",
        aliases=("Microsoft",),
        refresh_policy="securities_live_5m",
    ),
}


def resolve_catalog_symbol(value: object) -> str | None:
    """Resolve a user-facing catalog symbol or display name to one symbol.

    FINN uses this only for explicit user input.  It deliberately does not
    infer a symbol from a workspace, asset class, or another user's records.
    """
    normalized = str(value or "").strip().casefold()
    if not normalized:
        return None
    for symbol, asset in DEFAULT_ASSET_CATALOG.items():
        candidates = {
            symbol.casefold(), str(asset.get("display_name") or "").casefold(),
            *(str(alias).casefold() for alias in asset.get("aliases") or ()),
        }
        if normalized in candidates:
            return symbol
    return None


def resolve_catalog_symbol_in_text(value: object) -> str | None:
    """Resolve one catalog asset from a natural-language token or compound.

    Natural-language compounds such as ``bitcoinindicatoren`` still contain
    an explicit catalog display name.  This helper deliberately accepts only
    a leading display name or alias (never a short ticker prefix), preventing
    arbitrary identifiers from being mistaken for assets.
    """
    normalized = str(value or "").strip().casefold()
    if not normalized:
        return None
    exact = resolve_catalog_symbol(normalized)
    if exact:
        return exact
    for symbol, asset in DEFAULT_ASSET_CATALOG.items():
        names = (str(asset.get("display_name") or ""), *(str(alias) for alias in asset.get("aliases") or ()))
        for name in names:
            candidate = name.casefold().strip()
            if len(candidate) >= 4 and re.match(rf"^{re.escape(candidate)}[a-z]+$", normalized):
                return symbol
    return None


class AssetCatalogService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = AssetCatalogRepository(session)

    async def get_assets(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        normalized = list(dict.fromkeys(str(symbol or "").strip().upper() for symbol in symbols if str(symbol or "").strip()))
        if not normalized:
            return {}

        try:
            db_rows = await self.repository.get_assets(normalized)
        except Exception as exc:
            logger.exception("Asset catalog query failed; rolling back before defaults fallback")
            await self._rollback_after_query_failure()
            db_rows = {}

        merged: dict[str, dict[str, Any]] = {}
        for symbol in normalized:
            default = DEFAULT_ASSET_CATALOG.get(symbol, self._fallback_asset(symbol))
            override = db_rows.get(symbol, {})
            asset_class = str(override.get("asset_class") or default.get("asset_class") or "unknown").lower()
            logo_url = override.get("logo_url") or default.get("logo_url") or _default_logo_url(symbol, asset_class)
            primary_provider = (
                override.get("primary_provider")
                or override.get("provider")
                or default.get("primary_provider")
                or default.get("provider")
                or "manual"
            )
            merged[symbol] = {
                **default,
                **override,
                "symbol": symbol,
                "asset_class": asset_class,
                "logo_url": logo_url,
                "provider": primary_provider,
                "primary_provider": primary_provider,
                "fallback_provider": override.get("fallback_provider") or default.get("fallback_provider"),
                "provider_symbol": override.get("provider_symbol") or default.get("provider_symbol"),
                "exchange": override.get("exchange") or default.get("exchange"),
                "market_region": override.get("market_region") or default.get("market_region") or "global",
                "timezone": override.get("timezone") or default.get("timezone") or "UTC",
                "base_currency": override.get("base_currency") or default.get("base_currency"),
                "quote_currency": override.get("quote_currency") or default.get("quote_currency"),
                "entitlement_tier": override.get("entitlement_tier") or default.get("entitlement_tier") or "internal",
                "is_delayed": bool(override.get("is_delayed") if override.get("is_delayed") is not None else default.get("is_delayed", False)),
                "refresh_policy": override.get("refresh_policy") or default.get("refresh_policy"),
                "is_active": bool(override.get("is_active") if override.get("is_active") is not None else default.get("is_active", True)),
                "metadata": override.get("metadata") or default.get("metadata") or {},
            }
        return merged

    async def _rollback_after_query_failure(self) -> None:
        rollback = getattr(self.session, "rollback", None)
        if rollback is None:
            return
        try:
            await rollback()
        except Exception:
            logger.exception("Asset catalog rollback failed after query failure")

    async def get_asset(self, symbol: str) -> dict[str, Any]:
        assets = await self.get_assets([symbol])
        return assets.get(str(symbol or "").strip().upper(), self._fallback_asset(symbol))

    async def search_assets(
        self,
        query: str,
        asset_classes: list[str] | None = None,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        normalized_query = str(query or "").strip()
        if not normalized_query:
            return []

        normalized_classes = [
            str(asset_class or "").strip().lower()
            for asset_class in (asset_classes or [])
            if str(asset_class or "").strip()
        ]

        try:
            db_rows = await self.repository.search_assets(normalized_query, normalized_classes, limit)
        except Exception as exc:
            logger.warning("Asset catalog search failed; falling back to defaults: %s", exc)
            db_rows = []

        merged: dict[str, dict[str, Any]] = {}
        for row in db_rows:
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            merged[symbol] = (await self.get_assets([symbol])).get(symbol, self._fallback_asset(symbol))

        query_lower = normalized_query.lower()
        for symbol, asset in DEFAULT_ASSET_CATALOG.items():
            asset_class = str(asset.get("asset_class") or "").strip().lower()
            if normalized_classes and asset_class not in normalized_classes:
                continue
            display_name = str(asset.get("display_name") or "")
            if query_lower not in symbol.lower() and query_lower not in display_name.lower():
                continue
            merged.setdefault(symbol, asset)

        ranked = sorted(merged.values(), key=lambda asset: _search_score(asset, normalized_query))
        return ranked[:limit]

    def _fallback_asset(self, symbol: str) -> dict[str, Any]:
        normalized = str(symbol or "").strip().upper()
        asset_class = "crypto" if normalized.isalpha() and len(normalized) <= 5 else "unknown"
        return {
            "symbol": normalized,
            "display_name": normalized or "Unknown asset",
            "asset_class": asset_class,
            "logo_url": _default_logo_url(normalized, asset_class),
            "tradingview_symbol": None,
            "coingecko_id": None,
            "coincap_id": None,
            "yahoo_symbol": None,
            "provider": "fallback",
            "primary_provider": "fallback",
            "fallback_provider": None,
            "provider_symbol": None,
            "exchange": None,
            "market_region": "global",
            "timezone": "UTC",
            "base_currency": normalized if asset_class == "crypto" else None,
            "quote_currency": "USDT" if asset_class == "crypto" else None,
            "entitlement_tier": "internal",
            "is_delayed": False,
            "refresh_policy": None,
            "is_active": True,
            "metadata": {},
        }
