import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Primary assistant limits. Authenticated Finn users get enough room for
# multi-turn draft repair, while anonymous/IP fallback remains stricter.
from backend.utils.rate_limit import InMemoryRateLimiter, client_ip

chat_rate_limiter = InMemoryRateLimiter(requests_limit=30, window_seconds=60)
execute_rate_limiter = InMemoryRateLimiter(requests_limit=20, window_seconds=60)
ASSISTANT_USER_LIMIT = 30
ASSISTANT_FINN_DRAFT_LIMIT = 45
ASSISTANT_IP_FALLBACK_LIMIT = 20
ASSISTANT_EXECUTE_USER_LIMIT = 20
ASSISTANT_EXECUTE_IP_LIMIT = 30
LOCAL_PROXY_IPS = {"127.0.0.1", "::1", "localhost"}

from backend.infrastructure.database import async_session_factory, get_db
from backend.utils.auth_utils import get_current_user
from backend.infrastructure.models import ChatSession, ChatMessage
from backend.schemas.assistant_schema import (
    AssistantAnalyticsEvent,
    AssistantChatRequest,
    AssistantChatResponse,
    AssistantPreferences,
    AssistantPreferenceUpdate,
    ChatSessionResponse,
    ChatSessionDetailResponse,
)
from backend.services.finn_product_analytics_service import finn_product_analytics
from backend.services.locale_service import resolve_locale
from backend.services.trader_profile_service import (
    build_trader_profile_context,
    build_trader_profile_summary,
    has_trader_profile,
    normalize_trader_profile_preferences,
)
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.infrastructure.repositories.finn_v2_execution_repository import FinnV2ExecutionRepository
from backend.services.ai_action_engine import AiActionEngine
from backend.services.finn_v2_confirmation_service import FinnV2ConfirmationService
from backend.services.finn_v2_execution_service import FinnV2ExecutionService
from backend.services.finn_v2_runtime_selector_service import FinnV2RuntimeSelectorService
from backend.services.finn_v2_visible_delivery_service import FinnV2VisibleDeliveryService
from backend.schemas.finn_v2_confirmation_schema import FinnV2ConfirmationRequest
from backend.schemas.finn_v2_execution_schema import FinnV2ExecuteProposalRequest

router = APIRouter()
logger = logging.getLogger(__name__)
FINN_V2_VERIFIED_SOURCE = "finn_v2" + "_verified"


def _audit_context_summary(context: Optional[dict]) -> Dict[str, Any]:
    payload = context or {}
    return {
        "page": payload.get("page"),
        "page_type": payload.get("page_type"),
        "symbol": payload.get("symbol") or payload.get("asset"),
        "timeframe": payload.get("timeframe"),
        "setup_id": payload.get("setup_id"),
        "strategy_id": payload.get("strategy_id"),
        "bot_id": payload.get("bot_id"),
        "setup_symbol": payload.get("setup_symbol"),
        "setup_timeframe": payload.get("setup_timeframe"),
        "setup_type": payload.get("setup_type"),
        "setup_name": payload.get("setup_name"),
        "finn_subject_type": payload.get("finn_subject_type"),
        "current_flow": payload.get("current_flow"),
        "trader_profile_used": payload.get("trader_profile_used"),
        "trader_profile_summary": payload.get("trader_profile_summary"),
        "profile_match_mode": payload.get("profile_match_mode"),
        "profile_match_reason": payload.get("profile_match_reason"),
        "profile_conflict_detected": payload.get("profile_conflict_detected"),
    }


async def _enrich_with_trader_profile(
    db: AsyncSession,
    user_id: int,
    payload: Optional[dict] = None,
    *,
    query: Optional[str] = None,
) -> dict:
    context_payload = dict(payload or {})
    user = await UserRepository(db).get_by_id(user_id)
    preferences = getattr(user, "ai_preferences", {}) or {} if user else {}
    context_payload.update(build_trader_profile_context(preferences, request_context=context_payload, query=query))
    requested_locale = context_payload.get("locale")
    context_payload["locale"] = resolve_locale(
        {"locale": requested_locale} if requested_locale else preferences,
        context_payload,
    )
    return context_payload


