import logging
import uuid
import time
import collections
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks, Request
from sqlalchemy.ext.asyncio import AsyncSession

class InMemoryRateLimiter:
    def __init__(self, requests_limit: int, window_seconds: int):
        self.requests_limit = requests_limit
        self.window_seconds = window_seconds
        self.history = collections.defaultdict(list)

    def check_rate_limit(self, identifier: str):
        now = time.time()
        # Clean old timestamps
        self.history[identifier] = [t for t in self.history[identifier] if now - t < self.window_seconds]
        if len(self.history[identifier]) >= self.requests_limit:
            logger.warning(f"🛑 Rate limit exceeded for identifier: {identifier}")
            raise HTTPException(
                status_code=429,
                detail="Te veel verzoeken. Gelieve een minuut te wachten voor u nieuwe vragen stelt."
            )
        self.history[identifier].append(now)

# Limit user queries to max 6 queries or streams per minute (IP and User ID bounded)
chat_rate_limiter = InMemoryRateLimiter(requests_limit=6, window_seconds=60)

from typing import List
from sqlalchemy import select
from backend.infrastructure.database import get_db
from backend.utils.auth_utils import get_current_user
from backend.infrastructure.models import ChatSession, ChatMessage
from backend.schemas.assistant_schema import (
    AssistantActionExecuteRequest,
    AssistantActionExecuteResponse,
    AssistantChatRequest,
    AssistantChatResponse,
    AssistantPreferences,
    AssistantPreferenceUpdate,
    AssistantInsightResponse,
    ChatSessionResponse,
    ChatMessageResponse,
    ChatSessionDetailResponse,
)
from backend.services.ai_assistant_service import AiAssistantService
from backend.services.finn_plan_service import FinnPlanService
from backend.services.ai_gateway import AiGateway
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.infrastructure.repositories.setup_repository import SetupRepository
from backend.infrastructure.repositories.report_repository import ReportRepository
from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
from backend.infrastructure.repositories.strategy_repository import StrategyRepository
from backend.infrastructure.repositories.conversation_state_repository import ConversationStateRepository
from backend.infrastructure.repositories.assistant_context_repository import AssistantContextRepository

router = APIRouter()
logger = logging.getLogger(__name__)

async def get_assistant_service(db: AsyncSession = Depends(get_db)):
    score_repo = ScoreRepository(db)
    setup_repo = SetupRepository(db)
    report_repo = ReportRepository(db)
    bot_repo = BotRepository(db)
    user_repo = UserRepository(db)
    market_data_repo = MarketDataRepository(db)
    strategy_repo = StrategyRepository(db)
    state_repo = ConversationStateRepository(db)
    context_repo = AssistantContextRepository(db)
    ai_gateway = AiGateway(user_repo, score_repo)
    return AiAssistantService(
        score_repo, setup_repo, report_repo, bot_repo, user_repo, 
        market_data_repo, strategy_repo, state_repo, ai_gateway, context_repo
    )
