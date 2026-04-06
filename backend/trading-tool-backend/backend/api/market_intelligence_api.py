import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_db
from backend.utils.auth_utils import get_current_user
from backend.infrastructure.repositories.intelligence_repository import IntelligenceRepository
from backend.services.intelligence_service import IntelligenceService

logger = logging.getLogger(__name__)
router = APIRouter()

def get_intelligence_service(db: AsyncSession = Depends(get_db)):
    repo = IntelligenceRepository(db)
    return IntelligenceService(repo)

# =========================================================
# API: Market Intelligence
# =========================================================
@router.get("/market/intelligence", response_model=Dict[str, Any])
async def get_market_intelligence_api(
    current_user: dict = Depends(get_current_user),
    service: IntelligenceService = Depends(get_intelligence_service)
):
    try:
        user_id = current_user["id"]
        return await service.get_market_intelligence(user_id=user_id)
    except Exception as e:
        logger.exception("❌ Error fetching market intelligence")
        raise HTTPException(status_code=500, detail="Fout bij ophalen market intelligence")
