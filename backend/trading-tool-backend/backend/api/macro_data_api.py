import logging
from typing import List

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_db
from backend.services.macro_data_service import MacroDataService
from backend.schemas.macro_data_schema import (
    MacroDataResponse, MacroAggregateResponse, MacroAddResponse, 
    MacroIndicatorNamesResponse, MacroIndicatorRuleResponse
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
        
        service = MacroDataService(db)
        return await service.add_macro_indicator(int(user_id), raw_name, value)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [add_macro] Error: {e}", exc_info=True)
        raise HTTPException(500, "Fout bij opslaan macro-indicator.")

@router.get("/macro_data", response_model=List[MacroDataResponse])
async def get_macro_indicators(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        user_id = current_user["id"]
        service = MacroDataService(db)
        return await service.get_macro_indicators(int(user_id))
    except Exception as e:
        logger.error(f"❌ [get_macro] {e}", exc_info=True)
        raise HTTPException(500, "Fout bij ophalen macro-indicatoren.")

@router.delete("/macro_data/{name}")
async def delete_macro_indicator(
    name: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        service = MacroDataService(db)
        return await service.delete_macro_indicator(name, int(current_user["id"]))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [delete_macro] {e}", exc_info=True)
        raise HTTPException(500, "Fout bij verwijderen indicator.")

@router.get("/macro_data/day", response_model=List[MacroDataResponse])
async def get_latest_macro_day_data(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        service = MacroDataService(db)
        return await service.get_latest_macro_day_data(int(current_user["id"]))
    except Exception as e:
        logger.error(f"❌ [macro_day_data] {e}", exc_info=True)
        raise HTTPException(500, "Fout bij ophalen dagtabellen.")

# =========================================================
# AGGREGATIE DATA (WEEK / MAAND / KWARTAAL)
# =========================================================
@router.get("/macro_data/week", response_model=List[MacroAggregateResponse])
async def get_macro_week_data(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        service = MacroDataService(db)
        return await service.get_macro_week_data(int(current_user["id"]))
    except Exception as e:
        logger.error(f"❌ [macro_week_data] {e}", exc_info=True)
        raise HTTPException(500, "Fout bij ophalen macro week data.")

@router.get("/macro_data/month", response_model=List[MacroAggregateResponse])
async def get_macro_month_data(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        service = MacroDataService(db)
        return await service.get_macro_month_data(int(current_user["id"]))
    except Exception as e:
        logger.error(f"❌ [macro_month_data] {e}", exc_info=True)
        raise HTTPException(500, "Fout bij ophalen macro month data.")

@router.get("/macro_data/quarter", response_model=List[MacroAggregateResponse])
async def get_macro_quarter_data(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        service = MacroDataService(db)
        return await service.get_macro_quarter_data(int(current_user["id"]))
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
        raise HTTPException(500, detail=str(e))

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
        raise HTTPException(500, detail=str(e))
