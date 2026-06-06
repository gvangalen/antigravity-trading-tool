import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_db
from backend.utils.auth_utils import get_current_user

from backend.schemas.indicator_config_schema import (
    IndicatorConfigResponse,
    IndicatorSettingsUpdate,
    IndicatorCustomRulesSave,
    IndicatorResetPayload
)
from backend.infrastructure.repositories.indicator_config_repository import IndicatorConfigRepository
from backend.services.indicator_config_service import IndicatorConfigService

router = APIRouter()
logger = logging.getLogger(__name__)

async def get_indicator_config_service(db: AsyncSession = Depends(get_db)):
    repo = IndicatorConfigRepository(db)
    return IndicatorConfigService(repo)

# =========================================================
# ✅ 1) GET indicator config (USER override + template fallback)
# =========================================================
@router.get("/indicator_config/{category}/{indicator}", response_model=IndicatorConfigResponse)
async def get_indicator_config(
    category: str,
    indicator: str,
    current_user: dict = Depends(get_current_user),
    service: IndicatorConfigService = Depends(get_indicator_config_service)
):
    try:
        user_id = current_user["id"]
        col_res = await service.get_indicator_config(category, indicator, user_id)
        return col_res
    except ValueError as e:
        logger.warning("⚠️ Ongeldige indicator config request: %s", e)
        raise HTTPException(status_code=400, detail="Ongeldige indicator-configuratie.")
    except Exception as e:
        logger.exception("❌ Error getting indicator config")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# =========================================================
# ✅ 2) UPDATE mode + weight (USER ONLY)
# =========================================================
@router.put("/indicator_config/settings")
async def update_indicator_settings(
    payload: IndicatorSettingsUpdate,
    current_user: dict = Depends(get_current_user),
    service: IndicatorConfigService = Depends(get_indicator_config_service)
):
    try:
        user_id = current_user["id"]
        await service.update_indicator_settings(
            category=payload.category,
            indicator=payload.indicator,
            user_id=user_id,
            score_mode=payload.score_mode,
            weight=payload.weight
        )
        return {"ok": True, "indicator": payload.indicator}
    except ValueError as e:
        logger.warning("⚠️ Ongeldige indicator settings update: %s", e)
        raise HTTPException(status_code=400, detail="Ongeldige indicator-instellingen.")
    except Exception as e:
        logger.exception("❌ Error updating indicator settings")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# =========================================================
# ✅ 3) SAVE custom rules (USER ONLY)
# =========================================================
@router.post("/indicator_config/custom")
async def save_custom_rules(
    payload: IndicatorCustomRulesSave,
    current_user: dict = Depends(get_current_user),
    service: IndicatorConfigService = Depends(get_indicator_config_service)
):
    try:
        user_id = current_user["id"]
        await service.save_custom_rules(
            category=payload.category,
            indicator=payload.indicator,
            user_id=user_id,
            rules=payload.rules,
            weight=payload.weight
        )
        return {"ok": True}
    except ValueError as e:
        logger.warning("⚠️ Ongeldige indicator rules save: %s", e)
        raise HTTPException(status_code=400, detail="Ongeldige indicatorregels.")
    except Exception as e:
        logger.exception("❌ Error saving custom rules")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# =========================================================
# ✅ 4) RESET → verwijder user override
# =========================================================
@router.post("/indicator_config/reset")
async def reset_indicator_rules(
    payload: IndicatorResetPayload,
    current_user: dict = Depends(get_current_user),
    service: IndicatorConfigService = Depends(get_indicator_config_service)
):
    try:
        user_id = current_user["id"]
        await service.reset_indicator_rules(
            category=payload.category,
            indicator=payload.indicator,
            user_id=user_id
        )
        return {"ok": True}
    except ValueError as e:
        logger.warning("⚠️ Ongeldige indicator reset request: %s", e)
        raise HTTPException(status_code=400, detail="Ongeldige reset-aanvraag.")
    except Exception as e:
        logger.exception("❌ Error resetting indicator rules")
        raise HTTPException(status_code=500, detail="Internal Server Error")
