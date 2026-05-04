import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_

from backend.infrastructure.database import get_db
from backend.utils.auth_utils import get_current_user
from backend.infrastructure.models import Watchlist

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/watchlist", response_model=List[str])
async def get_watchlist(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    user_id = current_user["id"]
    stmt = select(Watchlist.symbol).where(Watchlist.user_id == user_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())

@router.post("/watchlist")
async def add_to_watchlist(
    request: Request,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db)
):
    data = await request.json()
    symbol = data.get("symbol")
    if not symbol:
        raise HTTPException(400, "Symbol is verplicht")
    
    user_id = current_user["id"]
    symbol = symbol.upper()

    # Check if already exists
    stmt = select(Watchlist).where(and_(Watchlist.user_id == user_id, Watchlist.symbol == symbol))
    existing = await session.execute(stmt)
    if existing.scalars().first():
        return {"message": f"{symbol} staat al in je watchlist"}

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
