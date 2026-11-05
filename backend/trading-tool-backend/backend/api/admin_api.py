import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Any

from backend.infrastructure.database import get_db
from backend.utils.auth_utils import get_current_user
from backend.services.admin_ai_service import AdminAiService
from backend.services.admin_user_service import AdminUserService
from backend.services.admin_finn_v2_service import AdminFinnV2Service
from backend.schemas.admin_schema import (
    AdminAiStatsResponse,
    AdminUserOverview,
    AdminUserPage,
    AdminUserUpdate,
    FinnV2AdminOverview,
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


@router.get("/admin/finn-v2/overview", response_model=FinnV2AdminOverview)
async def get_admin_finn_v2_overview(
    current_user: dict = Depends(check_admin),
    db: AsyncSession = Depends(get_db),
):
    return await AdminFinnV2Service(db).overview()

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


@router.get("/admin/users/page", response_model=AdminUserPage)
async def get_admin_users_page(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: str = Query("", max_length=120),
    plan: str = Query("all", max_length=20),
    current_user: dict = Depends(check_admin),
    db: AsyncSession = Depends(get_db),
):
    if plan not in {"all", "free", "basis", "pro", "premium"}:
        raise HTTPException(status_code=422, detail="Invalid plan filter")
    return await AdminUserService(db).get_users_page(
        offset=offset, limit=limit, search=search, plan=plan
    )

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
        
        user_page = await service.get_users_page(user_id=user_id, limit=1)
        if not user_page["items"]:
            raise HTTPException(status_code=404, detail="Gebruiker niet gevonden.")
        return user_page["items"][0]
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