def _audit_draft_summary(draft: Optional[dict]) -> Optional[Dict[str, Any]]:
    if not isinstance(draft, dict):
        return None
    summary = {
        "draft_kind": draft.get("draft_kind"),
        "plan_type": draft.get("plan_type"),
        "operation": draft.get("operation"),
        "asset": draft.get("asset"),
        "setup_id": draft.get("setup_id"),
        "strategy_id": draft.get("strategy_id"),
        "bot_id": draft.get("bot_id"),
        "existing_strategy_id": draft.get("existing_strategy_id"),
        "existing_bot_id": draft.get("existing_bot_id"),
    }
    return {key: value for key, value in summary.items() if value not in (None, "", [], {})}


def _trader_profile_event_metadata(context_payload: Optional[dict]) -> Dict[str, Any]:
    payload = context_payload or {}
    trader_profile = payload.get("trader_profile") if isinstance(payload.get("trader_profile"), dict) else {}
    behavior_flags = trader_profile.get("behavior_flags") if isinstance(trader_profile.get("behavior_flags"), list) else []
    return {
        "trader_profile_used": bool(payload.get("trader_profile_used")),
        "trader_profile_summary": payload.get("trader_profile_summary") or "",
        "profile_match_mode": payload.get("profile_match_mode") or "profile_missing_fallback",
        "profile_match_reason": payload.get("profile_match_reason") or "",
        "profile_conflict_detected": bool(payload.get("profile_conflict_detected")),
        "behavior_flags": [str(flag) for flag in behavior_flags[:5]],
        "behavior_flag": str(behavior_flags[0]) if behavior_flags else "",
    }


def _record_finn_product_event(
    *,
    user_id: int,
    event_name: str,
    session_id: Optional[str] = None,
    surface: str = "backend",
    page: Optional[str] = None,
    asset: Optional[str] = None,
    flow_type: Optional[str] = None,
    action_type: Optional[str] = None,
    report_type: Optional[str] = None,
    decision_id: Optional[str] = None,
    bot_id: Optional[int] = None,
    setup_id: Optional[int] = None,
    strategy_id: Optional[int] = None,
    trace_id: Optional[str] = None,
    prompt_text: Optional[str] = None,
    next_best_action: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
 ) -> Dict[str, Any]:
    return finn_product_analytics.record_event(
        user_id=user_id,
        event={
            "event_name": event_name,
            "session_id": session_id,
            "surface": surface,
            "page": page,
            "asset": asset,
            "flow_type": flow_type,
            "action_type": action_type,
            "report_type": report_type,
            "decision_id": decision_id,
            "bot_id": bot_id,
            "setup_id": setup_id,
            "strategy_id": strategy_id,
            "trace_id": trace_id,
            "prompt_text": prompt_text,
            "next_best_action": next_best_action,
            "metadata": metadata or {},
        },
    )


def _preflight_v2_runtime_selection(
    *,
    user_id: int,
    query: str,
    transport: str,
    context_payload: Optional[dict],
):
    selector = FinnV2RuntimeSelectorService()
    return selector.select(
        user_id=user_id,
        message=query,
        surface="assistant_chat_stream" if transport == "stream" else "assistant_chat",
        workspace_hints=context_payload or {},
        client_context=context_payload or {},
    )


