import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException

from backend.utils.auth_utils import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

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
