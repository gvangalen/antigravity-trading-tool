import os
import logging
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Depends

from backend.utils.auth_utils import get_current_user
from backend.services.system_service import SystemService
from backend.schemas.system_schema import BootstrapAgentsResponse

logger = logging.getLogger(__name__)
router = APIRouter()

dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(dotenv_path=dotenv_path)

logger.info("⚙️ system_api.py geladen – System endpoints (Clean Architecture).")

# =====================================================
# 🚀 BOOTSTRAP AGENTS (na onboarding)
# =====================================================
@router.post("/system/bootstrap-agents", response_model=BootstrapAgentsResponse)
async def bootstrap_agents(current_user=Depends(get_current_user)):
    """
    Triggers the background initialization of AI agents for a newly onboarded user.
    """
    try:
        user_id = current_user["id"]
        logger.info(f"🚀 API Request: Bootstrap agents gestart voor user {user_id}")

        result = await SystemService.bootstrap_agents_for_user(user_id)
        return result

    except Exception as e:
        logger.exception(f"❌ Bootstrap agents mislukt voor user: {e}")
        raise HTTPException(
            status_code=500,
            detail="Bootstrap agents starten mislukt",
        )
