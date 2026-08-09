import logging
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_, asc

from backend.infrastructure.database import get_db
from backend.services.asset_catalog_service import AssetCatalogService
from backend.utils.auth_utils import get_current_user
from backend.infrastructure.models import Watchlist

logger = logging.getLogger(__name__)
router = APIRouter()


class WatchlistItemResponse(BaseModel):
    symbol: str
    display_name: str
    asset_class: str
    logo_url: str | None = None
    tradingview_symbol: str | None = None


class WatchlistAddRequest(BaseModel):
    symbol: str
    asset_class: str | None = None
    display_name: str | None = None
    tradingview_symbol: str | None = None


async def _serialize_watchlist(
    session: AsyncSession,
    user_id: int,
) -> list[WatchlistItemResponse]:
    stmt = (
        select(Watchlist.symbol)
        .where(Watchlist.user_id == user_id)
        .order_by(asc(Watchlist.created_at), asc(Watchlist.id))
    )
    result = await session.execute(stmt)
    symbols = [str(symbol or "").upper() for symbol in result.scalars().all() if symbol]
    if not symbols:
        return []

    asset_map = await AssetCatalogService(session).get_assets(symbols)
    return [
        WatchlistItemResponse(
            symbol=symbol,
            display_name=asset_map.get(symbol, {}).get("display_name") or symbol,
            asset_class=asset_map.get(symbol, {}).get("asset_class") or "crypto",
            logo_url=asset_map.get(symbol, {}).get("logo_url"),
            tradingview_symbol=asset_map.get(symbol, {}).get("tradingview_symbol"),
        )
        for symbol in symbols
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
    symbol = payload.symbol
    if not symbol:
        raise HTTPException(400, "Symbol is verplicht")
    
    user_id = current_user["id"]
    symbol = symbol.upper()

    # Check if already exists
    stmt = select(Watchlist).where(and_(Watchlist.user_id == user_id, Watchlist.symbol == symbol))
    existing = await session.execute(stmt)
    if existing.scalars().first():
        return {"message": f"{symbol} staat al in je watchlist", "symbol": symbol}

    new_item = Watchlist(user_id=user_id, symbol=symbol)
    session.add(new_item)
    await session.commit()
    return {"message": f"{symbol} toegevoegd aan watchlist", "symbol": symbol}

@router.delete("/watchlist/{symbol}")
async def remove_from_watchlist(
    symbol: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    user_id = current_user["id"]
    symbol = symbol.upper()
    
    stmt = delete(Watchlist).where(and_(Watchlist.user_id == user_id, Watchlist.symbol == symbol))
    result = await session.execute(stmt)
    await session.commit()
    
    if result.rowcount == 0:
        raise HTTPException(404, f"{symbol} niet gevonden in je watchlist")
        
    return {"message": f"{symbol} verwijderd uit watchlist"}
