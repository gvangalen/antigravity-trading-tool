from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_db
from backend.services.workspace_data_service import WorkspaceDataService
from backend.utils.auth_utils import get_current_user


router = APIRouter()


@router.get("/workspace/asset")
async def get_asset_workspace(
    symbol: str = Query("BTC", min_length=1, max_length=20),
    market_period: str = Query("day", regex="^(day|week|month|quarter)$"),
    macro_period: str = Query("day", regex="^(day|week|month|quarter)$"),
    technical_period: str = Query("day", regex="^(day|week|month|quarter)$"),
    watchlist_symbols: str = Query("", max_length=250),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    parsed_watchlist = [
        item.strip()
        for item in watchlist_symbols.split(",")
        if item.strip()
    ]
    service = WorkspaceDataService(db)
    return await service.get_asset_workspace(
        int(current_user["id"]),
        symbol,
        market_period,
        macro_period,
        technical_period,
        parsed_watchlist,
    )


@router.get("/workspace/watchlist")
async def get_workspace_watchlist(
    symbols: str = Query("BTC,ETH", max_length=250),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    parsed = [symbol.strip() for symbol in symbols.split(",") if symbol.strip()]
    service = WorkspaceDataService(db)
    return await service.get_watchlist(int(current_user["id"]), parsed)
