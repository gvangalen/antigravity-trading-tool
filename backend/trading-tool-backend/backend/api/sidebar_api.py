from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import logging

from backend.infrastructure.database import get_db
from backend.infrastructure.repositories.sidebar_repository import SidebarRepository
from backend.services.sidebar_service import SidebarService
from backend.schemas.sidebar_schema import ActiveTradeResponse, BotStatusResponse

router = APIRouter()
logger = logging.getLogger(__name__)

async def get_sidebar_service(db: AsyncSession = Depends(get_db)) -> SidebarService:
    repository = SidebarRepository(db)
    return SidebarService(repository)

# ✅ Actieve trades ophalen (Nu via Service laag)
@router.get("/active-trades", response_model=List[ActiveTradeResponse])
async def get_active_trades(service: SidebarService = Depends(get_sidebar_service)):
    try:
        return await service.get_active_trades()
    except Exception as e:
        logger.error(f"❌ SB01: Fout bij ophalen trades: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ✅ AI bot status ophalen (Nu via Service laag)
@router.get("/ai-bot-status", response_model=BotStatusResponse)
async def get_ai_bot_status(service: SidebarService = Depends(get_sidebar_service)):
    try:
        return await service.get_ai_bot_status()
    except Exception as e:
        logger.error(f"❌ SB02: Fout bij ophalen botstatus: {e}")
        raise HTTPException(status_code=500, detail=str(e))
