import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_db
from backend.utils.auth_utils import get_current_user
from backend.schemas.score_schema import DailyCombinedScoreResponse, MasterScoreResponse, IntelligenceWeightsRequest
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.services.score_service import ScoreService

router = APIRouter()
logger = logging.getLogger(__name__)

async def get_score_service(db: AsyncSession = Depends(get_db)):
    repo = ScoreRepository(db)
    user_repo = UserRepository(db)
    return ScoreService(repo, user_repo)


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
    symbol: str = "BTC",
    current_user: dict = Depends(get_current_user),
    service: ScoreService = Depends(get_score_service)
):
    try:
        user_id = current_user["id"]
        return await service.get_daily_scores(user_id=user_id, symbol=symbol)
    except Exception as e:
        logger.error(f"❌ Fout bij /scores/daily ({symbol}): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Fout bij ophalen daily scores")


# =========================================================
# Score History (Analytics)
# =========================================================
@router.get("/scores/history")
async def get_score_history(
    days: int = 30,
    symbol: str = "BTC",
    current_user: dict = Depends(get_current_user),
    service: ScoreService = Depends(get_score_service)
):
    try:
        user_id = current_user["id"]
        return await service.get_score_history(user_id=user_id, days=days, symbol=symbol)
    except Exception as e:
        logger.error(f"❌ Fout bij /scores/history ({symbol}): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Fout bij ophalen score historie")


# =========================================================
# Update Intelligence Weights
# =========================================================
@router.post("/user/intelligence-weights")
async def update_intelligence_weights(
    req: IntelligenceWeightsRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        user_id = current_user["id"]
        user_repo = UserRepository(db)
        await user_repo.update_ai_preferences(user_id, {"intelligence_weights": req.weights})
        return {"status": "success", "message": "Wegingen bijgewerkt"}
    except Exception as e:
        logger.error(f"❌ Fout bij update_intelligence_weights: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Fout bij opslaan wegingen")


# =========================================================
# AI Master Score — uit ai_category_insights (user-specific)
# =========================================================
@router.get("/ai/master_score", response_model=MasterScoreResponse)
async def get_ai_master_score(
    symbol: str = "BTC",
    current_user: dict = Depends(get_current_user),
    service: ScoreService = Depends(get_score_service)
):
    try:
        user_id = current_user["id"]
        return await service.get_master_score(user_id=user_id, symbol=symbol)
    except Exception as e:
        logger.error(f"❌ Fout bij ophalen AI Master Score: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Fout bij ophalen master score")
