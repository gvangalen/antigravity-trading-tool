import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_db
from backend.utils.auth_utils import get_current_user
from backend.infrastructure.repositories.intelligence_repository import IntelligenceRepository
from backend.services.intelligence_service import IntelligenceService
from backend.services.locale_service import localize_generic_payload, resolve_request_locale

logger = logging.getLogger(__name__)
router = APIRouter()

async def get_intelligence_service(db: AsyncSession = Depends(get_db)):
    repo = IntelligenceRepository(db)
    return IntelligenceService(repo)

# =========================================================
# API: Market Intelligence
# =========================================================
@router.get("/market/intelligence", response_model=Dict[str, Any])
async def get_market_intelligence_api(
    symbol: str = "BTC",
    current_user: dict = Depends(get_current_user),
    service: IntelligenceService = Depends(get_intelligence_service),
    x_locale: str | None = Header(default=None, alias="X-Locale"),
):
    try:
        user_id = current_user["id"]
        
        # V1 Constraint: Only allow BTC, ETH, SOL
        if symbol.upper() not in ["BTC", "ETH", "SOL"]:
            symbol = "BTC"
            
        payload = await service.get_market_intelligence(user_id=user_id, symbol=symbol.upper())
        locale = resolve_request_locale(x_locale, current_user.get("ai_preferences") or {})
        return await localize_generic_payload(payload, locale)
    except Exception as e:
        logger.exception("❌ Error fetching market intelligence")
        raise HTTPException(status_code=500, detail="Fout bij ophalen market intelligence")

@router.post("/market/asset/initialize")
async def initialize_asset(
    payload: Dict[str, str],
    current_user: dict = Depends(get_current_user)
):
    symbol = payload.get("symbol")
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol is verplicht")
    
    try:
        from backend.celery_task.asset_initialization import initialize_asset_data
        initialize_asset_data.delay(current_user["id"], symbol.upper())
        return {"status": "accepted", "message": f"Initialization started for {symbol}"}
    except Exception as e:
        logger.error(f"❌ Error triggering asset initialization: {e}")
        raise HTTPException(status_code=500, detail="Fout bij starten asset initialisatie")
