import logging
from fastapi import APIRouter, HTTPException, Depends
from celery.result import AsyncResult

from backend.utils.auth_utils import get_current_user
from backend.celery_task.celery_app import celery_app
from backend.schemas.task_schema import CeleryTaskResponse

logger = logging.getLogger(__name__)
router = APIRouter()

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
