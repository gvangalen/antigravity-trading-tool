import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from backend.infrastructure.database import get_db
from backend.utils.auth_utils import get_current_user
from backend.services.admin_ai_service import AdminAiService
from backend.schemas.admin_schema import AdminAiStatsResponse

router = APIRouter()
logger = logging.getLogger(__name__)

def check_admin(current_user: dict = Depends(get_current_user)):
    """
    Strikte admin check op rol-niveau.
    """
    if current_user.get("role") != "admin":
        logger.warning(f"🚫 Unauthorized Admin Access Attempt by user {current_user.get('id')}")
        raise HTTPException(status_code=403, detail="Admin access required.")
    return current_user

@router.get("/admin/ai/stats", response_model=AdminAiStatsResponse)
async def get_admin_ai_stats(
    current_user: dict = Depends(check_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Haalt alle geaggregeerde AI stats op voor het admin dashboard.
    """
    try:
        service = AdminAiService(db)
        stats = await service.get_ai_stats_overview()
        return stats
    except Exception as e:
        logger.error(f"❌ Error fetching Admin AI Stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Fout bij het ophalen van AI statistieken.")
