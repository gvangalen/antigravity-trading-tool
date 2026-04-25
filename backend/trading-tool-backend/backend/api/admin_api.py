import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Any

from backend.infrastructure.database import get_db
from backend.utils.auth_utils import get_current_user
from backend.services.admin_ai_service import AdminAiService
from backend.services.admin_user_service import AdminUserService
from backend.schemas.admin_schema import (
    AdminAiStatsResponse,
    AdminUserOverview,
    AdminUserUpdate,
    AdminSystemLog,
    AdminLogAnalysisResponse
)
from backend.services.admin_log_service import AdminLogService

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

# =========================================================
# 👤 USER MANAGEMENT
# =========================================================
@router.get("/admin/users", response_model=List[AdminUserOverview])
async def get_admin_users(
    current_user: dict = Depends(check_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Haalt alle gebruikers op voor het admin dashboard.
    """
    try:
        service = AdminUserService(db)
        return await service.get_all_users_overview()
    except Exception as e:
        logger.error(f"❌ Error fetching Admin Users: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Fout bij het ophalen van gebruikers.")

@router.patch("/admin/users/{user_id}", response_model=AdminUserOverview)
async def update_admin_user(
    user_id: int,
    updates: AdminUserUpdate,
    current_user: dict = Depends(check_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Update een gebruiker (plan, limiet, status) door een admin.
    """
    try:
        service = AdminUserService(db)
        updated = await service.update_user_admin(user_id, updates.dict(exclude_unset=True))
        if not updated:
            raise HTTPException(status_code=404, detail="Gebruiker niet gevonden.")
        
        # We halen het volledige overview op om aan het response model te voldoen
        all_users = await service.get_all_users_overview()
        user_data = next((u for u in all_users if u["id"] == user_id), None)
        return user_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error updating Admin User {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Fout bij het updaten van de gebruiker.")

# =========================================================
# 📝 SYSTEM LOGS
# =========================================================
@router.get("/admin/logs", response_model=List[AdminSystemLog])
async def get_admin_logs(
    level: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    current_user: dict = Depends(check_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Haalt systeemlogs op met filters.
    """
    try:
        service = AdminLogService(db)
        return await service.get_logs(limit=limit, level=level, source=source, search=search)
    except Exception as e:
        logger.error(f"❌ Error fetching Admin Logs: {e}")
        raise HTTPException(status_code=500, detail="Fout bij ophalen van logs.")

@router.post("/admin/logs/analyze", response_model=AdminLogAnalysisResponse)
async def analyze_admin_logs(
    current_user: dict = Depends(check_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Analyseert recente errors met AI.
    """
    try:
        service = AdminLogService(db)
        return await service.analyze_errors_with_ai()
    except Exception as e:
        logger.error(f"❌ Error analyzing Admin Logs: {e}")
        raise HTTPException(status_code=500, detail="Fout bij AI analyse van logs.")
