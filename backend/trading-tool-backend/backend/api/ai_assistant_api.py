import logging
import uuid
import time
import collections
from typing import Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks, Request
from sqlalchemy.ext.asyncio import AsyncSession

class InMemoryRateLimiter:
    def __init__(self, requests_limit: int, window_seconds: int):
        self.requests_limit = requests_limit
        self.window_seconds = window_seconds
        self.history = collections.defaultdict(list)

    def check_rate_limit(self, identifier: str, *, limit: Optional[int] = None, window_seconds: Optional[int] = None):
        now = time.time()
        active_limit = limit or self.requests_limit
        active_window = window_seconds or self.window_seconds
        # Clean old timestamps
        self.history[identifier] = [t for t in self.history[identifier] if now - t < active_window]
        if len(self.history[identifier]) >= active_limit:
            logger.warning(f"🛑 Rate limit exceeded for identifier: {identifier}")
            retry_after = max(1, int(active_window - (now - self.history[identifier][0]))) if self.history[identifier] else active_window
            raise HTTPException(
                status_code=429,
                detail="Te veel verzoeken. Wacht kort en probeer opnieuw.",
                headers={"Retry-After": str(retry_after)},
            )
        self.history[identifier].append(now)

# Primary assistant limits. Authenticated Finn users get enough room for
# multi-turn draft repair, while anonymous/IP fallback remains stricter.
chat_rate_limiter = InMemoryRateLimiter(requests_limit=30, window_seconds=60)
ASSISTANT_USER_LIMIT = 30
ASSISTANT_FINN_DRAFT_LIMIT = 45
ASSISTANT_IP_FALLBACK_LIMIT = 20
LOCAL_PROXY_IPS = {"127.0.0.1", "::1", "localhost"}

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


def _client_ip(raw_request: Request) -> str:
    forwarded = raw_request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",", 1)[0].strip()
        if first:
            return first
    real_ip = raw_request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return raw_request.client.host if raw_request.client else "unknown"


def _is_finn_transactional_request(query: str, context: dict) -> bool:
    q = (query or "").lower()
    draft = context.get("finn_draft") if isinstance(context.get("finn_draft"), dict) else None
    if draft:
        return True
    return any(word in q for word in [
        "annuleer", "cancel", "setup", "strategie", "strategy", "dca",
        "trade", "entry", "stop", "target", "koop", "kopen", "bot",
        "macro", "technical", "indicator", "indicatoren", "node", "contrarian",
    ])


