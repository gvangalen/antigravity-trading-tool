"""Resolve an exact traded market; never infer it from a base asset or FX rate."""

from __future__ import annotations

import re
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


_ASSET_CODE = re.compile(r"^[A-Z0-9]{2,12}$")
_QUOTE_CODE = re.compile(r"^[A-Z0-9]{2,12}$")
_BINANCE_EXCHANGE_INFO = "https://api.binance.com/api/v3/exchangeInfo"


class MarketUnavailable(ValueError):
    """The requested exact pair has no verified tradable market."""


@dataclass(frozen=True)
class TradingMarket:
    id: int
    asset_symbol: str
    quote_currency: str
    venue: str
    provider: str
    provider_symbol: str
    tradingview_symbol: str
    source_verified_at: datetime

    @property
    def pair(self) -> str:
        return f"{self.asset_symbol}/{self.quote_currency}"


def normalize_pair(base: str, quote: str) -> tuple[str, str]:
    base = str(base or "").strip().upper()
    quote = str(quote or "").strip().upper()
    if not _ASSET_CODE.fullmatch(base) or not _QUOTE_CODE.fullmatch(quote):
        raise MarketUnavailable("Ongeldig handelspaar.")
    if base == quote:
        raise MarketUnavailable("De basis- en koersvaluta moeten verschillen.")
    return base, quote


def verify_binance_pair(payload: dict, base: str, quote: str) -> str:
    """Return only an exact, currently tradable spot symbol from exchangeInfo."""
    base, quote = normalize_pair(base, quote)
    candidates = payload.get("symbols") if isinstance(payload, dict) else None
    if not isinstance(candidates, list) or len(candidates) != 1:
        raise MarketUnavailable(f"{base}/{quote} is niet als exact handelspaar bevestigd.")
    market = candidates[0]
    expected_symbol = f"{base}{quote}"
    if (not isinstance(market, dict)
            or str(market.get("symbol") or "").upper() != expected_symbol
            or str(market.get("baseAsset") or "").upper() != base
            or str(market.get("quoteAsset") or "").upper() != quote
            or str(market.get("status") or "").upper() != "TRADING"
            or market.get("isSpotTradingAllowed") is not True):
        raise MarketUnavailable(f"{base}/{quote} is niet als actief spotpaar bevestigd.")
    return expected_symbol


class TradingMarketService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def inspect_crypto_quotes(self, base: str, quotes: tuple[str, ...] = ("EUR", "USDT")) -> list[dict]:
        """Read-only choice list; a provider outage never becomes an unsupported pair.

        No market row or price observation is written while showing choices.
        The exact pair is checked again when a user confirms a plan.
        """
        base = str(base or "").strip().upper()
        if not _ASSET_CODE.fullmatch(base):
            raise MarketUnavailable("Ongeldige asset.")

        async with httpx.AsyncClient(timeout=10.0) as client:
            async def inspect(quote: str) -> dict:
                _, quote = normalize_pair(base, quote)
                pair = f"{base}/{quote}"
                provider_symbol = f"{base}{quote}"
                try:
                    response = await client.get(_BINANCE_EXCHANGE_INFO,
                                                params={"symbol": provider_symbol})
                    if response.status_code in {400, 404}:
                        return {"pair": pair, "quote_currency": quote,
                                "status": "unavailable"}
                    response.raise_for_status()
                    verified_symbol = verify_binance_pair(response.json(), base, quote)
                except MarketUnavailable:
                    return {"pair": pair, "quote_currency": quote,
                            "status": "unavailable"}
                except (httpx.HTTPError, ValueError):
                    return {"pair": pair, "quote_currency": quote,
                            "status": "verification_unavailable"}
                return {"pair": pair, "quote_currency": quote,
                        "status": "available", "venue": "BINANCE",
                        "provider_symbol": verified_symbol,
                        "tradingview_symbol": f"BINANCE:{verified_symbol}"}

            return list(await asyncio.gather(*(inspect(quote) for quote in quotes)))

    async def _stored(self, base: str, quote: str) -> TradingMarket | None:
        result = await self.session.execute(text("""
            SELECT id, asset_symbol, quote_currency, venue, provider,
                   provider_symbol, tradingview_symbol, source_verified_at
            FROM trading_markets
            WHERE asset_symbol=:base AND quote_currency=:quote
              AND venue='BINANCE' AND is_active=TRUE
            LIMIT 1
        """), {"base": base, "quote": quote})
        row = result.mappings().first()
        return TradingMarket(**row) if row else None

    async def resolve(self, base: str, quote: str, *, verify_current: bool = False) -> TradingMarket:
        """Find or verify a pair; provider errors never select another quote."""
        base, quote = normalize_pair(base, quote)
        saved = await self._stored(base, quote)
        if saved and not verify_current:
            return saved
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(_BINANCE_EXCHANGE_INFO,
                                            params={"symbol": f"{base}{quote}"})
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MarketUnavailable(
                f"De beschikbaarheid van {base}/{quote} kan nu niet worden gecontroleerd."
            ) from exc
        provider_symbol = verify_binance_pair(payload, base, quote)
        verified_at = datetime.now(timezone.utc)
        result = await self.session.execute(text("""
            INSERT INTO trading_markets (
                asset_symbol, quote_currency, venue, provider, provider_symbol,
                tradingview_symbol, source_verified_at
            )
            SELECT :base, :quote, 'BINANCE', 'binance', :provider_symbol,
                   :tradingview_symbol, :verified_at
            WHERE EXISTS (SELECT 1 FROM asset_catalog
                          WHERE symbol=:base AND asset_class='crypto' AND is_active=TRUE)
            ON CONFLICT (asset_symbol, quote_currency, venue) DO UPDATE
            SET source_verified_at=EXCLUDED.source_verified_at,
                is_active=TRUE
            WHERE trading_markets.provider_symbol=EXCLUDED.provider_symbol
              AND trading_markets.provider=EXCLUDED.provider
              AND trading_markets.tradingview_symbol=EXCLUDED.tradingview_symbol
            RETURNING id
        """), {
            "base": base, "quote": quote,
            "provider_symbol": provider_symbol,
            "tradingview_symbol": f"BINANCE:{provider_symbol}",
            "verified_at": verified_at,
        })
        if result.scalar_one_or_none() is None:
            raise MarketUnavailable(f"{base}/{quote} is niet beschikbaar in de assetcatalogus.")
        market = await self._stored(base, quote)
        if market is None:
            raise MarketUnavailable(f"{base}/{quote} is niet opgeslagen.")
        return market
