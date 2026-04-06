import logging
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_db
from backend.utils.auth_utils import get_current_user
from backend.schemas.onboarding_schema import StepRequest, OnboardingStatusResponse
from backend.infrastructure.repositories.onboarding_repository import OnboardingRepository
from backend.services.onboarding_service import OnboardingService

router = APIRouter()
logger = logging.getLogger("onboarding")

def get_onboarding_service(db: AsyncSession = Depends(get_db)):
    repo = OnboardingRepository(db)
    return OnboardingService(repo)

# =====================================================
# Routes
# =====================================================

@router.get("/onboarding/status", response_model=OnboardingStatusResponse)
async def get_onboarding_status(
    request: Request,
    service: OnboardingService = Depends(get_onboarding_service),
    current_user: dict = Depends(get_current_user),
):
    try:
        user_id = current_user["id"]
        return await service.get_status_dict(user_id)
    except Exception as e:
        logger.exception("❌ Error opvragen onboarding status")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/onboarding/complete_step", response_model=OnboardingStatusResponse)
async def complete_step(
    payload: StepRequest,
    service: OnboardingService = Depends(get_onboarding_service),
    current_user: dict = Depends(get_current_user),
):
    try:
        user_id = current_user["id"]
        return await service.complete_step(user_id, payload.step)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("❌ Error voltooien onboarding step")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/onboarding/finish", response_model=OnboardingStatusResponse)
async def finish_onboarding(
    service: OnboardingService = Depends(get_onboarding_service),
    current_user: dict = Depends(get_current_user),
):
    try:
        user_id = current_user["id"]
        return await service.finish_onboarding(user_id)
    except Exception as e:
        logger.exception("❌ Error afronden onboarding pipeline")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/onboarding/reset", response_model=OnboardingStatusResponse)
async def reset_onboarding(
    service: OnboardingService = Depends(get_onboarding_service),
    current_user: dict = Depends(get_current_user),
):
    try:
        user_id = current_user["id"]
        return await service.reset_onboarding(user_id)
    except Exception as e:
        logger.exception("❌ Error resetten onboarding")
        raise HTTPException(status_code=500, detail="Internal Server Error")
