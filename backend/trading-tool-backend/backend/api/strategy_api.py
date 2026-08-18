import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_db
from backend.utils.auth_utils import get_current_user
from backend.schemas.trading_schema import StrategyCreateSchema
from backend.services.strategy_service import StrategyService

router = APIRouter()
logger = logging.getLogger(__name__)

def get_strategy_service(db: AsyncSession = Depends(get_db)):
    return StrategyService(db)

# ==========================================================
# 1️⃣ CREATE STRATEGY
# ==========================================================
@router.post("/strategies")
async def save_strategy(
    request: Request,
    current_user: dict = Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service)
):
    user_id = current_user["id"]
    raw_data = StrategyService.normalize_strategy_payload(await request.json())
    
    try:
        # Hybride valideren ("verplichte velden expliciet")
        payload = StrategyCreateSchema(**raw_data)
    except Exception as e:
        logger.error(f"❌ Validatiefout in strategy payload: {e}")
        raise HTTPException(422, detail=f"Validatie mislukt: {str(e)}")

    return await service.save_strategy(payload, raw_data, user_id)

# ==========================================================
# 2️⃣ QUERY STRATEGIES (cards + bot dropdown)
# ==========================================================
@router.post("/strategies/query")
async def query_strategies(
    request: Request,
    format: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service)
):
    filters = await request.json()
    user_id = current_user["id"]
    return await service.query_strategies(user_id, filters, format_type=format)

# ==========================================================
# 3️⃣ GENERATE STRATEGY (AI)
# ==========================================================
@router.post("/strategies/generate/{setup_id}")
async def generate_strategy_for_setup(
    setup_id: int,
    current_user: dict = Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service)
):
    return await service.generate_strategy_for_setup(setup_id, current_user["id"])

# ==========================================================
# 4️⃣ UPDATE STRATEGY (incl curve editor)
# ==========================================================
@router.put("/strategies/{strategy_id}")
async def update_strategy(
    strategy_id: int,
    request: Request,
    current_user: dict = Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service)
):
    data = StrategyService.normalize_strategy_payload(await request.json())
    return await service.update_strategy(strategy_id, data, current_user["id"])

# ==========================================================
# 5️⃣ DELETE STRATEGY
# ==========================================================
@router.delete("/strategies/{strategy_id}")
async def delete_strategy(
    strategy_id: int,
    current_user: dict = Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service)
):
    return await service.delete_strategy(strategy_id, current_user["id"])

# ==========================================================
# 6️⃣ AI STRATEGY ANALYSE
# ==========================================================
@router.post("/strategies/analyze/{strategy_id}")
async def analyze_strategy(
    strategy_id: int,
    current_user: dict = Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service)
):
    return await service.analyze_strategy(strategy_id, current_user["id"])

# ==========================================================
# 7️⃣ GET STRATEGY BY SETUP
# ==========================================================
@router.get("/strategies/by_setup/{setup_id}")
async def get_strategy_by_setup(
    setup_id: int,
    format: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service)
):
    return await service.get_strategy_by_setup(setup_id, current_user["id"], format_type=format)

# ==========================================================
# 8️⃣ LAST STRATEGY
# ==========================================================
@router.get("/strategies/last")
async def get_last_strategy(
    format: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service)
):
    return await service.get_last_strategy(current_user["id"], format_type=format)

# ==========================================================
# 9️⃣ FAVORITE TOGGLE
# ==========================================================
@router.patch("/strategies/{strategy_id}/favorite")
async def toggle_favorite(
    strategy_id: int,
    current_user: dict = Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service)
):
    return await service.toggle_favorite(strategy_id, current_user["id"])

# ==========================================================
# 🔟 EXPORT CSV
# ==========================================================
@router.get("/strategies/export")
async def export_strategies(
    current_user: dict = Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service)
):
    return await service.export_strategies(current_user["id"])

# ==========================================================
# 11 Get Curvers 
# ==========================================================
@router.get("/curves/execution")
async def get_execution_curves(
    current_user: dict = Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service)
):
    return await service.get_execution_curves(current_user["id"])

# ==========================================================
# 12 ACTIVE STRATEGY FOR TODAY
# ==========================================================
@router.get("/strategies/active-today")
async def get_active_strategy_today(
    current_user: dict = Depends(get_current_user),
    service: StrategyService = Depends(get_strategy_service)
):
    return await service.get_active_strategy_today(current_user["id"])