@router.post("/assistant/chat", response_model=AssistantChatResponse)
async def assistant_chat(
    request: AssistantChatRequest,
    raw_request: Request,
    x_trace_id: Optional[str] = Header(None),
    current_user: dict = Depends(get_current_user),
    service: AiAssistantService = Depends(get_assistant_service),
    db: AsyncSession = Depends(get_db),
):
    trace_id = x_trace_id or f"trdm-trace-{uuid.uuid4().hex[:8]}-{hex(int(time.time()))[2:]}"
    try:
        user_id = current_user["id"]
        ip_addr = raw_request.client.host if raw_request.client else "unknown"
        
        # Apply Rate Limiting
        chat_rate_limiter.check_rate_limit(f"user_{user_id}")
        chat_rate_limiter.check_rate_limit(f"ip_{ip_addr}")
        context_payload = request.context.dict(exclude_none=True) if hasattr(request.context, "dict") else (request.context or {})
        finn = FinnPlanService(db)
        if finn.looks_like_plan_request(request.query, context_payload.get("finn_draft")):
            return AssistantChatResponse(**finn.build_response(request.query, context_payload))

        response, action, draft, state, reasoning, suggested_actions, actual_session_id = await service.get_chat_response(
            user_id, request.query, request.history, request.context, trace_id=trace_id, session_id=request.session_id
        )
        intent = service._classify_intent(request.query)
        if not isinstance(action, dict):
            action = None
        if not isinstance(draft, dict):
            draft = None
        if not isinstance(state, dict):
            state = None
        if not isinstance(reasoning, dict):
            reasoning = None
        if not isinstance(suggested_actions, list):
            suggested_actions = None
        return AssistantChatResponse(
            response=response,
            intent=intent,
            action=action,
            draft=draft,
            state=state,
            reasoning=reasoning,
            suggested_actions=suggested_actions,
            trace_id=trace_id,
            session_id=actual_session_id
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ AI Assistant Chat Error: {e} | Trace: {trace_id}", exc_info=True)
        raise HTTPException(status_code=500, detail="Fout bij AI Assistant")

# =====================================================
# Chat Sessions REST endpoints
# =====================================================

@router.get("/assistant/sessions", response_model=List[ChatSessionResponse])
async def list_chat_sessions(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        user_id = current_user["id"]
        # Fetch sessions ordered by updated_at desc
        stmt = select(ChatSession).where(ChatSession.user_id == user_id).order_by(ChatSession.updated_at.desc())
        res = await db.execute(stmt)
        sessions = res.scalars().all()
        return sessions
    except Exception as e:
        logger.exception("❌ Error opvragen chatsessies")
        raise HTTPException(status_code=500, detail="Fout bij ophalen chatsessies")


@router.get("/assistant/sessions/{session_id}", response_model=ChatSessionDetailResponse)
async def get_chat_session_detail(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        user_id = current_user["id"]
        # Fetch session
        stmt = select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
        res = await db.execute(stmt)
        session = res.scalars().first()
        if not session:
            raise HTTPException(status_code=404, detail="Chatsessie niet gevonden")
        
        # Fetch messages ordered chronologically
        msg_stmt = select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc())
        msg_res = await db.execute(msg_stmt)
        messages = msg_res.scalars().all()
        
        return ChatSessionDetailResponse(session=session, messages=messages)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"❌ Error opvragen chatsessie {session_id}")
        raise HTTPException(status_code=500, detail="Fout bij ophalen chatsessie details")


@router.delete("/assistant/sessions/{session_id}")
async def delete_chat_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        user_id = current_user["id"]
        # Verify ownership
        stmt = select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
        res = await db.execute(stmt)
        session = res.scalars().first()
        if not session:
            raise HTTPException(status_code=404, detail="Chatsessie niet gevonden")
        
        # Delete session (will cascade delete messages due to Foreign Key ON DELETE CASCADE)
        await db.delete(session)
        await db.commit()
        return {"status": "ok", "message": "Chathistorie succesvol gewist"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"❌ Error verwijderen chatsessie {session_id}")
        raise HTTPException(status_code=500, detail="Fout bij verwijderen chatsessie")


from fastapi.responses import StreamingResponse
import json

@router.post("/assistant/chat/stream")
async def assistant_chat_stream(
    request: AssistantChatRequest,
    background_tasks: BackgroundTasks,
    raw_request: Request,
    x_trace_id: Optional[str] = Header(None),
    current_user: dict = Depends(get_current_user),
    service: AiAssistantService = Depends(get_assistant_service)
):
    """
    ⚡ Real-Time SSE Stream for AI Assistant Chat (Fase 3 Lightweight)
    """
    user_id = current_user["id"]
    ip_addr = raw_request.client.host if raw_request.client else "unknown"

    # Apply Rate Limiting
    chat_rate_limiter.check_rate_limit(f"user_{user_id}")
    chat_rate_limiter.check_rate_limit(f"ip_{ip_addr}")

    trace_id = x_trace_id or f"trdm-trace-{uuid.uuid4().hex[:8]}-{hex(int(time.time()))[2:]}"

    async def event_generator():
        try:
            async for chunk in service.get_chat_response_stream(
                user_id, request.query, request.history, request.context,
                trace_id=trace_id, background_tasks=background_tasks
            ):
                # Hardened early client disconnect cleanup
                if await raw_request.is_disconnected():
                    logger.warning(f"🔌 Client disconnected mid-stream | Trace: {trace_id}. Aborting stream generator.")
                    break

                event_name = chunk["event"]
                data_val = chunk["data"]
                
                # Inject trace_id into envelope payload so frontend has it immediately
                if event_name == "envelope" and isinstance(data_val, dict):
                    data_val["trace_id"] = trace_id
                
                if isinstance(data_val, dict):
                    data_str = json.dumps(data_val)
                else:
                    data_str = str(data_val)
                    
                yield f"event: {event_name}\ndata: {data_str}\n\n"
        except Exception as e:
            logger.error(f"❌ Error in SSE assistant stream generator | Trace: {trace_id}: {e}", exc_info=True)
            err_payload = json.dumps({"response": "⚠️ Externe stream fout opgetreden. Klik op retry.", "trace_id": trace_id})
            yield f"event: error\ndata: {err_payload}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.get("/assistant/preferences", response_model=AssistantPreferences)
async def get_preferences(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(current_user["id"])
    prefs = getattr(user, "ai_preferences", {}) or {}
    # Inject first_name for UI greeting persistence
    if user.first_name:
        prefs["first_name"] = user.first_name
    return AssistantPreferences(preferences=prefs)

@router.patch("/assistant/preferences", response_model=AssistantPreferences)
async def update_preferences(
    request: AssistantPreferenceUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    user_repo = UserRepository(db)
    updates = {k: v for k, v in request.dict().items() if v is not None}
    user = await user_repo.update_ai_preferences(current_user["id"], updates)
    return AssistantPreferences(preferences=user.ai_preferences)

@router.post("/assistant/insight", response_model=AssistantInsightResponse)
async def get_insight(
    context: dict,
    current_user: dict = Depends(get_current_user),
    service: AiAssistantService = Depends(get_assistant_service)
):
    try:
        user_id = current_user["id"]
        insight = await service.get_assistant_insight(user_id, context)
        return AssistantInsightResponse(
            greeting=insight.get("greeting", "Hoi!"),
            bot_insight=insight.get("bot_insight"),
            market_insight=insight.get("market_insight"),
            context_detected=context
        )
    except Exception as e:
        logger.error(f"❌ AI Assistant Insight Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Fout bij AI Insight")


from backend.services.ai_action_engine import AiActionEngine

async def get_ai_action_engine(db: AsyncSession = Depends(get_db)):
    return AiActionEngine(db)

@router.post("/assistant/actions/execute")
async def execute_pending_action(
    payload: dict,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    engine: AiActionEngine = Depends(get_ai_action_engine),
):
    if payload.get("action"):
        try:
            finn = FinnPlanService(db)
            return await finn.execute_action(current_user["id"], payload["action"])
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ AI Assistant Action Error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Fout bij Finn action")

    action_id = payload.get("action_id")
    if not action_id:
        raise HTTPException(status_code=400, detail="Action ID is verplicht.")
    
    user_id = current_user["id"]
    return await engine.execute_pending_action(action_id, user_id)