def _apply_assistant_rate_limit(
    *,
    user_id: int,
    raw_request: Request,
    query: str,
    context: dict,
    endpoint: str,
) -> Tuple[str, int]:
    ip_addr = _client_ip(raw_request)
    user_limit = ASSISTANT_FINN_DRAFT_LIMIT if _is_finn_transactional_request(query, context) else ASSISTANT_USER_LIMIT
    chat_rate_limiter.check_rate_limit(f"user_{user_id}:assistant", limit=user_limit)

    # Behind nginx/PM2 the backend often sees 127.0.0.1. Do not make all real
    # users share one localhost bucket; only use IP fallback for real client IPs.
    if ip_addr not in LOCAL_PROXY_IPS:
        chat_rate_limiter.check_rate_limit(f"ip_{ip_addr}:assistant", limit=ASSISTANT_IP_FALLBACK_LIMIT)
    else:
        logger.debug("Skipping assistant IP rate limit for local proxy IP %s on %s", ip_addr, endpoint)
    return ip_addr, user_limit

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
        finn = FinnPlanService(db)
        context_payload = await finn.hydrate_context(user_id, _assistant_context_payload(request.context))
        _apply_assistant_rate_limit(
            user_id=user_id,
            raw_request=raw_request,
            query=request.query,
            context=context_payload,
            endpoint="/assistant/chat",
        )
        if finn.looks_like_daily_score_refresh_request(request.query):
            finn_response = await finn.build_daily_score_refresh_response(user_id, request.query, context_payload)
            finn_response["trace_id"] = trace_id
            return AssistantChatResponse(**finn_response)
        if finn.looks_like_bot_decision_request(request.query) or (
            context_payload.get("current_flow") == "bot_decision"
            and context_payload.get("pending_behavioral_memory_friction")
        ):
            finn_response = await finn.build_bot_decision_response(user_id, request.query, context_payload)
            finn_response["trace_id"] = trace_id
            return AssistantChatResponse(**finn_response)
        if finn.looks_like_bot_decision_review_request(request.query):
            finn_response = await finn.build_bot_decision_review_response(user_id, request.query, context_payload)
            finn_response["trace_id"] = trace_id
            return AssistantChatResponse(**finn_response)
        if finn.looks_like_bot_execution_decision_request(request.query):
            finn_response = await finn.build_bot_execution_decision_response(user_id, request.query, context_payload)
            finn_response["trace_id"] = trace_id
            return AssistantChatResponse(**finn_response)
        if finn.looks_like_behavioral_memory_request(request.query):
            finn_response = await finn.build_behavioral_memory_response(user_id, request.query, context_payload)
            finn_response["trace_id"] = trace_id
            return AssistantChatResponse(**finn_response)
        if finn.looks_like_weekly_reflection_request(request.query):
            finn_response = await finn.build_weekly_reflection_response(user_id, request.query, context_payload)
            finn_response["trace_id"] = trace_id
            return AssistantChatResponse(**finn_response)
        if finn.looks_like_behavioral_intelligence_request(request.query):
            finn_response = await finn.build_behavioral_intelligence_response(user_id, request.query, context_payload)
            finn_response["trace_id"] = trace_id
            return AssistantChatResponse(**finn_response)
        if finn.looks_like_daily_coach_request(request.query):
            finn_response = await finn.build_daily_coach_response(user_id, request.query, context_payload)
            finn_response["trace_id"] = trace_id
            return AssistantChatResponse(**finn_response)
        if finn.is_cancel_request(request.query):
            finn_response = await finn.build_cancel_response(user_id, context_payload)
            if finn_response:
                finn_response["trace_id"] = trace_id
                await finn.persist_response_state(user_id, finn_response)
                return AssistantChatResponse(**finn_response)
        if finn.looks_like_indicator_insight_request(request.query):
            finn_response = await finn.build_indicator_insight_response(user_id, request.query, context_payload)
            finn_response["trace_id"] = trace_id
            return AssistantChatResponse(**finn_response)
        if finn.looks_like_status_request(request.query):
            finn_response = await finn.build_status_response(user_id, request.query, context_payload)
            finn_response["trace_id"] = trace_id
            return AssistantChatResponse(**finn_response)
        if finn.looks_like_indicator_config_request(request.query, context_payload):
            finn_response = await finn.build_indicator_config_response_for_user(user_id, request.query, context_payload)
            finn_response["trace_id"] = trace_id
            await finn.persist_response_state(user_id, finn_response)
            return AssistantChatResponse(**finn_response)
        if finn.looks_like_bot_request(request.query, context_payload):
            finn_response = await finn.build_bot_response_for_user(user_id, request.query, context_payload)
            finn_response["trace_id"] = trace_id
            await finn.persist_response_state(user_id, finn_response)
            return AssistantChatResponse(**finn_response)
        if finn.looks_like_strategy_request(request.query, context_payload):
            finn_response = await finn.build_strategy_response_for_user(user_id, request.query, context_payload)
            finn_response["trace_id"] = trace_id
            await finn.persist_response_state(user_id, finn_response)
            return AssistantChatResponse(**finn_response)
        if finn.looks_like_plan_request(request.query, context_payload.get("finn_draft")):
            finn_response = finn.build_response(request.query, context_payload)
            finn_response["trace_id"] = trace_id
            await finn.persist_response_state(user_id, finn_response)
            return AssistantChatResponse(**finn_response)

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


def _assistant_context_payload(context) -> dict:
    if hasattr(context, "dict"):
        return context.dict(exclude_none=True)
    return context or {}


def _sse_event(event_name: str, data_val) -> str:
    if isinstance(data_val, dict):
        data_str = json.dumps(data_val)
    else:
        data_str = str(data_val)
    return f"event: {event_name}\ndata: {data_str}\n\n"

