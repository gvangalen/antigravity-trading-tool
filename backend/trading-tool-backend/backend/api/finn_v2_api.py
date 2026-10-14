from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.finn_v2_contract import is_terminal_status
from backend.domain.finn_v2_runtime_contract import RuntimeContractConflictError
from backend.infrastructure.database import async_session_factory, get_db
from backend.infrastructure.models import FinnV2Conversation, FinnV2Run
from backend.infrastructure.repositories.finn_v2_runtime_contract_repository import FinnV2RuntimeContractRepository
from backend.schemas.finn_v2_schema import (
    AgentRunCancelResponse,
    AgentRunRequest,
    AgentRunStatusEnvelope,
)
from backend.services.finn_v2_gateway_service import FinnV2GatewayService
from backend.services.finn_v2_run_service import FinnV2RunService
from backend.utils.auth_utils import get_current_user


router = APIRouter()


@router.get("/assistant/v2/conversations")
async def list_finn_v2_conversations(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List only the owner's visible FINN 2.0 conversations."""
    user_id = int(current_user["id"])
    rows = (await db.execute(
        select(FinnV2Conversation)
        .where(FinnV2Conversation.user_id == user_id)
        .order_by(FinnV2Conversation.updated_at.desc())
        .limit(20)
    )).scalars().all()
    result = []
    for row in rows:
        first_run = (await db.execute(
            select(FinnV2Run.message)
            .where(
                FinnV2Run.user_id == user_id,
                FinnV2Run.conversation_id == row.id,
                FinnV2Run.visibility == "visible",
            )
            .order_by(FinnV2Run.created_at.asc())
            .limit(1)
        )).scalar_one_or_none()
        if first_run is None:
            continue
        # V2 rows still carry a legacy internal placeholder title. The first
        # visible user turn is the readable conversation title.
        title = str(first_run or "FINN gesprek").strip()
        result.append({"id": row.id, "title": title[:88], "updated_at": row.updated_at})
    return result


@router.get("/assistant/v2/conversations/{conversation_id}")
async def get_finn_v2_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return visible text only; old proposals never regain a confirm button."""
    user_id = int(current_user["id"])
    row = (await db.execute(
        select(FinnV2Conversation).where(
            FinnV2Conversation.id == conversation_id,
            FinnV2Conversation.user_id == user_id,
        )
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="FINN gesprek niet gevonden")
    runs = (await db.execute(
        select(FinnV2Run)
        .where(
            FinnV2Run.user_id == user_id,
            FinnV2Run.conversation_id == conversation_id,
            FinnV2Run.visibility == "visible",
        )
        .order_by(FinnV2Run.created_at.asc())
        .limit(100)
    )).scalars().all()
    messages = []
    for run in runs:
        if run.message and run.message != "[redacted by finn_v2_retention]":
            messages.append({"role": "user", "content": run.message})
        response = run.response_json or {}
        content = response.get("content") if isinstance(response, dict) else None
        if isinstance(content, str) and content.strip():
            messages.append({"role": "assistant", "content": content})
    return {"id": row.id, "messages": messages}

# Prevent proxy buffering from hiding the terminal event or keeping a closed
# generator observable as an open client stream.
_SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def get_gateway_service(db: AsyncSession = Depends(get_db)) -> FinnV2GatewayService:
    return FinnV2GatewayService(db)


def get_run_service(db: AsyncSession = Depends(get_db)) -> FinnV2RunService:
    return FinnV2RunService(db)


def _sse(event_name: str, payload: dict) -> str:
    # Match FastAPI's polling response encoding exactly; ``default=str``
    # serializes datetimes with a space and caused transport-only drift.
    return f"event: {event_name}\ndata: {json.dumps(jsonable_encoder(payload))}\n\n"


async def _load_run_envelope(*, run_id: str, user_id: int) -> AgentRunStatusEnvelope:
    """Build a transport envelope without retaining a DB session across SSE waits."""
    async with async_session_factory() as session:
        gateway = FinnV2GatewayService(session)
        run_service = FinnV2RunService(session)
        run = await gateway.get_run(run_id=run_id, user_id=user_id)
        return await run_service.envelope_from_run(run)


@router.post("/assistant/v2/runs", response_model=AgentRunStatusEnvelope)
async def create_finn_v2_run(
    request: AgentRunRequest,
    raw_request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
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
    envelope = await run_service.envelope_from_run(run)
    # The creation response is the sole nonterminal transport that needs this
    # metadata. Bounded polling therefore does not add a contract query for
    # every progress update.
    runtime_contract = await FinnV2RuntimeContractRepository(db).get_for_run(run_id=run_id)
    if runtime_contract is None:
        raise HTTPException(status_code=500, detail="runtime_contract_missing_after_run_creation")
    envelope.runtime_trace = {
        "contract": {
            "contract_id": runtime_contract.contract_id,
            "contract_version": runtime_contract.contract_version,
            "revision": runtime_contract.revision,
            "run_id": run.id,
            "conversation_id": run.conversation_id,
        }
    }
    return envelope


@router.get("/assistant/v2/runs/{run_id}", response_model=AgentRunStatusEnvelope)
async def get_finn_v2_run(
    run_id: str,
    current_user: dict = Depends(get_current_user),
):
    return await _load_run_envelope(run_id=run_id, user_id=int(current_user["id"]))


@router.post("/assistant/v2/runs/{run_id}/cancel", response_model=AgentRunCancelResponse)
async def cancel_finn_v2_run(
    run_id: str,
    current_user: dict = Depends(get_current_user),
    gateway: FinnV2GatewayService = Depends(get_gateway_service),
    run_service: FinnV2RunService = Depends(get_run_service),
):
    run = await gateway.get_run(run_id=run_id, user_id=int(current_user["id"]))
    if is_terminal_status(run.status):
        raise HTTPException(status_code=409, detail="FINN V2 run is already terminal")
    try:
        await run_service.cancel_run(run_id=run_id, user_id=int(current_user["id"]))
    except RuntimeContractConflictError as exc:
        # A terminal worker result won after the first status read. The client
        # can GET that authoritative result instead of displaying a local Stop.
        if str(exc) != "runtime_contract_already_terminal":
            raise
        raise HTTPException(status_code=409, detail="FINN V2 run is already terminal") from exc
    refreshed = await gateway.get_run(run_id=run_id, user_id=int(current_user["id"]))
    return AgentRunCancelResponse(run=await run_service.envelope_from_run(refreshed))


@router.get("/assistant/v2/runs/{run_id}/stream")
async def stream_finn_v2_run(
    run_id: str,
    raw_request: Request,
    current_user: dict = Depends(get_current_user),
):
    async def event_generator() -> AsyncGenerator[str, None]:
        last_status = None
        while True:
            if await raw_request.is_disconnected():
                return

            envelope = await _load_run_envelope(run_id=run_id, user_id=int(current_user["id"]))
            if envelope.status != last_status:
                yield _sse(f"run.{envelope.status}", envelope.dict())
                last_status = envelope.status
            if is_terminal_status(envelope.status):
                return
            await asyncio.sleep(0.1)

    return StreamingResponse(
        event_generator(), media_type="text/event-stream", headers=_SSE_HEADERS,
    )