def _log_finn_prompt_audit(
    *,
    trace_id: str,
    user_id: int,
    prompt: str,
    route_source: str,
    detected_intent: Optional[str],
    intent_confidence: Optional[float],
    selected_flow: Optional[str],
    selected_entity: Optional[Dict[str, Any]],
    context_payload: Optional[dict],
    used_draft: bool,
    draft_summary: Optional[Dict[str, Any]],
    response_type: str,
    success: str,
    mode: Optional[str] = None,
    context_confidence: Optional[Dict[str, Any]] = None,
    draft_rejected_reason: Optional[str] = None,
    legacy_rescue_reason: Optional[str] = None,
    latency_ms: Optional[float] = None,
    response_source: Optional[str] = None,
    response_handler: Optional[str] = None,
) -> None:
    audit_payload = {
        "trace_id": trace_id,
        "user_id": user_id,
        "prompt": prompt,
        "detected_intent": detected_intent,
        "intent_confidence": intent_confidence,
        "selected_flow": selected_flow,
        "selected_entity": selected_entity or {},
        "context": _audit_context_summary(context_payload),
        "draft_used": used_draft,
        "draft": draft_summary,
        "response_type": response_type,
        "success": success,
        "route_source": route_source,
        "mode": mode,
        "context_confidence": context_confidence,
        "draft_rejected_reason": draft_rejected_reason,
        "legacy_rescue_reason": legacy_rescue_reason,
        "latency_ms": latency_ms,
        "response_source": response_source,
        "response_handler": response_handler,
    }
    logger.info("📋 [FINN-P0-AUDIT] %s", json.dumps(audit_payload, ensure_ascii=False, default=str))


def _client_ip(raw_request: Request) -> str:
    return client_ip(raw_request)


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


def _apply_assistant_execute_rate_limit(*, user_id: int, raw_request: Request) -> None:
    ip_addr = _client_ip(raw_request)
    execute_rate_limiter.check_rate_limit(
        f"user_{user_id}:assistant_execute",
        limit=ASSISTANT_EXECUTE_USER_LIMIT,
        detail="Te veel Finn execute-verzoeken. Wacht kort en probeer opnieuw.",
    )
    if ip_addr not in LOCAL_PROXY_IPS:
        execute_rate_limiter.check_rate_limit(
            f"ip_{ip_addr}:assistant_execute",
            limit=ASSISTANT_EXECUTE_IP_LIMIT,
            detail="Te veel Finn execute-verzoeken vanaf dit IP-adres. Wacht kort en probeer opnieuw.",
        )


def _new_finn_plan_service(db: AsyncSession, *, trace_id: Optional[str] = None):
    from backend.services.finn_plan_service import FinnPlanService

    return FinnPlanService(db, trace_id=trace_id)


