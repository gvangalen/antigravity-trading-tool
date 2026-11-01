from datetime import datetime, timezone
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_db
from backend.infrastructure.models import AssetCatalog, TradingMarket
from backend.schemas.market_provider_schema import AssetRecord
from backend.services.asset_catalog_service import AssetCatalogService
from backend.services.market_data_provider_registry import MarketDataProviderRegistry
from backend.services.trading_market_service import MarketUnavailable, TradingMarketService
from backend.services.market_data_ingestion_service import MarketDataIngestionService
from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
from backend.services.exact_market_workspace_service import ExactMarketWorkspaceService
from backend.utils.auth_utils import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/assets/chart-candles")
async def get_verified_chart_candles(
    tradingview_symbol: str = Query(..., min_length=3, max_length=120),
    interval: str = Query("D"),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Return provider candles for a catalogued instrument or exact trading pair.

    This read-only route supplies a chart when the third-party TradingView
    widget does not initialize. A requested symbol is never sent upstream
    without first resolving its verified catalog identity.
    """
    del current_user  # Authentication is required; candles themselves are public market data.
    normalized_symbol = tradingview_symbol.strip().upper()
    interval_map = {
        "15": ("15m", "15min"), "60": ("1h", "1h"),
        "240": ("4h", "4h"), "D": ("1d", "1day"),
        "W": ("1w", "1week"), "M": ("1M", "1month"),
        "3M": ("3M", "1month"),
    }
    if interval not in interval_map:
        raise HTTPException(422, "Ongeldige grafiekperiode.")

    market = (await session.execute(select(TradingMarket).where(
        TradingMarket.tradingview_symbol == normalized_symbol,
        TradingMarket.is_active.is_(True),
    ).limit(1))).scalars().first()
    if market is not None:
        catalog = (await session.execute(select(AssetCatalog).where(
            AssetCatalog.symbol == market.asset_symbol,
            AssetCatalog.is_active.is_(True),
        ).limit(1))).scalars().first()
        if catalog is None:
            raise HTTPException(404, "Handelspaar niet beschikbaar.")
        provider_name = market.provider
        asset = AssetRecord(
            symbol=market.asset_symbol, display_name=catalog.display_name,
            asset_class=catalog.asset_class, provider=provider_name,
            primary_provider=provider_name, provider_symbol=market.provider_symbol,
            quote_currency=market.quote_currency, exchange=market.venue,
            timezone=catalog.timezone or "UTC",
        )
    else:
        catalog = (await session.execute(select(AssetCatalog).where(
            AssetCatalog.tradingview_symbol == normalized_symbol,
            AssetCatalog.is_active.is_(True),
        ).limit(1))).scalars().first()
        if catalog is None or catalog.asset_class == "crypto":
            raise HTTPException(404, "Grafiekbron niet beschikbaar.")
        provider_name = catalog.primary_provider or catalog.provider
        asset = AssetRecord(
            symbol=catalog.symbol, display_name=catalog.display_name,
            asset_class=catalog.asset_class, provider=provider_name or "manual",
            primary_provider=provider_name or "manual",
            provider_symbol=catalog.provider_symbol or catalog.symbol,
            quote_currency=catalog.quote_currency, exchange=catalog.exchange,
            timezone=catalog.timezone or "UTC",
        )

    try:
        provider = MarketDataProviderRegistry().resolve_for_asset(asset)
        provider_interval = interval_map[interval][0 if asset.asset_class == "crypto" else 1]
        candles = await provider.fetch_candles(asset, provider_interval, limit=220)
    except Exception as exc:
        logger.warning("Chart candle source unavailable for %s: %s", normalized_symbol, type(exc).__name__)
        raise HTTPException(503, "Grafiekgegevens tijdelijk niet beschikbaar.") from exc

    verified_candles = [candle for candle in candles
                        if candle.provider_symbol.upper() == str(asset.provider_symbol).upper()]
    if interval == "3M" and asset.asset_class != "crypto":
        # Twelve Data supplies monthly bars; combine them into actual quarter bars.
        quarters = {}
        for candle in sorted(verified_candles, key=lambda item: item.period_start):
            key = (candle.period_start.year, (candle.period_start.month - 1) // 3)
            if key not in quarters:
                quarters[key] = {
                    "time": candle.period_start.isoformat(), "open": candle.open,
                    "high": candle.high, "low": candle.low, "close": candle.close,
                    "volume": candle.volume,
                }
            else:
                bar = quarters[key]
                bar["high"] = max(bar["high"], candle.high)
                bar["low"] = min(bar["low"], candle.low)
                bar["close"] = candle.close
                if candle.volume is not None:
                    bar["volume"] = (bar["volume"] or 0) + candle.volume
        response_candles = list(quarters.values())
    else:
        response_candles = [
            {"time": candle.period_start.isoformat(), "open": candle.open,
             "high": candle.high, "low": candle.low, "close": candle.close,
             "volume": candle.volume}
            for candle in verified_candles
        ]

    return {
        "symbol": normalized_symbol,
        "source": provider.provider_name,
        "quote_currency": asset.quote_currency,
        "interval": interval,
        "candles": response_candles,
    }


class AssetSearchItemResponse(BaseModel):
    symbol: str
    display_name: str
    asset_class: str
    exchange: str | None = None
    tradingview_symbol: str | None = None
    logo_url: str | None = None


class TradingMarketChoiceResponse(BaseModel):
    pair: str
    quote_currency: str
    status: str
    venue: str | None = None
    provider_symbol: str | None = None
    tradingview_symbol: str | None = None


class TradingMarketsResponse(BaseModel):
    asset_class: str
    markets: List[TradingMarketChoiceResponse]


@router.post("/assets/{symbol}/trading-markets/{quote_currency}/select")
async def select_crypto_trading_market(
    symbol: str,
    quote_currency: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    include_workspace: bool = False,
    market_period: str = "day",
    macro_period: str = "day",
    technical_period: str = "day",
    watchlist_symbols: str = "",
):
    """Verify and register a selected exact market before pair-scoped reads."""
    base = str(symbol or "").strip().upper()
    quote = str(quote_currency or "").strip().upper()
    asset = await AssetCatalogService(session).get_asset(base)
    if not asset or str(asset.get("asset_class") or "").lower() != "crypto":
        raise HTTPException(404, "Geen ondersteunde crypto-asset gevonden.")
    if quote not in {"EUR", "USDT"}:
        raise HTTPException(422, "Kies een ondersteund handelspaar.")
    if include_workspace and (
        any(period not in {"day", "week", "month", "quarter"}
            for period in (market_period, macro_period, technical_period))
        or len(watchlist_symbols) > 250
    ):
        raise HTTPException(422, "Ongeldige werkruimtekeuze.")
    try:
        market = await TradingMarketService(session).resolve(base, quote)
    except MarketUnavailable as exc:
        raise HTTPException(422, str(exc)) from exc
    await session.commit()
    snapshot = await MarketDataRepository(session).get_latest_exact_market_snapshot(market.id)
    observed_at = getattr(snapshot, "source_observed_at", None)

    def is_current(value: datetime | None) -> bool:
        if value is None:
            return False
        age = (datetime.now(timezone.utc) - value.replace(
            tzinfo=value.tzinfo or timezone.utc,
        )).total_seconds()
        return -30 <= age <= 120

    snapshot_status = "available" if is_current(observed_at) else "pending"
    if snapshot_status == "pending":
        try:
            ingested = await MarketDataIngestionService(session).ingest_exact_market_snapshot(market)
            captured_at = ingested.get("observed_at")
            parsed_at = datetime.fromisoformat(captured_at) if captured_at else None
            snapshot_status = "available" if is_current(parsed_at) else "pending"
        except Exception as exc:
            await session.rollback()
            logger.warning("Exact market snapshot pending after selection: pair=%s code=%s",
                           market.pair, type(exc).__name__)
    response = {
        "market_id": market.id,
        "pair": market.pair,
        "quote_currency": market.quote_currency,
        "provider_symbol": market.provider_symbol,
        "tradingview_symbol": market.tradingview_symbol,
        "snapshot_status": snapshot_status,
    }
    if include_workspace:
        workspace = await ExactMarketWorkspaceService(session).get(
            int(current_user["id"]), base, quote,
            periods={"market": market_period, "macro": macro_period,
                     "technical": technical_period},
            watchlist_symbols=[item.strip() for item in watchlist_symbols.split(",") if item.strip()],
        )
        if workspace is None:
            logger.error("Selected exact market missing in same-session workspace read: pair=%s id=%s",
                         market.pair, market.id)
            raise HTTPException(503, "selected_market_workspace_unavailable")
        response["workspace"] = workspace
    return response


@router.get("/assets/{symbol}/trading-markets", response_model=TradingMarketsResponse)
async def get_crypto_trading_markets(
    symbol: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    _ = current_user
    base = str(symbol or "").strip().upper()
    asset = await AssetCatalogService(session).get_asset(base)
    asset_class = str((asset or {}).get("asset_class") or "unknown").lower()
    if asset_class in {"stock", "etf"}:
        return TradingMarketsResponse(asset_class=asset_class, markets=[])
    if asset_class != "crypto":
        raise HTTPException(404, "Geen ondersteunde asset gevonden.")
    try:
        markets = await TradingMarketService(session).inspect_crypto_quotes(base)
        return TradingMarketsResponse(asset_class="crypto", markets=markets)
    except MarketUnavailable as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/assets/search", response_model=List[AssetSearchItemResponse])
async def search_assets(
    q: str = Query(default="", min_length=1),
    asset_classes: str = Query(default="crypto,stock"),
    limit: int = Query(default=8, ge=1, le=20),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    _ = current_user
    classes = [
        value.strip().lower()
        for value in str(asset_classes or "").split(",")
        if value.strip()
    ]

    results = await AssetCatalogService(session).search_assets(
        q,
        asset_classes=classes,
        limit=limit,
    )
    return [
        AssetSearchItemResponse(
            symbol=str(asset.get("symbol") or "").upper(),
            display_name=asset.get("display_name") or str(asset.get("symbol") or "").upper(),
            asset_class=str(asset.get("asset_class") or "unknown").lower(),
            exchange=asset.get("exchange"),
            tradingview_symbol=asset.get("tradingview_symbol"),
            logo_url=asset.get("logo_url"),
        )
        for asset in results
        if asset.get("symbol")
    ]
