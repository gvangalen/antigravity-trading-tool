import logging
from typing import List
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_, asc

from backend.infrastructure.database import get_db
from backend.services.asset_catalog_service import AssetCatalogService
from backend.utils.auth_utils import get_current_user
from backend.infrastructure.models import Watchlist, TradingMarket
from backend.services.indicator_score_refresh_service import queue_exact_market_refresh

logger = logging.getLogger(__name__)
router = APIRouter()


class WatchlistItemResponse(BaseModel):
    symbol: str
    market_id: int | None = None
    quote_currency: str | None = None
    display_name: str
    asset_class: str
    logo_url: str | None = None
    tradingview_symbol: str | None = None


class WatchlistAddRequest(BaseModel):
    symbol: str
    market_id: int | None = None
    asset_class: str | None = None
    display_name: str | None = None
    tradingview_symbol: str | None = None


async def _serialize_watchlist(
    session: AsyncSession,
    user_id: int,
) -> list[WatchlistItemResponse]:
    stmt = (
        select(Watchlist, TradingMarket)
        .outerjoin(TradingMarket, Watchlist.market_id == TradingMarket.id)
        .where(Watchlist.user_id == user_id)
        .order_by(asc(Watchlist.created_at), asc(Watchlist.id))
    )
    result = await session.execute(stmt)
    entries = result.all()
    symbols = [str(item.symbol or "").upper() for item, _ in entries if item.symbol]
    if not symbols:
        return []

    asset_map = await AssetCatalogService(session).get_assets(symbols)
    return [
        WatchlistItemResponse(
            symbol=str(item.symbol).upper(),
            market_id=item.market_id,
            quote_currency=market.quote_currency if market else None,
            display_name=asset_map.get(item.symbol, {}).get("display_name") or item.symbol,
            asset_class=asset_map.get(item.symbol, {}).get("asset_class") or "crypto",
            logo_url=asset_map.get(item.symbol, {}).get("logo_url"),
            tradingview_symbol=market.tradingview_symbol if market else asset_map.get(item.symbol, {}).get("tradingview_symbol"),
        )
        for item, market in entries
    ]


@router.get("/watchlist", response_model=List[WatchlistItemResponse])
async def get_watchlist(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    user_id = current_user["id"]
    return await _serialize_watchlist(session, int(user_id))

@router.post("/watchlist")
async def add_to_watchlist(
    payload: WatchlistAddRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    symbol = (payload.symbol or "").strip().upper()
    if not symbol:
        raise HTTPException(400, "Symbol is verplicht")
    
    user_id = current_user["id"]
    market = None
    if payload.market_id is not None:
        market = (await session.execute(select(TradingMarket).where(
            TradingMarket.id == payload.market_id,
            TradingMarket.asset_symbol == symbol,
            TradingMarket.is_active.is_(True),
            TradingMarket.venue == "BINANCE",
        ))).scalar_one_or_none()
        if market is None:
            raise HTTPException(422, "Handelspaar is niet geverifieerd")

    # Check if already exists
    stmt = select(Watchlist).where(and_(Watchlist.user_id == user_id, Watchlist.symbol == symbol,
        Watchlist.market_id == payload.market_id if market else Watchlist.market_id.is_(None)))
    existing = await session.execute(stmt)
    if existing.scalars().first():
        return {"message": f"{symbol} staat al in je watchlist", "symbol": symbol}

    if market is not None:
        legacy = (await session.execute(select(Watchlist).where(
            Watchlist.user_id == user_id,
            Watchlist.symbol == symbol,
            Watchlist.market_id.is_(None),
        ))).scalar_one_or_none()
        if legacy is not None:
            legacy.market_id = market.id
            await session.commit()
            queue_exact_market_refresh(int(market.id))
            return {"message": f"{symbol}/{market.quote_currency} toegevoegd aan watchlist", "symbol": symbol}

    new_item = Watchlist(user_id=user_id, symbol=symbol, market_id=payload.market_id)
    session.add(new_item)
    await session.commit()
    if market is not None:
        queue_exact_market_refresh(int(market.id))
    return {"message": f"{symbol} toegevoegd aan watchlist", "symbol": symbol}

@router.delete("/watchlist/{symbol}")
async def remove_from_watchlist(
    symbol: str,
    market_id: int | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    user_id = current_user["id"]
    symbol = symbol.upper()
    
    if market_id is None:
        matching = (await session.execute(select(Watchlist.id).where(
            Watchlist.user_id == user_id, Watchlist.symbol == symbol,
        ))).scalars().all()
        if len(matching) > 1:
            raise HTTPException(409, "Kies welk handelspaar je wilt verwijderen")
        if not matching:
            raise HTTPException(404, f"{symbol} niet gevonden in je watchlist")
        stmt = delete(Watchlist).where(Watchlist.id == matching[0], Watchlist.user_id == user_id)
    else:
        stmt = delete(Watchlist).where(
            Watchlist.user_id == user_id,
            Watchlist.symbol == symbol,
            Watchlist.market_id == market_id,
        )
    result = await session.execute(stmt)
    await session.commit()
    
    if result.rowcount == 0:
        raise HTTPException(404, f"{symbol} niet gevonden in je watchlist")
        
    return {"message": f"{symbol} verwijderd uit watchlist"}
