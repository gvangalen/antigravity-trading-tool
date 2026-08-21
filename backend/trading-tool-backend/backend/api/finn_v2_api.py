from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_db
from backend.schemas.finn_v2_schema import (
    AgentRunCancelResponse,
    AgentRunRequest,
    AgentRunStatusEnvelope,
)
from backend.services.finn_v2_gateway_service import FinnV2GatewayService
from backend.services.finn_v2_run_service import FinnV2RunService
from backend.utils.auth_utils import get_current_user


router = APIRouter()


def get_gateway_service(db: AsyncSession = Depends(get_db)) -> FinnV2GatewayService:
    return FinnV2GatewayService(db)


def get_run_service(db: AsyncSession = Depends(get_db)) -> FinnV2RunService:
    return FinnV2RunService(db)


def _sse(event_name: str, payload: dict) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload, default=str)}\n\n"


@router.post("/assistant/v2/runs", response_model=AgentRunStatusEnvelope)
async def create_finn_v2_run(
    request: AgentRunRequest,
    raw_request: Request,
    current_user: dict = Depends(get_current_user),
    gateway: FinnV2GatewayService = Depends(get_gateway_service),
    run_service: FinnV2RunService = Depends(get_run_service),
):
    run_id = await gateway.run_foundation_now(
        user_id=int(current_user["id"]),
        request_payload=request.dict(),
        request_path=raw_request.url.path,
        request_id=getattr(raw_request.state, "trace_id", None),
        trace_id=getattr(raw_request.state, "trace_id", None),
    )
    run = await gateway.get_run(run_id=run_id, user_id=int(current_user["id"]))
    return await run_service.envelope_from_run(run)


@router.get("/assistant/v2/runs/{run_id}", response_model=AgentRunStatusEnvelope)
async def get_finn_v2_run(
    run_id: str,
    current_user: dict = Depends(get_current_user),
    gateway: FinnV2GatewayService = Depends(get_gateway_service),
    run_service: FinnV2RunService = Depends(get_run_service),
):
    run = await gateway.get_run(run_id=run_id, user_id=int(current_user["id"]))
    return await run_service.envelope_from_run(run)


@router.post("/assistant/v2/runs/{run_id}/cancel", response_model=AgentRunCancelResponse)
async def cancel_finn_v2_run(
    run_id: str,
    current_user: dict = Depends(get_current_user),
    gateway: FinnV2GatewayService = Depends(get_gateway_service),
    run_service: FinnV2RunService = Depends(get_run_service),
):
    run = await gateway.get_run(run_id=run_id, user_id=int(current_user["id"]))
    if run.status in {"completed", "blocked", "failed", "canceled"}:
        raise HTTPException(status_code=409, detail="FINN V2 run is already terminal")
    await run_service.cancel_run(run_id=run_id, user_id=int(current_user["id"]))
    refreshed = await gateway.get_run(run_id=run_id, user_id=int(current_user["id"]))
    return AgentRunCancelResponse(run=await run_service.envelope_from_run(refreshed))


@router.get("/assistant/v2/runs/{run_id}/stream")
async def stream_finn_v2_run(
    run_id: str,
    raw_request: Request,
    current_user: dict = Depends(get_current_user),
    gateway: FinnV2GatewayService = Depends(get_gateway_service),
    run_service: FinnV2RunService = Depends(get_run_service),
):
    async def event_generator() -> AsyncGenerator[str, None]:
        last_status = None
        while True:
            run = await gateway.get_run(run_id=run_id, user_id=int(current_user["id"]))
            envelope = await run_service.envelope_from_run(run)
            if envelope.status != last_status:
                yield _sse(f"run.{envelope.status}", envelope.dict())
                last_status = envelope.status
            if envelope.status in {"completed", "blocked", "failed", "canceled"}:
                return
            if await raw_request.is_disconnected():
                return
            await asyncio.sleep(0.1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
