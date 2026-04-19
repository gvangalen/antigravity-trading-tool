import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_db
from backend.utils.auth_utils import get_current_user
from backend.engine.backtest_engine import run_bot_backtest

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/backtest/bot/{bot_id}")
async def start_bot_backtest(
    bot_id: int,
    scenario: str = "default",
    current_user: dict = Depends(get_current_user)
):
    """
    Endpoint to run a backtest for a specific bot with optional scenario.
    """
    user_id = current_user["id"]
    
    # Run backtest (sync engine)
    result = run_bot_backtest(user_id=user_id, bot_id=bot_id, days=30, scenario=scenario)
    
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Backtest failed"))
        
    return result
