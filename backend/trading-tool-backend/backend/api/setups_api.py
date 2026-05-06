from fastapi import APIRouter, HTTPException, Request, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import logging
from typing import Optional, List

from backend.infrastructure.database import get_db
from backend.utils.auth_utils import get_current_user
from backend.schemas.trading_schema import SetupCreateSchema
from backend.services.setup_service import SetupService

router = APIRouter()
logger = logging.getLogger(__name__)

async def get_setup_service(db: AsyncSession = Depends(get_db)):
    return SetupService(db)

# ============================================================
# 1️⃣ Setup aanmaken
# ============================================================
@router.post("/setups")
async def save_setup(
    request: Request, 
    current_user: dict = Depends(get_current_user),
    service: SetupService = Depends(get_setup_service)
):
    user_id = current_user["id"]
    raw_data = await request.json()
    
    # Valideer verplichte Pydantic velden expliciet
    try:
        payload = SetupCreateSchema(**raw_data)
    except Exception as e:
        logger.error(f"❌ Validatiefout in setup payload: {e}")
        raise HTTPException(422, detail=f"Validatie mislukt: {str(e)}")

    # Rest van logica in service (hybride permissief)
    return await service.save_setup(payload, raw_data, user_id)

# ============================================================
# 🔟 Laatste setup
# ============================================================
@router.get("/setups/last")
async def last_setup(
    setup_id: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_user),
    service: SetupService = Depends(get_setup_service)
):
    user_id = current_user["id"]
    return await service.get_last_setup(user_id, setup_id)

# ============================================================
# 2️⃣ Alle setups
# ============================================================
@router.get("/setups")
async def get_setups(
    setup_type: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    service: SetupService = Depends(get_setup_service)
):
    user_id = current_user["id"]
    return await service.get_setups(user_id, setup_type)

# ============================================================
# 3️⃣ DCA setups
# ============================================================
@router.get("/setups/dca")
async def get_dca_setups(
    current_user: dict = Depends(get_current_user),
    service: SetupService = Depends(get_setup_service)
):
    user_id = current_user["id"]
    return await service.get_dca_setups(user_id)

# ============================================================
# 🔟 Daily setup scores
# ============================================================
@router.get("/setups/daily-scores")
async def get_daily_setup_scores(
    symbol: str = Query("BTC"),
    current_user: dict = Depends(get_current_user),
    service: SetupService = Depends(get_setup_service)
):
    user_id = current_user["id"]
    return await service.get_daily_setup_scores(user_id, symbol.upper())

# ============================================================
# 4️⃣ Setup bijwerken
# ============================================================
@router.patch("/setups/{setup_id}")
async def update_setup(
    setup_id: int,
    request: Request,
    current_user: dict = Depends(get_current_user),
    service: SetupService = Depends(get_setup_service)
):
    user_id = current_user["id"]
    raw_data = await request.json()
    return await service.update_setup(setup_id, raw_data, user_id)

# ============================================================
# 5️⃣ Setup verwijderen
# ============================================================
@router.delete("/setups/{setup_id}")
async def delete_setup(
    setup_id: int, 
    current_user: dict = Depends(get_current_user),
    service: SetupService = Depends(get_setup_service)
):
    user_id = current_user["id"]
    return await service.delete_setup(setup_id, user_id)

# ============================================================
# 6️⃣ Naamcheck
# ============================================================
@router.get("/setups/check_name/{name}")
async def check_name(
    name: str, 
    current_user: dict = Depends(get_current_user),
    service: SetupService = Depends(get_setup_service)
):
    user_id = current_user["id"]
    return await service.check_name(name, user_id)

# ============================================================
# 7️⃣ AI explanation
# ============================================================
@router.post("/setups/explanation/{setup_id}")
async def ai_explanation(
    setup_id: int, 
    current_user: dict = Depends(get_current_user),
    service: SetupService = Depends(get_setup_service)
):
    user_id = current_user["id"]
    return await service.ai_explanation(setup_id, user_id)

# ============================================================
# 8️⃣ Top setups
# ============================================================
@router.get("/setups/top")
async def get_top_setups(
    limit: int = 3, 
    current_user: dict = Depends(get_current_user),
    service: SetupService = Depends(get_setup_service)
):
    user_id = current_user["id"]
    return await service.get_top_setups(user_id, limit)

# ============================================================
# 🔥 Active setup
# ============================================================
@router.get("/setups/active")
async def get_active_setup(
    symbol: str = Query("BTC"),
    current_user: dict = Depends(get_current_user),
    service: SetupService = Depends(get_setup_service)
):
    user_id = current_user["id"]
    return await service.get_active_setup(user_id, symbol.upper())

# ============================================================
# 9️⃣ Eén setup ophalen
# ============================================================
@router.get("/setups/{setup_id}")
async def get_setup_by_id(
    setup_id: int, 
    current_user: dict = Depends(get_current_user),
    service: SetupService = Depends(get_setup_service)
):
    user_id = current_user["id"]
    return await service.get_setup_by_id(setup_id, user_id)
