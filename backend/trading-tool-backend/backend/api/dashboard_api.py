import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from backend.infrastructure.database import get_db
from backend.utils.auth_utils import get_current_user
from backend.schemas.dashboard_schema import (
    DashboardResponse,
    TradingAdviceSchema,
    TopSetupSchema,
    SetupSummarySchema
)
from backend.services.dashboard_service import DashboardService
from backend.infrastructure.repositories.dashboard_repository import DashboardRepository

router = APIRouter()
logger = logging.getLogger(__name__)

async def get_dashboard_service(db: AsyncSession = Depends(get_db)):
    repo = DashboardRepository(db)
    return DashboardService(repo)

# =========================================================
# 🔥 DASHBOARD DATA (USER-SPECIFIEK)
# =========================================================
@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard_data(
    symbol: str = "BTC",
    current_user: dict = Depends(get_current_user),
    service: DashboardService = Depends(get_dashboard_service)
):
    """Haalt alle data voor de widgets op via parallel database queries."""
    user_id = current_user["id"]
    
    # V1 Constraint: Only allow BTC, ETH, SOL
    if symbol.upper() not in ["BTC", "ETH", "SOL"]:
        symbol = "BTC"
        
    return await service.get_dashboard_data(user_id, symbol.upper())


# =========================================================
# ❤️ HEALTH CHECK
# =========================================================
@router.get("/dashboard/health")
async def health_check(service: DashboardService = Depends(get_dashboard_service)):
    return await service.check_health()


# =========================================================
# 🧠 TRADING ADVICE (user-specifiek)
# =========================================================
@router.get("/dashboard/trading_advice", response_model=TradingAdviceSchema)
async def get_trading_advice(
    symbol: str = "BTC",
    current_user: dict = Depends(get_current_user),
    service: DashboardService = Depends(get_dashboard_service)
):
    user_id = current_user["id"]
    return await service.get_trading_advice(symbol, user_id)


# =========================================================
# ⭐ TOP SETUPS (user-specifiek)
# =========================================================
@router.get("/dashboard/top_setups", response_model=List[TopSetupSchema])
async def get_top_setups(
    current_user: dict = Depends(get_current_user),
    service: DashboardService = Depends(get_dashboard_service)
):
    user_id = current_user["id"]
    return await service.get_top_setups(user_id)


# =========================================================
# 📝 SETUP SUMMARY (user-specifiek)
# =========================================================
@router.get("/dashboard/setup_summary", response_model=List[SetupSummarySchema])
async def get_setup_summary(
    current_user: dict = Depends(get_current_user),
    service: DashboardService = Depends(get_dashboard_service)
):
    user_id = current_user["id"]
    return await service.get_setup_summary(user_id)
