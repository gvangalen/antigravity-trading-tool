from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_db, measure_read_connection_acquire
from backend.services.workspace_data_service import WorkspaceDataService
from backend.services.exact_market_workspace_service import ExactMarketWorkspaceService
from backend.utils.auth_utils import get_current_user


router = APIRouter()


@router.get("/workspace/exact-market")
async def get_exact_market_workspace(
    request: Request,
    symbol: str = Query(..., min_length=1, max_length=20),
    quote_currency: str = Query(..., regex="^(EUR|USDT)$"),
    market_period: str = Query("day", regex="^(day|week|month|quarter)$"),
    macro_period: str = Query("day", regex="^(day|week|month|quarter)$"),
    technical_period: str = Query("day", regex="^(day|week|month|quarter)$"),
    watchlist_symbols: str = Query("", max_length=250),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await measure_read_connection_acquire(db, route="workspace", trace_id=getattr(request.state, "trace_id", None))
    payload = await ExactMarketWorkspaceService(db).get(
        int(current_user["id"]), symbol, quote_currency,
        periods={"market": market_period, "macro": macro_period, "technical": technical_period},
        watchlist_symbols=[item.strip() for item in watchlist_symbols.split(",") if item.strip()],
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="exact_market_not_verified")
    return payload


@router.get("/workspace/asset")
async def get_asset_workspace(
    request: Request,
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
    await measure_read_connection_acquire(db, route="workspace", trace_id=getattr(request.state, "trace_id", None))
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
