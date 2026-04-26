import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from celery.result import AsyncResult

from backend.infrastructure.database import get_db
from backend.utils.auth_utils import get_current_user
from backend.celery_task.celery_app import celery_app
from backend.services.agent_service import AgentService
from backend.schemas.agent_schema import AgentInsightResponse, AgentReflectionResponse, CeleryTaskResponse

logger = logging.getLogger(__name__)
router = APIRouter()

async def get_agent_service(db: AsyncSession = Depends(get_db)):
    return AgentService(db)

# ============================================================
# DYNAMIC CATEGORY AGENT INSIGHTS & REFLECTIONS
# ============================================================
# Categories: macro, market, technical, setup, strategy
# This single parameterized route replaces 10 specific routes!

@router.get("/agents/insights/{category}", response_model=AgentInsightResponse)
async def get_agent_insight(
    category: str,
    current_user: dict = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service)
):
    valid_categories = ["macro", "market", "technical", "setup", "strategy"]
    if category not in valid_categories:
        raise HTTPException(status_code=404, detail="Ongeldige categorie")
        
    return await service.get_insights(current_user["id"], category)


@router.get("/agents/reflections/{category}", response_model=AgentReflectionResponse)
async def get_agent_reflections(
    category: str,
    current_user: dict = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service)
):
    valid_categories = ["macro", "market", "technical", "setup", "strategy"]
    if category not in valid_categories:
        raise HTTPException(status_code=404, detail="Ongeldige categorie")
        
    return await service.get_reflections(current_user["id"], category)


# ============================================================
# TASK STATUS (CELERY)
# ============================================================
@router.get("/tasks/{task_id}", response_model=CeleryTaskResponse)
async def get_task_status(
    task_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        result = AsyncResult(task_id, app=celery_app)

        response = {
            "task_id": task_id,
            "state": result.state,
        }

        if result.state == "SUCCESS":
            response["result"] = result.result
        elif result.state == "FAILURE":
            response["error"] = str(result.result)

        return response

    except Exception:
        logger.exception("Task status fout")
        raise HTTPException(status_code=500, detail="Task status ophalen mislukt")
