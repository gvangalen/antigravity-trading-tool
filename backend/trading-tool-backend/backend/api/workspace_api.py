from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_db, measure_read_connection_acquire
from backend.services.workspace_data_service import WorkspaceDataService
from backend.services.exact_market_workspace_service import ExactMarketWorkspaceService
from backend.services.exact_market_indicator_service import ExactMarketIndicatorService
from backend.services.pair_indicator_config_service import PairIndicatorConfigService
from backend.services.indicator_score_refresh_service import queue_indicator_score_refresh
from backend.utils.scoring_utils import normalize_indicator_name
from backend.domain.market_indicator_catalog import get_market_indicator_definition
from backend.domain.macro_indicator_catalog import get_macro_indicator_definition
from backend.domain.technical_indicator_catalog import get_technical_indicator_definition
from backend.infrastructure.models import MacroData
from backend.utils.auth_utils import get_current_user


router = APIRouter()


class PairIndicatorWrite(BaseModel):
    market_id: int = Field(gt=0)
    category: str
    indicator: str
    mode: str
    score_mode: str
    weight: float = Field(ge=0, le=3)
    rules: list[dict] = Field(default_factory=list)


async def _pair_config(db: AsyncSession, market_id: int, category: str, indicator: str):
    service = PairIndicatorConfigService(db)
    market = await service.market(market_id)
    if market is None:
        raise HTTPException(status_code=404, detail="exact_market_not_verified")
    category = str(category or "").strip().lower()
    indicator = normalize_indicator_name(indicator)
    if category not in {"market", "macro", "technical"} or not indicator:
        raise HTTPException(status_code=400, detail="invalid_indicator")
    definition = {"market": get_market_indicator_definition,
                  "macro": get_macro_indicator_definition,
                  "technical": get_technical_indicator_definition}[category](indicator)
    if not definition or not definition.get("active"):
        raise HTTPException(status_code=400, detail="unsupported_indicator_for_market")
    return service, market, category, indicator


@router.get("/workspace/exact-market/indicator-config")
async def get_pair_indicator_config(
    market_id: int = Query(..., gt=0), category: str = Query(...), indicator: str = Query(...),
    current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    service, market, category, indicator = await _pair_config(db, market_id, category, indicator)
    return await service.get(int(current_user["id"]), market, category, indicator)


@router.put("/workspace/exact-market/indicator-config")
async def put_pair_indicator_config(
    payload: PairIndicatorWrite, current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service, market, category, indicator = await _pair_config(
        db, payload.market_id, payload.category, payload.indicator)
    if payload.mode not in {"add", "edit"}:
        raise HTTPException(status_code=400, detail="invalid_indicator_mode")
    try:
        await service.save(int(current_user["id"]), market, category, indicator,
                           mode=payload.mode, score_mode=payload.score_mode,
                           weight=payload.weight, rules=payload.rules)
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(status_code=409 if detail == "indicator_already_configured_for_pair"
                            else 422, detail=detail) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="indicator_already_configured_for_pair") from exc
    status = "ready"
    if category == "macro":
        source = await db.execute(select(MacroData.id).where(
            MacroData.user_id == int(current_user["id"]),
            MacroData.symbol == market.asset_symbol,
            MacroData.name == indicator,
        ).limit(1))
        if source.first() is None:
            status = "pending_source"
    if category in {"market", "technical"}:
        try:
            result = await ExactMarketIndicatorService(db).materialize(
                market, owner_ids={int(current_user["id"])})
            if not result["written"]:
                status = "pending_source"
        except Exception:
            # The preference is already committed. A transient source failure
            # must not report that the user's saved choice was rolled back.
            await db.rollback()
            status = "pending_source"
    queue_indicator_score_refresh(int(current_user["id"]), market.asset_symbol,
                                  market_id=int(market.id))
    return {"ok": True, "market_id": market.id,
            "pair": f"{market.asset_symbol}/{market.quote_currency}", "status": status}


@router.delete("/workspace/exact-market/indicator-config")
async def delete_pair_indicator_config(
    market_id: int = Query(..., gt=0), category: str = Query(...), indicator: str = Query(...),
    current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    service, market, category, indicator = await _pair_config(db, market_id, category, indicator)
    await service.disable(int(current_user["id"]), market, category, indicator)
    queue_indicator_score_refresh(int(current_user["id"]), market.asset_symbol,
                                  market_id=int(market.id))
    return {"ok": True, "market_id": market.id}


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