@router.post("/assistant/chat", response_model=AssistantChatResponse)
async def assistant_chat(
    request: AssistantChatRequest,
    raw_request: Request,
    x_trace_id: Optional[str] = Header(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    trace_id = x_trace_id or f"trdm-trace-{uuid.uuid4().hex[:8]}-{hex(int(time.time()))[2:]}"
    started_at = time.perf_counter()
    try:
        user_id = current_user["id"]
        # Keep the entry boundary limited to client state and transport
        # controls. The durable FINN V2 run selects its contract before it
        # reads personalized context in the lifecycle worker.
        context_payload = dict(_assistant_context_payload(request.context))
        runtime_selection = _preflight_v2_runtime_selection(
            user_id=user_id,
            query=request.query,
            transport="chat",
            context_payload=context_payload,
        )
        if request.session_id:
            context_payload["session_id"] = request.session_id
        _apply_assistant_rate_limit(
            user_id=user_id,
            raw_request=raw_request,
            query=request.query,
            context=context_payload,
            endpoint="/assistant/chat",
        )
        _record_finn_product_event(
            user_id=user_id,
            event_name="finn_prompt_submitted",
            session_id=request.session_id,
            surface="assistant_chat",
            page=context_payload.get("page"),
            asset=context_payload.get("symbol") or context_payload.get("asset"),
            flow_type=context_payload.get("current_flow"),
            bot_id=context_payload.get("bot_id"),
            setup_id=context_payload.get("setup_id"),
            strategy_id=context_payload.get("strategy_id"),
            trace_id=trace_id,
            prompt_text=request.query,
            metadata=_trader_profile_event_metadata(context_payload),
        )
        v2_visible = await _try_v2_visible_delivery(
            db=db,
            user_id=user_id,
            message=request.query,
            context_payload=context_payload,
            transport="chat",
            request_path=_safe_request_path(raw_request, "/api/assistant/chat"),
            request_id=_safe_request_trace_id(raw_request, trace_id),
            trace_id=trace_id,
            runtime_selection=runtime_selection,
        )
        return AssistantChatResponse(
            response=v2_visible.get("response") or "",
            intent=v2_visible.get("intent") or "unavailable",
            action=v2_visible.get("action"),
            draft=v2_visible.get("draft"),
            state=v2_visible.get("state"),
            reasoning=v2_visible.get("reasoning"),
            suggested_actions=v2_visible.get("suggested_actions"),
            trace_id=trace_id,
            session_id=request.session_id,
            flow=(v2_visible.get("state") or {}).get("current_flow"),
            actions=v2_visible.get("actions") or [],
            can_confirm=bool(v2_visible.get("can_confirm")),
            summary=v2_visible.get("summary"),
            risk_summary=v2_visible.get("risk_summary"),
            next_best_action=v2_visible.get("next_best_action"),
            response_trace=v2_visible.get("response_trace"),
        )
    except HTTPException:
        raise
    except Exception as e:
        _log_finn_prompt_audit(
            trace_id=trace_id,
            user_id=current_user["id"],
            prompt=request.query,
            route_source="exception",
            detected_intent=None,
            intent_confidence=None,
            selected_flow=None,
            selected_entity=None,
            context_payload=_assistant_context_payload(request.context),
            used_draft=bool(isinstance((_assistant_context_payload(request.context) or {}).get("finn_draft"), dict)),
            draft_summary=_audit_draft_summary((_assistant_context_payload(request.context) or {}).get("finn_draft")),
            response_type="exception",
            success="failure",
            draft_rejected_reason=((_assistant_context_payload(request.context) or {}).get("_finn_sanitization") or {}).get("draft_rejected_reason"),
            latency_ms=(time.perf_counter() - started_at) * 1000,
        )
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


@router.api_route("/assistant/sessions/new", methods=["GET", "POST"], response_model=ChatSessionResponse)
async def create_compat_chat_session(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        user_id = current_user["id"]
        now = datetime.utcnow()
        session = ChatSession(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title="Nieuw FINN gesprek",
            created_at=now,
            updated_at=now,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session
    except Exception:
        logger.exception("❌ Error aanmaken compat chatsessie")
        raise HTTPException(status_code=500, detail="Fout bij aanmaken chatsessie")


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


def _assistant_context_payload(context) -> dict:
    if hasattr(context, "dict"):
        return context.dict(exclude_none=True)
    return context or {}


def _safe_request_path(raw_request: Request, fallback: str) -> str:
    scope = getattr(raw_request, "scope", {}) or {}
    path = scope.get("path")
    return path if isinstance(path, str) and path else fallback


def _safe_request_trace_id(raw_request: Request, fallback: str) -> str:
    state = getattr(raw_request, "state", None)
    return getattr(state, "trace_id", fallback)


def _session_requires_rollback(session: AsyncSession) -> bool:
    sync_session = getattr(session, "sync_session", None)
    if sync_session is not None and getattr(sync_session, "is_active", True) is False:
        return True
    transaction = session.get_transaction()
    return bool(transaction is not None and getattr(transaction, "is_active", True) is False)


def _sse_event(event_name: str, data_val) -> str:
    if isinstance(data_val, dict):
        data_str = json.dumps(data_val, ensure_ascii=False, default=str)
    else:
        data_str = str(data_val)
    return f"event: {event_name}\ndata: {data_str}\n\n"


async def _try_v2_visible_delivery(
    *,
    db: AsyncSession,
    user_id: int,
    message: str,
    context_payload: Optional[dict],
    transport: str,
    request_path: str,
    request_id: str,
    trace_id: str,
    runtime_selection=None,
):
    selection = runtime_selection or _preflight_v2_runtime_selection(
        user_id=user_id,
        query=message,
        transport=transport,
        context_payload=context_payload,
    )
    if selection.selected_runtime != "v2" or not selection.visible_allowed:
        raise ValueError("v2_runtime_not_selected")
    try:
        async with async_session_factory() as v2_db:
            try:
                envelope = await FinnV2VisibleDeliveryService(v2_db).deliver_assistant_envelope(
                    user_id=user_id,
                    message=message,
                    context_payload=context_payload,
                    transport=transport,
                    request_path=request_path,
                    request_id=request_id,
                    trace_id=trace_id,
                )
            except Exception:
                if _session_requires_rollback(v2_db):
                    await v2_db.rollback()
                else:
                    await v2_db.commit()
                raise
            await v2_db.commit()
        envelope.setdefault("response_trace", {})
        envelope["response_trace"]["runtime_selection"] = selection.dict()
        return envelope
    except Exception as exc:
        try:
            await db.rollback()
        except Exception:
            logger.exception(
                "FINN V2 visible delivery rollback failed",
                extra={
                    "trace_id": trace_id,
                    "request_id": request_id,
                    "user_id": user_id,
                    "transport": transport,
                    "request_path": request_path,
                },
            )
        reason = getattr(exc, "code", str(exc))
        return {
            "response": "Ik kan nu geen veilige verified V2-response uitleveren.",
            "intent": "unavailable",
            "state": {"current_flow": "finn_v2_visible_failed"},
            "summary": "De V2-runtime kon geen veilige verified response afleveren.",
            "risk_summary": reason,
            "next_best_action": None,
            "response_trace": {
                "trace_id": trace_id,
                "run_id": getattr(exc, "run_id", None),
                "pipeline_version": "finn_v2",
                "router_name": "finn_v2_orchestrator",
                "selected_handler": "FinnV2VisibleDeliveryService.deliver_assistant_envelope",
                "response_source": FINN_V2_VERIFIED_SOURCE,
                "runtime_selection": selection.dict(),
                "error": reason,
                "failure_stage": getattr(exc, "failure_stage", None),
            },
            "can_confirm": False,
            "actions": [],
        }


def _require_csrf_match(request: Request, provided: Optional[str]) -> None:
    cookie_token = request.cookies.get("csrf_token")
    if cookie_token and provided != cookie_token:
        raise HTTPException(status_code=403, detail="CSRF token mismatch")

@router.post("/assistant/chat/stream")
async def assistant_chat_stream(
    request: AssistantChatRequest,
    background_tasks: BackgroundTasks,
    raw_request: Request,
    x_trace_id: Optional[str] = Header(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    ⚡ Real-Time SSE Stream for AI Assistant Chat (Fase 3 Lightweight)
    """
    user_id = current_user["id"]

    trace_id = x_trace_id or f"trdm-trace-{uuid.uuid4().hex[:8]}-{hex(int(time.time()))[2:]}"
    started_at = time.perf_counter()

    async def event_generator():
        try:
            # Match the non-streaming boundary exactly. Selection and any
            # contract-required context collection happen after run creation.
            context_payload = dict(_assistant_context_payload(request.context))
            runtime_selection = _preflight_v2_runtime_selection(
                user_id=user_id,
                query=request.query,
                transport="stream",
                context_payload=context_payload,
            )
            if request.session_id:
                context_payload["session_id"] = request.session_id
            _apply_assistant_rate_limit(
                user_id=user_id,
                raw_request=raw_request,
                query=request.query,
                context=context_payload,
                endpoint="/assistant/chat/stream",
            )
            _record_finn_product_event(
                user_id=user_id,
                event_name="finn_prompt_submitted",
                session_id=request.session_id,
                surface="assistant_chat_stream",
                page=context_payload.get("page"),
                asset=context_payload.get("symbol") or context_payload.get("asset"),
                flow_type=context_payload.get("current_flow"),
                bot_id=context_payload.get("bot_id"),
                setup_id=context_payload.get("setup_id"),
                strategy_id=context_payload.get("strategy_id"),
                trace_id=trace_id,
                prompt_text=request.query,
                metadata=_trader_profile_event_metadata(context_payload),
            )
            v2_visible = await _try_v2_visible_delivery(
                db=db,
                user_id=user_id,
                message=request.query,
                context_payload=context_payload,
                transport="stream",
                request_path=_safe_request_path(raw_request, "/api/assistant/chat/stream"),
                request_id=_safe_request_trace_id(raw_request, trace_id),
                trace_id=trace_id,
                runtime_selection=runtime_selection,
            )
            yield _sse_event("envelope", v2_visible)
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
    existing_user = await user_repo.get_by_id(current_user["id"])
    existing_preferences = getattr(existing_user, "ai_preferences", {}) or {}
    old_profile = normalize_trader_profile_preferences(existing_preferences)
    old_has_profile = has_trader_profile(old_profile)
    updates = {k: v for k, v in request.dict().items() if v is not None}
    user = await user_repo.update_ai_preferences(current_user["id"], updates)
    new_preferences = getattr(user, "ai_preferences", {}) or {}
    new_profile = normalize_trader_profile_preferences(new_preferences)
    new_has_profile = has_trader_profile(new_profile)

    if not old_has_profile and new_has_profile:
        _record_finn_product_event(
            user_id=current_user["id"],
            event_name="trader_profile_created",
            surface="assistant_preferences",
            flow_type="trader_profile",
            metadata={
                "profile_summary": build_trader_profile_summary(new_profile),
                "trader_profile": new_profile,
            },
        )
    elif old_profile != new_profile:
        _record_finn_product_event(
            user_id=current_user["id"],
            event_name="trader_profile_updated",
            surface="assistant_preferences",
            flow_type="trader_profile",
            metadata={
                "previous_profile_summary": build_trader_profile_summary(old_profile),
                "profile_summary": build_trader_profile_summary(new_profile),
                "trader_profile": new_profile,
            },
        )

    return AssistantPreferences(preferences=user.ai_preferences)

async def get_ai_action_engine(db: AsyncSession = Depends(get_db)):
    return AiActionEngine(db)

@router.post("/assistant/actions/execute")
async def execute_pending_action(
    payload: dict,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    engine: AiActionEngine = Depends(get_ai_action_engine),
):
    trace_id = getattr(request.state, "trace_id", None)
    action_id = payload.get("action_id")
    if not action_id:
        raise HTTPException(status_code=400, detail="Action ID is verplicht.")
    
    user_id = current_user["id"]
    _apply_assistant_execute_rate_limit(user_id=user_id, raw_request=request)
    if str(action_id).startswith("finn-"):
        try:
            finn = _new_finn_plan_service(db, trace_id=trace_id)
            result = await finn.execute_issued_action(user_id, str(action_id))
            from backend.services.finn_plan_service import FinnPlanService
            FinnPlanService.invalidate_runtime_caches_for_user(user_id)
            _record_finn_product_event(
                user_id=user_id,
                event_name="finn_confirm_confirmed",
                surface="assistant_execute",
                flow_type="confirm",
                action_type="execute_issued_action",
                trace_id=trace_id,
                metadata={"action_id": str(action_id)},
            )
            return result
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ AI Assistant Action Error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Fout bij Finn action")
    return await engine.execute_pending_action(action_id, user_id, trace_id=trace_id)


@router.post("/assistant/analytics/events")
async def record_assistant_analytics_event(
    payload: AssistantAnalyticsEvent,
    current_user: dict = Depends(get_current_user),
):
    event = _record_finn_product_event(
        user_id=current_user["id"],
        event_name=payload.event_name,
        session_id=payload.session_id,
        surface=payload.surface,
        page=payload.page,
        asset=payload.asset,
        flow_type=payload.flow_type,
        action_type=payload.action_type,
        report_type=payload.report_type,
        decision_id=payload.decision_id,
        bot_id=payload.bot_id,
        setup_id=payload.setup_id,
        strategy_id=payload.strategy_id,
        trace_id=payload.trace_id,
        prompt_text=payload.prompt_text,
        next_best_action=payload.next_best_action,
        metadata=payload.metadata,
    )
    return {"ok": True, "event": event}


@router.get("/assistant/traces/{trace_id}")
async def get_assistant_response_trace(
    trace_id: str,
    current_user: dict = Depends(get_current_user),
):
    trace = finn_product_analytics.get_response_trace(
        user_id=current_user["id"],
        trace_id=trace_id,
    )
    if trace is None:
        raise HTTPException(status_code=404, detail="FINN-trace niet gevonden.")
    return trace

@router.get("/assistant/finn/state")
async def get_finn_state(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    finn = _new_finn_plan_service(db)
    response = await finn.get_open_plan_state(current_user["id"])
    return await _enrich_with_trader_profile(db, current_user["id"], response)


@router.get("/assistant/mission-control")
async def get_finn_mission_control(
    symbol: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    requested_symbol = str(symbol or "").strip().upper()
    if requested_symbol and not re.fullmatch(r"[A-Z0-9._-]{1,20}", requested_symbol):
        raise HTTPException(status_code=422, detail="Ongeldig assetsymbool.")
    trace_id = getattr(request.state, "trace_id", None) if request else None
    service = FinnV2VisibleDeliveryService(db)
    try:
        response = await asyncio.wait_for(
            service.deliver_mission_control(
                user_id=current_user["id"],
                context_payload={
                    "page": "assistant",
                    "surface": "today_with_finn",
                    "symbol": requested_symbol or None,
                },
                request_id=trace_id or f"mission-{uuid.uuid4().hex}",
                trace_id=trace_id or f"mission-{uuid.uuid4().hex}",
            ),
            timeout=8.0,
        )
    except Exception as exc:
        logger.exception("FINN mission control enrichment failed", exc_info=exc)
        response = await service.deliver_mission_control_fallback(
            user_id=current_user["id"],
            trace_id=trace_id or f"mission-{uuid.uuid4().hex}",
            symbol=requested_symbol or None,
        )
    # Mission Control projects mutable owner-scoped state. A process-local
    # cache cannot be coherently invalidated across PM2 workers after an
    # execution, so every request reads the persisted projection directly.
    return response


@router.get("/assistant/v2/proposals/{proposal_id}")
async def assistant_v2_get_proposal(
    proposal_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from backend.infrastructure.repositories.finn_v2_proposal_repository import FinnV2ProposalRepository
    from backend.schemas.finn_v2_execution_schema import FinnV2ProposalSummary
    from backend.schemas.finn_v2_proposal_schema import PROPOSAL_VERSION

    proposal = await FinnV2ProposalRepository(db).get_by_id_for_user(proposal_id=proposal_id, user_id=current_user["id"])
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    change = dict((proposal.payload_json or {}).get("change") or {})
    return FinnV2ProposalSummary(
        proposal_id=proposal.id,
        run_id=proposal.run_id,
        user_id=proposal.user_id,
        status=proposal.status,
        operation_type=proposal.operation_type,
        target={"target_type": proposal.target_type, "target_id": proposal.target_id, "asset": proposal.asset},
        payload_hash=proposal.payload_hash,
        evidence_set_hash=proposal.evidence_set_hash,
        requires_step_up_auth=proposal.requires_step_up_auth,
        expires_at=proposal.expires_at,
        proposal_version=PROPOSAL_VERSION,
        confirmation_required=True,
        before_state=dict(change.get("before_state") or change.get("before") or {}),
        requested_state=dict(change.get("requested_state") or change.get("changed_fields") or {}),
        target_revision=change.get("target_revision"),
        snapshot_timestamp=change.get("snapshot_timestamp"),
    )


@router.post("/assistant/v2/proposals/{proposal_id}/publish")
async def assistant_v2_publish_proposal(
    proposal_id: str,
    raw_request: Request,
    x_csrf_token: Optional[str] = Header(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from backend.services.finn_v2_flag_service import FinnV2FlagService
    from backend.infrastructure.repositories.finn_v2_proposal_repository import FinnV2ProposalRepository

    flags = FinnV2FlagService()
    if not flags.is_visible_proposals_enabled() or not flags.is_confirmation_routes_enabled():
        raise HTTPException(status_code=404, detail="Proposal publication disabled")
    execute_rate_limiter.check_rate_limit(
        f"user_{current_user['id']}:finn_v2_publish",
        limit=ASSISTANT_EXECUTE_USER_LIMIT,
    )
    _require_csrf_match(raw_request, x_csrf_token)
    try:
        token, expires_at = await FinnV2ConfirmationService(db).issue_confirmation_token(proposal_id=proposal_id, user_id=current_user["id"])
    except ValueError as exc:
        if str(exc) != "proposal_not_pending_confirmation":
            raise
        raise HTTPException(status_code=409, detail="Proposal is no longer pending confirmation") from exc
    proposal = await FinnV2ProposalRepository(db).get_by_id_for_user(proposal_id=proposal_id, user_id=current_user["id"])
    return {
        "proposal_id": proposal_id,
        "status": "pending_confirmation",
        "confirmation_token": token,
        "expires_at": expires_at,
        "payload_hash": proposal.payload_hash if proposal else "",
        "confirmation_required": True,
    }


@router.post("/assistant/v2/proposals/{proposal_id}/confirm")
async def assistant_v2_confirm_proposal(
    proposal_id: str,
    request: FinnV2ExecuteProposalRequest,
    raw_request: Request,
    x_csrf_token: Optional[str] = Header(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from backend.services.finn_v2_flag_service import FinnV2FlagService

    flags = FinnV2FlagService()
    if not flags.is_confirmation_routes_enabled():
        raise HTTPException(status_code=404, detail="Confirmation disabled")
    execute_rate_limiter.check_rate_limit(
        f"user_{current_user['id']}:finn_v2_confirm",
        limit=ASSISTANT_EXECUTE_USER_LIMIT,
    )
    _require_csrf_match(raw_request, request.csrf_token or x_csrf_token)
    try:
        result = await FinnV2ConfirmationService(db).confirm(
            user_id=current_user["id"],
            request=FinnV2ConfirmationRequest(
                proposal_id=proposal_id,
                confirmation_token=request.confirmation_token,
                expected_payload_hash=request.expected_payload_hash,
            ),
        )
    except ValueError as exc:
        if str(exc) != "proposal_not_pending_confirmation":
            raise
        raise HTTPException(status_code=409, detail="Proposal is no longer pending confirmation") from exc
    return result.dict()


@router.post("/assistant/v2/proposals/{proposal_id}/cancel")
async def assistant_v2_cancel_proposal(
    proposal_id: str,
    raw_request: Request,
    x_csrf_token: Optional[str] = Header(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_csrf_match(raw_request, x_csrf_token)
    try:
        return await FinnV2ConfirmationService(db).cancel(
            proposal_id=proposal_id,
            user_id=current_user["id"],
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Proposal not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Proposal can no longer be cancelled") from exc


@router.post("/assistant/v2/proposals/{proposal_id}/execute")
async def assistant_v2_execute_proposal(
    proposal_id: str,
    request: FinnV2ExecuteProposalRequest,
    raw_request: Request,
    x_csrf_token: Optional[str] = Header(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from backend.services.finn_v2_flag_service import FinnV2FlagService

    flags = FinnV2FlagService()
    if not flags.is_action_execution_enabled():
        raise HTTPException(status_code=404, detail="Execution disabled")
    # A replay with the same key cannot create another execution: the execution
    # service returns the persisted result. Do not consume the mutation budget
    # for that safe idempotency read, but keep the rate limit for every new key.
    replay = await FinnV2ExecutionRepository(db).get_by_idempotency_key_for_user(
        idempotency_key=request.idempotency_key,
        user_id=current_user["id"],
    )
    if replay is None:
        execute_rate_limiter.check_rate_limit(
            f"user_{current_user['id']}:finn_v2_execute",
            limit=ASSISTANT_EXECUTE_USER_LIMIT,
        )
    _require_csrf_match(raw_request, request.csrf_token or x_csrf_token)
    result = (
        await FinnV2ExecutionService(db).execute(
            proposal_id=proposal_id,
            user_id=current_user["id"],
            idempotency_key=request.idempotency_key,
            expected_payload_hash=request.expected_payload_hash,
        )
    ).dict()
    # FINN Today reads its owner-scoped projection directly on each request.
    from backend.services.finn_plan_service import FinnPlanService
    FinnPlanService.invalidate_runtime_caches_for_user(current_user["id"])
    return result
