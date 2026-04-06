import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_db
from backend.utils.auth_utils import get_current_user
from backend.schemas.score_schema import DailyCombinedScoreResponse, MasterScoreResponse
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.services.score_service import ScoreService

router = APIRouter()
logger = logging.getLogger(__name__)

def get_score_service(db: AsyncSession = Depends(get_db)):
    repo = ScoreRepository(db)
    return ScoreService(repo)


# =========================================================
# Macro Score
# =========================================================
@router.get("/score/macro")
async def get_macro_score(
    current_user: dict = Depends(get_current_user),
    service: ScoreService = Depends(get_score_service)
):
    try:
        user_id = current_user["id"]
        return await service.get_macro_score(user_id=user_id)
    except Exception as e:
        logger.error(f"❌ /score/macro: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Fout bij ophalen macro-score")


# =========================================================
# Technical Score
# =========================================================
@router.get("/score/technical")
async def get_technical_score(
    current_user: dict = Depends(get_current_user),
    service: ScoreService = Depends(get_score_service)
):
    try:
        user_id = current_user["id"]
        return await service.get_technical_score(user_id=user_id)
    except Exception as e:
        logger.error(f"❌ /score/technical: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Fout bij ophalen technische score")


# =========================================================
# Market Score
# =========================================================
@router.get("/score/market")
async def get_market_score(
    current_user: dict = Depends(get_current_user),
    service: ScoreService = Depends(get_score_service)
):
    try:
        user_id = current_user["id"]
        return await service.get_market_score(user_id=user_id)
    except Exception as e:
        logger.error(f"❌ /score/market: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Fout bij ophalen market-score")


# =========================================================
# Daily Combined Score (Dashboard)
# =========================================================
@router.get("/scores/daily", response_model=DailyCombinedScoreResponse)
async def get_daily_scores(
    current_user: dict = Depends(get_current_user),
    service: ScoreService = Depends(get_score_service)
):
    try:
        user_id = current_user["id"]
        return await service.get_daily_scores(user_id=user_id)
    except Exception as e:
        logger.error(f"❌ Fout bij /scores/daily: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Fout bij ophalen daily scores")


# =========================================================
# AI Master Score — uit ai_category_insights (user-specific)
# =========================================================
@router.get("/ai/master_score", response_model=MasterScoreResponse)
async def get_ai_master_score(
    current_user: dict = Depends(get_current_user),
    service: ScoreService = Depends(get_score_service)
):
    try:
        user_id = current_user["id"]
        return await service.get_master_score(user_id=user_id)
    except Exception as e:
        logger.error(f"❌ Fout bij ophalen AI Master Score: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Fout bij ophalen master score")
