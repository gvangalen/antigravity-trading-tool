import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_db
from backend.services.macro_data_service import MacroDataService
from backend.schemas.macro_data_schema import (
    MacroDataResponse, MacroAggregateResponse, MacroAddResponse, 
    MacroIndicatorNamesResponse, MacroIndicatorRuleResponse
)
from backend.schemas.technical_data_schema import (
    TechnicalIndicatorPreferenceItem,
    TechnicalIndicatorPreferenceResponse,
)
from backend.utils.auth_utils import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)
logger.info("🚀 macro_data_api.py geladen – in Clean Architecture mode met AsyncSession")


# =========================================================
# INDICATORS (USER GEBASEERD)
# =========================================================
@router.post("/macro_data", response_model=MacroAddResponse)
async def add_macro_indicator(
    payload: dict,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        user_id = current_user["id"]
        raw_name = payload.get("name")
        value = payload.get("value")
        symbol = payload.get("symbol")
        
        service = MacroDataService(db)
        return await service.add_macro_indicator(int(user_id), raw_name, value, symbol=symbol)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [add_macro] Error: {e}", exc_info=True)
        raise HTTPException(500, "Fout bij opslaan macro-indicator.")

@router.get("/macro_data", response_model=List[MacroDataResponse])
async def get_macro_indicators(
    symbol: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        user_id = current_user["id"]
        service = MacroDataService(db)
        return await service.get_macro_indicators(int(user_id), symbol=symbol)
    except Exception as e:
        logger.error(f"❌ [get_macro] {e}", exc_info=True)
        raise HTTPException(500, "Fout bij ophalen macro-indicatoren.")

@router.delete("/macro_data/{name}")
async def delete_macro_indicator(
    name: str,
    symbol: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        service = MacroDataService(db)
        return await service.delete_macro_indicator(name, int(current_user["id"]), symbol=symbol)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [delete_macro] {e}", exc_info=True)
        raise HTTPException(500, "Fout bij verwijderen indicator.")

@router.get("/macro_data/day", response_model=List[MacroDataResponse])
async def get_latest_macro_day_data(
    symbol: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        service = MacroDataService(db)
        return await service.get_latest_macro_day_data(int(current_user["id"]), symbol=symbol)
    except Exception as e:
        logger.error(f"❌ [macro_day_data] {e}", exc_info=True)
        raise HTTPException(500, "Fout bij ophalen dagtabellen.")

# =========================================================
# AGGREGATIE DATA (WEEK / MAAND / KWARTAAL)
# =========================================================
@router.get("/macro_data/week", response_model=List[MacroAggregateResponse])
async def get_macro_week_data(
    symbol: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        service = MacroDataService(db)
        return await service.get_macro_week_data(int(current_user["id"]), symbol=symbol)
    except Exception as e:
        logger.error(f"❌ [macro_week_data] {e}", exc_info=True)
        raise HTTPException(500, "Fout bij ophalen macro week data.")

@router.get("/macro_data/month", response_model=List[MacroAggregateResponse])
async def get_macro_month_data(
    symbol: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        service = MacroDataService(db)
        return await service.get_macro_month_data(int(current_user["id"]), symbol=symbol)
    except Exception as e:
        logger.error(f"❌ [macro_month_data] {e}", exc_info=True)
        raise HTTPException(500, "Fout bij ophalen macro month data.")

@router.get("/macro_data/quarter", response_model=List[MacroAggregateResponse])
async def get_macro_quarter_data(
    symbol: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        service = MacroDataService(db)
        return await service.get_macro_quarter_data(int(current_user["id"]), symbol=symbol)
    except Exception as e:
        logger.error(f"❌ [macro_quarter_data] {e}", exc_info=True)
        raise HTTPException(500, "Fout bij ophalen macro quarter data.")

# =========================================================
# INDICATOR CONFIG & RULES
# =========================================================
@router.get("/macro/indicators", response_model=List[MacroIndicatorNamesResponse])
async def get_all_macro_indicators(db: AsyncSession = Depends(get_db)):
    try:
        service = MacroDataService(db)
        return await service.get_all_macro_indicators()
    except Exception as e:
        logger.error(f"❌ [macro_indicator_names] {e}")
        raise HTTPException(500, "Fout bij ophalen macro-indicatornamen.")

@router.get("/macro_indicator_rules/{name}", response_model=List[MacroIndicatorRuleResponse])
async def get_rules_for_macro_indicator(
    name: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        service = MacroDataService(db)
        return await service.get_rules_for_macro_indicator(name, int(current_user["id"]))
    except Exception as e:
        logger.error(f"❌ [macro_indicator_rules] {e}")
        raise HTTPException(500, "Fout bij ophalen macro-indicatorregels.")


@router.get("/macro/preferences", response_model=TechnicalIndicatorPreferenceResponse)
async def get_macro_preferences(
    symbol: Optional[str] = Query(None),
    asset_class: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = current_user["id"]
    service = MacroDataService(db)
    resolved = await service.resolve_effective_preferences(user_id, symbol=symbol, asset_class=asset_class)
    return TechnicalIndicatorPreferenceResponse(
        scope=resolved["scope"],
        symbol=resolved["symbol"],
        asset_class=resolved["asset_class"],
        indicators=[
            TechnicalIndicatorPreferenceItem(
                indicator=row.indicator,
                priority=int(row.priority or 100),
            )
            for row in resolved["rows"]
        ],
    )


@router.post("/macro/preferences/bootstrap", response_model=TechnicalIndicatorPreferenceResponse)
async def bootstrap_macro_preferences(
    symbol: Optional[str] = Query(None),
    asset_class: Optional[str] = Query(None),
    scope: str = Query("asset_class"),
    preset: str = Query("recommended"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = current_user["id"]
    service = MacroDataService(db)
    try:
        result = await service.bootstrap_preferences(
            user_id,
            symbol=symbol,
            asset_class=asset_class,
            scope=scope,
            preset=preset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return TechnicalIndicatorPreferenceResponse(
        scope=result["scope"],
        symbol=result["symbol"],
        asset_class=result["asset_class"],
        indicators=[
            TechnicalIndicatorPreferenceItem(
                indicator=row.indicator,
                priority=int(row.priority or 100),
            )
            for row in result["rows"]
        ],
    )


@router.post("/macro/preferences/sync")
async def sync_macro_preferences_for_symbol(
    symbol: str = Query(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = current_user["id"]
    service = MacroDataService(db)
    result = await service.sync_effective_indicators(user_id, symbol)
    await db.commit()
    return result
