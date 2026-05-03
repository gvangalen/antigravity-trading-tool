import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_db
from backend.services.market_data_service import MarketDataService
from backend.schemas.market_data_schema import (
    MarketDataResponse, MarketDataIndicatorResponse, MarketData7DResponse,
    MarketForwardReturnResponse, ForwardReturnChartResponse
)
from backend.utils.auth_utils import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)
logger.info("🚀 market_data_api.py geladen – in Clean Architecture mode met AsyncSession")

# Globale configuratie endpoint (wordt meegegeven aan service runtime)
MARKET_RAW_ENDPOINTS = {
    "btc_volume": "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=7"
}


# =========================================================
# INDICATORS (USER GEBASEERD)
# =========================================================
@router.post("/market_data/indicator", response_model=MarketDataIndicatorResponse)
async def add_user_market_indicator(
    payload: dict,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        user_id = current_user["id"]
        raw_name = payload.get("indicator") or payload.get("name")
        value = payload.get("value")
        symbol = payload.get("symbol") or "BTC"
        
        service = MarketDataService(db)
        return await service.add_user_market_indicator(int(user_id), raw_name, value, symbol=symbol)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [add_indicator] Error: {e}", exc_info=True)
        raise HTTPException(500, "Fout bij opslaan market-indicator.")

@router.get("/market_data/indicators", response_model=List[MarketDataIndicatorResponse])
async def list_user_market_indicators(
    limit: int = Query(200, ge=1, le=1000),
    symbol: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        user_id = current_user["id"]
        service = MarketDataService(db)
        return await service.list_user_market_indicators(int(user_id), symbol=symbol, limit=limit)
    except Exception as e:
        logger.error(f"❌ [list_indicators] {e}", exc_info=True)
        raise HTTPException(500, "Fout bij ophalen market-indicatoren.")

@router.delete("/market_data/indicator/{name}")
async def delete_market_indicator(
    name: str,
    symbol: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        service = MarketDataService(db)
        return await service.delete_user_market_indicator(name, int(current_user["id"]), symbol=symbol)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [delete_indicator] {e}", exc_info=True)
        raise HTTPException(500, "Fout bij verwijderen indicator.")

@router.get("/market_data/day")
async def get_market_day_data(
    symbol: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        service = MarketDataService(db)
        return await service.get_market_day_data(int(current_user["id"]), symbol=symbol)
    except Exception as e:
        logger.error(f"❌ [market_day_data] {e}", exc_info=True)
        raise HTTPException(500, "Fout bij ophalen dagtabellen.")


# =========================================================
# INDICATOR CONFIG & RULES
# =========================================================
@router.get("/market/indicator_names")
async def get_market_indicator_names(db: AsyncSession = Depends(get_db)):
    try:
        service = MarketDataService(db)
        return await service.get_global_indicators()
    except Exception as e:
        logger.error(f"❌ [indicator_names] {e}")
        raise HTTPException(500, detail=str(e))

@router.get("/market/indicator_rules/{name}")
async def get_market_indicator_rules(
    name: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        service = MarketDataService(db)
        return await service.get_indicator_rules(name, int(current_user["id"]))
    except Exception as e:
        logger.error(f"❌ [indicator_rules] {e}")
        raise HTTPException(500, detail=str(e))


# =========================================================
# GLOBALE MARKT DATA (LIST, LATEST, INTERPRETED)
# =========================================================
@router.get("/market_data/list", response_model=List[MarketDataResponse])
async def list_market_data(
    since_minutes: int = Query(default=1440),
    db: AsyncSession = Depends(get_db)
):
    try:
        service = MarketDataService(db)
        return await service.get_market_data_list(since_minutes)
    except Exception as e:
        logger.error(f"❌ [list] DB-fout: {e}")
        raise HTTPException(500, "❌ Kon marktdata niet ophalen.")

@router.get("/market_data/{symbol}/latest", response_model=MarketDataResponse)
async def get_latest_price(
    symbol: str,
    db: AsyncSession = Depends(get_db)
):
    try:
        service = MarketDataService(db)
        result = await service.repository.get_latest_snapshot(symbol.upper())
        if not result:
            raise HTTPException(404, f"Geen {symbol} data gevonden")
        return MarketDataResponse.from_orm(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [latest_price] {symbol} Error: {e}")
        raise HTTPException(500, f"Kon laatste {symbol}_prijs niet ophalen")

@router.get("/market_data/interpreted")
async def fetch_interpreted_data(
    symbol: str = Query("BTC"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        service = MarketDataService(db)
        return await service.get_interpreted_data(int(current_user["id"]), symbol=symbol)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [interpreted] {symbol} Fout: {e}")
        raise HTTPException(500, f"❌ Interpretatiefout voor {symbol}.")


# =========================================================
# 7D DATA (COINGECKO SYNC & GET)
# =========================================================
@router.post("/market_data/7d/fill")
async def fill_7day_data(
    symbol: str = Query("BTC"),
    overwrite: bool = Query(False),
    db: AsyncSession = Depends(get_db)
):
    try:
        service = MarketDataService(db)
        return await service.sync_symbol_7day_data(symbol, overwrite=overwrite)
    except Exception as e:
        logger.error(f"❌ Fout bij ophalen en opslaan {symbol} market data: {e}")
        return {"error": f"❌ {str(e)}"}

@router.get("/market_data/7d", response_model=List[MarketData7DResponse])
async def get_market_data_7d(
    symbol: str = Query("BTC"),
    db: AsyncSession = Depends(get_db)
):
    try:
        service = MarketDataService(db)
        return await service.get_market_data_7d(symbol)
    except Exception as e:
        logger.error(f"❌ [7d] {symbol} Fout: {e}")
        raise HTTPException(500, "Fout bij ophalen 7-daagse data.")


# =========================================================
# FORWARD RETURNS
# =========================================================
@router.get("/market_data/forward", response_model=List[MarketForwardReturnResponse])
async def get_market_forward_returns(
    symbol: str = Query("BTC"),
    db: AsyncSession = Depends(get_db)
):
    try:
        service = MarketDataService(db)
        return await service.get_market_forward_returns(symbol)
    except Exception as e:
        logger.error(f"❌ [forward] {symbol} Fout: {e}")
        raise HTTPException(500, "Fout bij ophalen forward returns.")

@router.get("/market_data/forward/week", response_model=List[ForwardReturnChartResponse])
async def get_week_returns(
    symbol: str = Query("BTC"),
    db: AsyncSession = Depends(get_db)
):
    try:
        service = MarketDataService(db)
        return await service.get_forward_returns_aggregated('7d', symbol=symbol)
    except Exception as e:
         logger.error(f"❌ Week returns {symbol} error: {e}")
         raise HTTPException(500, "Fout bij ophalen week returns.")

@router.get("/market_data/forward/maand", response_model=List[ForwardReturnChartResponse])
async def get_month_returns(
    symbol: str = Query("BTC"),
    db: AsyncSession = Depends(get_db)
):
    try:
        service = MarketDataService(db)
        return await service.get_forward_returns_aggregated('30d', symbol=symbol)
    except Exception as e:
         logger.error(f"❌ Month returns {symbol} error: {e}")
         raise HTTPException(500, "Fout bij ophalen maand returns.")

@router.get("/market_data/forward/kwartaal", response_model=List[ForwardReturnChartResponse])
async def get_quarter_returns(
    symbol: str = Query("BTC"),
    db: AsyncSession = Depends(get_db)
):
    try:
        service = MarketDataService(db)
        return await service.get_forward_returns_aggregated('90d', symbol=symbol)
    except Exception as e:
         logger.error(f"❌ Quarter returns {symbol} error: {e}")
         raise HTTPException(500, "Fout bij ophalen kwartaal returns.")

@router.get("/market_data/forward/jaar", response_model=List[ForwardReturnChartResponse])
async def get_year_returns(
    symbol: str = Query("BTC"),
    db: AsyncSession = Depends(get_db)
):
    try:
        service = MarketDataService(db)
        return await service.get_forward_returns_aggregated('365d', symbol=symbol)
    except Exception as e:
         logger.error(f"❌ Year returns {symbol} error: {e}")
         raise HTTPException(500, "Fout bij ophalen jaar returns.")
