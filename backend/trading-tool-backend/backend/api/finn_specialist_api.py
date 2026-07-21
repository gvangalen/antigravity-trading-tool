import json
from typing import Any, Type, TypeVar

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_db
from backend.schemas.finn_specialist_schema import IndicatorContextRequest, WorkspaceContextRequest
from backend.services.finn_specialist_service import FinnSpecialistService
from backend.services.finn_workspace_specialist_service import FinnWorkspaceSpecialistService
from backend.utils.auth_utils import get_current_user


router = APIRouter()
RequestModel = TypeVar("RequestModel", bound=BaseModel)


def _parse_specialist_payload(payload: Any, model: Type[RequestModel]) -> RequestModel:
    """Accept one legacy JSON-string layer while clients roll to the object contract."""
    candidate = payload
    if isinstance(candidate, str):
        try:
            candidate = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail="Request body must be a JSON object.") from exc

    if not isinstance(candidate, dict):
        raise HTTPException(status_code=422, detail="Request body must be a JSON object.")

    try:
        return model.parse_obj(candidate)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


@router.post("/finn/specialists/indicator-context")
async def get_indicator_context(
    raw_payload: Any = Body(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payload = _parse_specialist_payload(raw_payload, IndicatorContextRequest)
    result = await FinnSpecialistService(db).explain_indicator(
        user_id=int(current_user["id"]),
        user_email=current_user.get("email"),
        symbol=payload.symbol,
        category=payload.category,
        indicator=payload.indicator,
        period=payload.period,
        timeframe=payload.timeframe,
        locale=payload.locale,
    )
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=result)
    return result


@router.post("/finn/specialists/workspace-context")
async def get_workspace_context(
    raw_payload: Any = Body(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payload = _parse_specialist_payload(raw_payload, WorkspaceContextRequest)
    result = await FinnWorkspaceSpecialistService(db).explain(
        user_id=int(current_user["id"]),
        user_email=current_user.get("email"),
        subject_type=payload.subject_type,
        subject_id=payload.subject_id,
        symbol=payload.symbol,
        timeframe=payload.timeframe,
        period=payload.period,
        locale=payload.locale,
    )
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=result)
    return result
