from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _default_logo_url(symbol: str, asset_class: str) -> str | None:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return None
    if asset_class == "crypto":
        return f"https://assets.coincap.io/assets/icons/{normalized.lower()}@2x.png"
    return None


DEFAULT_ASSET_CATALOG: dict[str, dict[str, Any]] = {
    "BTC": {
        "symbol": "BTC",
        "display_name": "Bitcoin",
        "asset_class": "crypto",
        "logo_url": _default_logo_url("BTC", "crypto"),
        "tradingview_symbol": "BINANCE:BTCUSDT",
        "coingecko_id": "bitcoin",
        "coincap_id": "bitcoin",
        "yahoo_symbol": "BTC-USD",
        "provider": "default",
    },
    "ETH": {
        "symbol": "ETH",
        "display_name": "Ethereum",
        "asset_class": "crypto",
        "logo_url": _default_logo_url("ETH", "crypto"),
        "tradingview_symbol": "BINANCE:ETHUSDT",
        "coingecko_id": "ethereum",
        "coincap_id": "ethereum",
        "yahoo_symbol": "ETH-USD",
        "provider": "default",
    },
    "SOL": {
        "symbol": "SOL",
        "display_name": "Solana",
        "asset_class": "crypto",
        "logo_url": _default_logo_url("SOL", "crypto"),
        "tradingview_symbol": "BINANCE:SOLUSDT",
        "coingecko_id": "solana",
        "coincap_id": "solana",
        "yahoo_symbol": "SOL-USD",
        "provider": "default",
    },
    "SPY": {
        "symbol": "SPY",
        "display_name": "SPDR S&P 500 ETF Trust",
        "asset_class": "etf",
        "logo_url": None,
        "tradingview_symbol": "AMEX:SPY",
        "coingecko_id": None,
        "coincap_id": None,
        "yahoo_symbol": "SPY",
        "provider": "default",
    },
    "QQQ": {
        "symbol": "QQQ",
        "display_name": "Invesco QQQ Trust",
        "asset_class": "etf",
        "logo_url": None,
        "tradingview_symbol": "NASDAQ:QQQ",
        "coingecko_id": None,
        "coincap_id": None,
        "yahoo_symbol": "QQQ",
        "provider": "default",
    },
    "AAPL": {
        "symbol": "AAPL",
        "display_name": "Apple Inc.",
        "asset_class": "stock",
        "logo_url": None,
        "tradingview_symbol": "NASDAQ:AAPL",
        "coingecko_id": None,
        "coincap_id": None,
        "yahoo_symbol": "AAPL",
        "provider": "default",
    },
    "MSFT": {
        "symbol": "MSFT",
        "display_name": "Microsoft Corporation",
        "asset_class": "stock",
        "logo_url": None,
        "tradingview_symbol": "NASDAQ:MSFT",
        "coingecko_id": None,
        "coincap_id": None,
        "yahoo_symbol": "MSFT",
        "provider": "default",
    },
}


class AssetCatalogService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_assets(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        normalized = list(dict.fromkeys(str(symbol or "").strip().upper() for symbol in symbols if str(symbol or "").strip()))
        if not normalized:
            return {}

        result = await self.session.execute(
            text(
                """
                SELECT
                    symbol,
                    display_name,
                    asset_class,
                    logo_url,
                    tradingview_symbol,
                    coingecko_id,
                    coincap_id,
                    yahoo_symbol,
                    provider,
                    is_active,
                    metadata
                FROM asset_catalog
                WHERE symbol = ANY(:symbols)
                """
            ),
            {"symbols": normalized},
        )
        db_rows = {
            str(row.symbol).upper(): {
                "symbol": str(row.symbol).upper(),
                "display_name": row.display_name,
                "asset_class": row.asset_class or "unknown",
                "logo_url": row.logo_url,
                "tradingview_symbol": row.tradingview_symbol,
                "coingecko_id": row.coingecko_id,
                "coincap_id": row.coincap_id,
                "yahoo_symbol": row.yahoo_symbol,
                "provider": row.provider or "database",
                "is_active": bool(row.is_active) if row.is_active is not None else True,
                "metadata": row.metadata or {},
            }
            for row in result.fetchall()
        }

        merged: dict[str, dict[str, Any]] = {}
        for symbol in normalized:
            default = DEFAULT_ASSET_CATALOG.get(symbol, self._fallback_asset(symbol))
            override = db_rows.get(symbol, {})
            asset_class = str(override.get("asset_class") or default.get("asset_class") or "unknown").lower()
            logo_url = override.get("logo_url") or default.get("logo_url") or _default_logo_url(symbol, asset_class)
            merged[symbol] = {
                **default,
                **override,
                "symbol": symbol,
                "asset_class": asset_class,
                "logo_url": logo_url,
            }
        return merged

    async def get_asset(self, symbol: str) -> dict[str, Any]:
        assets = await self.get_assets([symbol])
        return assets.get(str(symbol or "").strip().upper(), self._fallback_asset(symbol))

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
            "is_active": True,
            "metadata": {},
        }