@router.post("/assistant/chat/stream")
async def assistant_chat_stream(
    request: AssistantChatRequest,
    background_tasks: BackgroundTasks,
    raw_request: Request,
    x_trace_id: Optional[str] = Header(None),
    current_user: dict = Depends(get_current_user),
    service: AiAssistantService = Depends(get_assistant_service),
    db: AsyncSession = Depends(get_db),
):
    """
    ⚡ Real-Time SSE Stream for AI Assistant Chat (Fase 3 Lightweight)
    """
    user_id = current_user["id"]

    trace_id = x_trace_id or f"trdm-trace-{uuid.uuid4().hex[:8]}-{hex(int(time.time()))[2:]}"

    async def event_generator():
        try:
            finn = FinnPlanService(db)
            context_payload = await finn.hydrate_context(user_id, _assistant_context_payload(request.context))
            _apply_assistant_rate_limit(
                user_id=user_id,
                raw_request=raw_request,
                query=request.query,
                context=context_payload,
                endpoint="/assistant/chat/stream",
            )
            if finn.looks_like_daily_score_refresh_request(request.query):
                envelope = await finn.build_daily_score_refresh_response(user_id, request.query, context_payload)
                envelope["trace_id"] = trace_id
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_bot_decision_request(request.query) or (
                context_payload.get("current_flow") == "bot_decision"
                and context_payload.get("pending_behavioral_memory_friction")
            ):
                envelope = await finn.build_bot_decision_response(user_id, request.query, context_payload)
                envelope["trace_id"] = trace_id
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_bot_decision_review_request(request.query):
                envelope = await finn.build_bot_decision_review_response(user_id, request.query, context_payload)
                envelope["trace_id"] = trace_id
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_bot_execution_decision_request(request.query):
                envelope = await finn.build_bot_execution_decision_response(user_id, request.query, context_payload)
                envelope["trace_id"] = trace_id
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_behavioral_memory_request(request.query):
                envelope = await finn.build_behavioral_memory_response(user_id, request.query, context_payload)
                envelope["trace_id"] = trace_id
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_weekly_reflection_request(request.query):
                envelope = await finn.build_weekly_reflection_response(user_id, request.query, context_payload)
                envelope["trace_id"] = trace_id
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_behavioral_intelligence_request(request.query):
                envelope = await finn.build_behavioral_intelligence_response(user_id, request.query, context_payload)
                envelope["trace_id"] = trace_id
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_daily_coach_request(request.query):
                envelope = await finn.build_daily_coach_response(user_id, request.query, context_payload)
                envelope["trace_id"] = trace_id
                yield _sse_event("envelope", envelope)
                return

            if finn.is_cancel_request(request.query):
                envelope = await finn.build_cancel_response(user_id, context_payload)
                if envelope:
                    envelope["trace_id"] = trace_id
                    await finn.persist_response_state(user_id, envelope)
                    yield _sse_event("envelope", envelope)
                    return

            if finn.looks_like_indicator_insight_request(request.query):
                envelope = await finn.build_indicator_insight_response(user_id, request.query, context_payload)
                envelope["trace_id"] = trace_id
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_status_request(request.query):
                envelope = await finn.build_status_response(user_id, request.query, context_payload)
                envelope["trace_id"] = trace_id
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_indicator_config_request(request.query, context_payload):
                envelope = await finn.build_indicator_config_response_for_user(user_id, request.query, context_payload)
                envelope["trace_id"] = trace_id
                await finn.persist_response_state(user_id, envelope)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_bot_request(request.query, context_payload):
                envelope = await finn.build_bot_response_for_user(user_id, request.query, context_payload)
                envelope["trace_id"] = trace_id
                await finn.persist_response_state(user_id, envelope)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_strategy_request(request.query, context_payload):
                envelope = await finn.build_strategy_response_for_user(user_id, request.query, context_payload)
                envelope["trace_id"] = trace_id
                await finn.persist_response_state(user_id, envelope)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_plan_request(request.query, context_payload.get("finn_draft")):
                envelope = finn.build_response(request.query, context_payload)
                envelope["trace_id"] = trace_id
                await finn.persist_response_state(user_id, envelope)
                yield _sse_event("envelope", envelope)
                return

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

                yield _sse_event(event_name, data_val)
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
            context_detected=insight.get("context_detected") or context,
            suggested_actions=insight.get("suggested_actions"),
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

@router.get("/assistant/finn/state")
async def get_finn_state(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    finn = FinnPlanService(db)
    return await finn.get_open_plan_state(current_user["id"])


@router.get("/assistant/mission-control")
async def get_finn_mission_control(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    finn = FinnPlanService(db)
    return await finn.build_mission_control_response(
        current_user["id"],
        {"page": "assistant", "scope": "mission_control"},
    )
