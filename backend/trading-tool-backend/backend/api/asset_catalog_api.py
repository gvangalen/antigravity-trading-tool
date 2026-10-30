from datetime import datetime, timezone
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_db
from backend.services.asset_catalog_service import AssetCatalogService
from backend.services.trading_market_service import MarketUnavailable, TradingMarketService
from backend.services.market_data_ingestion_service import MarketDataIngestionService
from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
from backend.services.exact_market_workspace_service import ExactMarketWorkspaceService
from backend.utils.auth_utils import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


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
