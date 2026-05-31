import logging
import os
import time
import uuid
from copy import deepcopy
from typing import Any, Dict, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks, Request
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
MISSION_CONTROL_CACHE_TTL_SECONDS = int(os.getenv("MISSION_CONTROL_CACHE_TTL_SECONDS", "20"))
_mission_control_cache: Dict[int, Dict[str, Any]] = {}


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
        "current_flow": payload.get("current_flow"),
    }


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


def _audit_selected_entity(response: Optional[dict], context: Optional[dict]) -> Dict[str, Any]:
    response = response or {}
    state = response.get("state") if isinstance(response.get("state"), dict) else {}
    draft = response.get("draft") if isinstance(response.get("draft"), dict) else {}
    entity = {
        "asset": state.get("asset") or draft.get("asset") or (context or {}).get("symbol") or (context or {}).get("asset"),
        "setup_id": state.get("setup_id") or draft.get("setup_id") or (context or {}).get("setup_id"),
        "strategy_id": state.get("strategy_id") or draft.get("strategy_id") or (context or {}).get("strategy_id"),
        "bot_id": state.get("bot_id") or draft.get("bot_id") or (context or {}).get("bot_id"),
        "operation": state.get("operation") or draft.get("operation"),
    }
    return {key: value for key, value in entity.items() if value not in (None, "", [], {})}


def _audit_response_type(response: Optional[dict]) -> str:
    response = response or {}
    if response.get("actions"):
        return "actionable_envelope"
    if response.get("draft"):
        return "draft_envelope"
    if response.get("state"):
        return "stateful_response"
    return "text_response"


def _audit_success_label(response: Optional[dict]) -> str:
    response = response or {}
    text = str(response.get("response") or "").lower()
    if "kon geen analyse ophalen" in text:
        return "failure"
    if text.startswith("⚠️") or text.startswith("warning"):
        return "degraded"
    return "success"


def _legacy_response_is_generic_failure(response_text: Optional[str]) -> bool:
    text = str(response_text or "").strip().lower()
    if not text:
        return True
    return (
        "kon geen analyse ophalen" in text
        or "probeer opnieuw" in text and text.startswith("⚠️")
        or "interne authenticatiefout" in text
        or "insufficient_quota" in text
    )


def _query_prefers_non_transactional_finn_response(
    finn: FinnPlanService,
    query: str,
    context_payload: Optional[dict],
) -> bool:
    context_payload = context_payload or {}
    return any([
        finn.looks_like_general_capability_request(query),
        finn.looks_like_product_help_request(query, context_payload),
        finn.looks_like_education_request(query),
        finn.looks_like_mission_control_explain_request(query, context_payload),
        finn.looks_like_entity_explain_request(query, context_payload),
        finn.looks_like_behavioral_intelligence_request(query),
        finn.looks_like_weekly_reflection_request(query),
        finn.looks_like_behavioral_memory_request(query),
        finn.looks_like_finn_report_request(query),
        finn.looks_like_daily_coach_request(query),
        finn.looks_like_indicator_insight_request(query),
        finn.looks_like_status_request(query),
    ])


def _legacy_response_needs_finn_rescue(
    finn: FinnPlanService,
    query: str,
    context_payload: Optional[dict],
    *,
    response_text: Optional[str],
    action: Optional[dict],
    draft: Optional[dict],
    state: Optional[dict],
) -> bool:
    if action or draft:
        return False
    if _legacy_response_is_generic_failure(response_text):
        return True
    if not _query_prefers_non_transactional_finn_response(finn, query, context_payload):
        return False
    current_flow = str((state or {}).get("current_flow") or "").lower()
    return current_flow in {"setup_creation", "strategy_creation", "bot_creation", "indicator_config"}


async def _build_finn_core_rescue_envelope(
    *,
    finn: FinnPlanService,
    user_id: int,
    query: str,
    context_payload: Optional[dict],
) -> dict:
    context_payload = context_payload or {}
    if finn.looks_like_general_capability_request(query):
        return await finn.build_general_capability_response(user_id, query, context_payload)
    if finn.looks_like_product_help_request(query, context_payload):
        return await finn.build_product_help_response(user_id, query, context_payload)
    if finn.looks_like_education_request(query):
        return await finn.build_education_response(user_id, query, context_payload)
    if finn.looks_like_mission_control_explain_request(query, context_payload):
        return await finn.build_mission_control_explain_response(user_id, query, context_payload)
    if finn.looks_like_entity_explain_request(query, context_payload):
        return await finn.build_context_explain_response(user_id, query, context_payload)
    if finn.looks_like_behavioral_intelligence_request(query):
        return await finn.build_behavioral_intelligence_response(user_id, query, context_payload)
    if finn.looks_like_weekly_reflection_request(query):
        return await finn.build_weekly_reflection_response(user_id, query, context_payload)
    if finn.looks_like_behavioral_memory_request(query):
        return await finn.build_behavioral_memory_response(user_id, query, context_payload)
    if finn.looks_like_finn_report_request(query):
        return await finn.build_finn_report_response(user_id, query, context_payload)
    if finn.looks_like_daily_coach_request(query):
        return await finn.build_daily_coach_response(user_id, query, context_payload)
    if finn.looks_like_indicator_insight_request(query):
        return await finn.build_indicator_insight_response(user_id, query, context_payload)
    if finn.looks_like_status_request(query):
        return await finn.build_status_response(user_id, query, context_payload)
    return await finn.build_general_capability_response(user_id, query, context_payload)


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


def _legacy_bot_decision_resume(query: str, context: Optional[dict]) -> bool:
    payload = context or {}
    return bool(
        payload.get("current_flow") == "bot_decision"
        and payload.get("pending_behavioral_memory_friction")
    )


def _redact_assistant_reasoning(payload: Optional[dict]) -> Optional[dict]:
    if not isinstance(payload, dict):
        return payload
    payload["reasoning"] = None
    return payload


def _get_cached_mission_control(user_id: int) -> Optional[dict]:
    cached = _mission_control_cache.get(int(user_id))
    if not cached:
        return None
    if cached["expires_at"] <= time.time():
        _mission_control_cache.pop(int(user_id), None)
        return None
    return deepcopy(cached["response"])


def _store_cached_mission_control(user_id: int, response: dict) -> None:
    _mission_control_cache[int(user_id)] = {
        "expires_at": time.time() + max(1, MISSION_CONTROL_CACHE_TTL_SECONDS),
        "response": deepcopy(response),
    }


def _invalidate_mission_control_cache(user_id: int) -> None:
    _mission_control_cache.pop(int(user_id), None)

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


async def _finalize_finn_response(
    finn: FinnPlanService,
    user_id: int,
    response: dict,
    trace_id: str,
    *,
    persist_state: bool = False,
    prompt: Optional[str] = None,
    context_payload: Optional[dict] = None,
    route_source: str = "finn",
    legacy_rescue_reason: Optional[str] = None,
    latency_ms: Optional[float] = None,
) -> AssistantChatResponse:
    response["trace_id"] = trace_id
    response = finn._build_response_analysis_metadata(response, context_payload, route_source=route_source)
    _redact_assistant_reasoning(response)
    await finn.issue_response_actions(user_id, response)
    if persist_state:
        await finn.persist_response_state(user_id, response)
    reasoning = response.get("reasoning") if isinstance(response.get("reasoning"), dict) else {}
    _log_finn_prompt_audit(
        trace_id=trace_id,
        user_id=user_id,
        prompt=prompt or "",
        route_source=route_source,
        detected_intent=response.get("intent"),
        intent_confidence=reasoning.get("confidence_score"),
        selected_flow=response.get("flow") or (response.get("state") or {}).get("current_flow"),
        selected_entity=_audit_selected_entity(response, context_payload),
        context_payload=context_payload,
        used_draft=bool(isinstance((context_payload or {}).get("finn_draft"), dict)),
        draft_summary=_audit_draft_summary((context_payload or {}).get("finn_draft")),
        response_type=_audit_response_type(response),
        success=_audit_success_label(response),
        mode=(response.get("analysis") or {}).get("mode"),
        context_confidence=(response.get("analysis") or {}).get("context_confidence"),
        draft_rejected_reason=((context_payload or {}).get("_finn_sanitization") or {}).get("draft_rejected_reason"),
        legacy_rescue_reason=legacy_rescue_reason,
        latency_ms=latency_ms,
    )
    return AssistantChatResponse(**response)


async def _prepare_finn_envelope(
    finn: FinnPlanService,
    user_id: int,
    envelope: dict,
    trace_id: str,
    *,
    persist_state: bool = False,
    prompt: Optional[str] = None,
    context_payload: Optional[dict] = None,
    route_source: str = "finn_stream",
    legacy_rescue_reason: Optional[str] = None,
    latency_ms: Optional[float] = None,
) -> dict:
    envelope["trace_id"] = trace_id
    envelope = finn._build_response_analysis_metadata(envelope, context_payload, route_source=route_source)
    _redact_assistant_reasoning(envelope)
    await finn.issue_response_actions(user_id, envelope)
    if persist_state:
        await finn.persist_response_state(user_id, envelope)
    reasoning = envelope.get("reasoning") if isinstance(envelope.get("reasoning"), dict) else {}
    _log_finn_prompt_audit(
        trace_id=trace_id,
        user_id=user_id,
        prompt=prompt or "",
        route_source=route_source,
        detected_intent=envelope.get("intent"),
        intent_confidence=reasoning.get("confidence_score"),
        selected_flow=envelope.get("flow") or (envelope.get("state") or {}).get("current_flow"),
        selected_entity=_audit_selected_entity(envelope, context_payload),
        context_payload=context_payload,
        used_draft=bool(isinstance((context_payload or {}).get("finn_draft"), dict)),
        draft_summary=_audit_draft_summary((context_payload or {}).get("finn_draft")),
        response_type=_audit_response_type(envelope),
        success=_audit_success_label(envelope),
        mode=(envelope.get("analysis") or {}).get("mode"),
        context_confidence=(envelope.get("analysis") or {}).get("context_confidence"),
        draft_rejected_reason=((context_payload or {}).get("_finn_sanitization") or {}).get("draft_rejected_reason"),
        legacy_rescue_reason=legacy_rescue_reason,
        latency_ms=latency_ms,
    )
    return envelope


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
    started_at = time.perf_counter()
    try:
        user_id = current_user["id"]
        finn = FinnPlanService(db)
        context_payload = await finn.hydrate_context(user_id, _assistant_context_payload(request.context))
        context_payload = finn.sanitize_context_for_query(request.query, context_payload)
        _apply_assistant_rate_limit(
            user_id=user_id,
            raw_request=raw_request,
            query=request.query,
            context=context_payload,
            endpoint="/assistant/chat",
        )
        if finn.looks_like_daily_score_refresh_request(request.query):
            finn_response = await finn.build_daily_score_refresh_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload
            )
        if finn.looks_like_general_capability_request(request.query):
            finn_response = await finn.build_general_capability_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000
            )
        if finn.looks_like_education_request(request.query):
            finn_response = await finn.build_education_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000
            )
        if finn.looks_like_mission_control_explain_request(request.query, context_payload):
            finn_response = await finn.build_mission_control_explain_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000
            )
        if finn.looks_like_entity_explain_request(request.query, context_payload):
            finn_response = await finn.build_context_explain_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000
            )
        if finn.looks_like_product_help_request(request.query, context_payload):
            finn_response = await finn.build_product_help_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000
            )
        if finn.looks_like_bot_decision_request(request.query) or _legacy_bot_decision_resume(
            request.query,
            context_payload,
        ):
            finn_response = await finn.build_bot_decision_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, persist_state=True, prompt=request.query, context_payload=context_payload
            )
        if finn.looks_like_bot_decision_review_request(request.query):
            finn_response = await finn.build_bot_decision_review_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload
            )
        if finn.looks_like_bot_execution_decision_request(request.query):
            finn_response = await finn.build_bot_execution_decision_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload
            )
        if finn.looks_like_finn_report_request(request.query):
            finn_response = await finn.build_finn_report_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload
            )
        if finn.looks_like_behavioral_memory_request(request.query):
            finn_response = await finn.build_behavioral_memory_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload
            )
        if finn.looks_like_weekly_reflection_request(request.query):
            finn_response = await finn.build_weekly_reflection_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload
            )
        if finn.looks_like_behavioral_intelligence_request(request.query):
            finn_response = await finn.build_behavioral_intelligence_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload
            )
        if finn.looks_like_daily_coach_request(request.query):
            finn_response = await finn.build_daily_coach_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload
            )
        if finn.is_cancel_request(request.query):
            finn_response = await finn.build_cancel_response(user_id, context_payload)
            if finn_response:
                return await _finalize_finn_response(
                    finn, user_id, finn_response, trace_id, persist_state=True, prompt=request.query, context_payload=context_payload
                )
        if finn.looks_like_indicator_insight_request(request.query):
            finn_response = await finn.build_indicator_insight_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload
            )
        if finn.looks_like_status_request(request.query):
            finn_response = await finn.build_status_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload
            )
        if finn.looks_like_indicator_config_request(request.query, context_payload):
            finn_response = await finn.build_indicator_config_response_for_user(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, persist_state=True, prompt=request.query, context_payload=context_payload
            )
        if finn.looks_like_bot_request(request.query, context_payload):
            finn_response = await finn.build_bot_response_for_user(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, persist_state=True, prompt=request.query, context_payload=context_payload
            )
        if finn.looks_like_strategy_request(request.query, context_payload):
            finn_response = await finn.build_strategy_response_for_user(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, persist_state=True, prompt=request.query, context_payload=context_payload
            )
        if finn.looks_like_plan_request(request.query, context_payload.get("finn_draft")):
            finn_response = finn.build_response(request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, persist_state=True, prompt=request.query, context_payload=context_payload
            )

        try:
            response, action, draft, state, reasoning, suggested_actions, actual_session_id = await service.get_chat_response(
                user_id, request.query, request.history, request.context, trace_id=trace_id, session_id=request.session_id
            )
        except Exception as legacy_exc:
            logger.warning("⚠️ Legacy assistant failed; trying FINN core rescue | Trace: %s | Error: %s", trace_id, legacy_exc)
            rescue = await _build_finn_core_rescue_envelope(
                finn=finn,
                user_id=user_id,
                query=request.query,
                context_payload=context_payload,
            )
            return await _finalize_finn_response(
                finn,
                user_id,
                rescue,
                trace_id,
                prompt=request.query,
                context_payload=context_payload,
                route_source="finn_core_rescue_exception",
                legacy_rescue_reason="legacy_exception",
                latency_ms=(time.perf_counter() - started_at) * 1000,
            )
        intent = service._classify_intent(request.query)
        if not isinstance(action, dict):
            action = None
        if not isinstance(draft, dict):
            draft = None
        if not isinstance(state, dict):
            state = None
        reasoning = None
        if not isinstance(suggested_actions, list):
            suggested_actions = None
        if _legacy_response_needs_finn_rescue(
            finn,
            request.query,
            context_payload,
            response_text=response,
            action=action,
            draft=draft,
            state=state,
        ):
            rescue = await _build_finn_core_rescue_envelope(
                finn=finn,
                user_id=user_id,
                query=request.query,
                context_payload=context_payload,
            )
            return await _finalize_finn_response(
                finn,
                user_id,
                rescue,
                trace_id,
                prompt=request.query,
                context_payload=context_payload,
                route_source="finn_core_rescue_legacy",
                legacy_rescue_reason="legacy_non_transactional_misroute_or_generic_failure",
                latency_ms=(time.perf_counter() - started_at) * 1000,
            )
        legacy_response = {
            "response": response,
            "intent": intent,
            "flow": (state or {}).get("current_flow"),
            "draft": draft,
            "state": state,
            "actions": action and [action] or [],
        }
        legacy_response = finn._build_response_analysis_metadata(
            legacy_response,
            context_payload,
            route_source="legacy",
        )
        _log_finn_prompt_audit(
            trace_id=trace_id,
            user_id=user_id,
            prompt=request.query,
            route_source="legacy_assistant",
            detected_intent=intent,
            intent_confidence=None,
            selected_flow=(state or {}).get("current_flow"),
            selected_entity=_audit_selected_entity(legacy_response, _assistant_context_payload(request.context)),
            context_payload=_assistant_context_payload(request.context),
            used_draft=bool(draft),
            draft_summary=_audit_draft_summary(draft),
            response_type=_audit_response_type(legacy_response),
            success=_audit_success_label(legacy_response),
            mode=(legacy_response.get("analysis") or {}).get("mode") or finn._response_mode_for_flow((state or {}).get("current_flow"), draft),
            context_confidence=(legacy_response.get("analysis") or {}).get("context_confidence"),
            draft_rejected_reason=(context_payload.get("_finn_sanitization") or {}).get("draft_rejected_reason"),
            latency_ms=(time.perf_counter() - started_at) * 1000,
        )
        return AssistantChatResponse(
            response=response,
            intent=intent,
            action=action,
            draft=draft,
            state=legacy_response.get("state"),
            reasoning=reasoning,
            suggested_actions=suggested_actions,
            trace_id=trace_id,
            session_id=actual_session_id
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
    started_at = time.perf_counter()

    async def event_generator():
        try:
            finn = FinnPlanService(db)
            context_payload = await finn.hydrate_context(user_id, _assistant_context_payload(request.context))
            context_payload = finn.sanitize_context_for_query(request.query, context_payload)
            _apply_assistant_rate_limit(
                user_id=user_id,
                raw_request=raw_request,
                query=request.query,
                context=context_payload,
                endpoint="/assistant/chat/stream",
            )
            if finn.looks_like_daily_score_refresh_request(request.query):
                envelope = await finn.build_daily_score_refresh_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_general_capability_request(request.query):
                envelope = await finn.build_general_capability_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_product_help_request(request.query, context_payload):
                envelope = await finn.build_product_help_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_education_request(request.query):
                envelope = await finn.build_education_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_mission_control_explain_request(request.query, context_payload):
                envelope = await finn.build_mission_control_explain_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_entity_explain_request(request.query, context_payload):
                envelope = await finn.build_context_explain_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_bot_decision_request(request.query) or _legacy_bot_decision_resume(
                request.query,
                context_payload,
            ):
                envelope = await finn.build_bot_decision_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, persist_state=True, prompt=request.query, context_payload=context_payload)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_bot_decision_review_request(request.query):
                envelope = await finn.build_bot_decision_review_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_bot_execution_decision_request(request.query):
                envelope = await finn.build_bot_execution_decision_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_finn_report_request(request.query):
                envelope = await finn.build_finn_report_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_behavioral_memory_request(request.query):
                envelope = await finn.build_behavioral_memory_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_weekly_reflection_request(request.query):
                envelope = await finn.build_weekly_reflection_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_behavioral_intelligence_request(request.query):
                envelope = await finn.build_behavioral_intelligence_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_daily_coach_request(request.query):
                envelope = await finn.build_daily_coach_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload)
                yield _sse_event("envelope", envelope)
                return

            if finn.is_cancel_request(request.query):
                envelope = await finn.build_cancel_response(user_id, context_payload)
                if envelope:
                    envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, persist_state=True, prompt=request.query, context_payload=context_payload)
                    yield _sse_event("envelope", envelope)
                    return

            if finn.looks_like_indicator_insight_request(request.query):
                envelope = await finn.build_indicator_insight_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_status_request(request.query):
                envelope = await finn.build_status_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_indicator_config_request(request.query, context_payload):
                envelope = await finn.build_indicator_config_response_for_user(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, persist_state=True, prompt=request.query, context_payload=context_payload)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_bot_request(request.query, context_payload):
                envelope = await finn.build_bot_response_for_user(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, persist_state=True, prompt=request.query, context_payload=context_payload)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_strategy_request(request.query, context_payload):
                envelope = await finn.build_strategy_response_for_user(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, persist_state=True, prompt=request.query, context_payload=context_payload)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_plan_request(request.query, context_payload.get("finn_draft")):
                envelope = finn.build_response(request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, persist_state=True, prompt=request.query, context_payload=context_payload)
                yield _sse_event("envelope", envelope)
                return

            try:
                async for chunk in service.get_chat_response_stream(
                    user_id, request.query, request.history, request.context,
                    trace_id=trace_id, background_tasks=background_tasks
                ):
                    if await raw_request.is_disconnected():
                        logger.warning(f"🔌 Client disconnected mid-stream | Trace: {trace_id}. Aborting stream generator.")
                        break

                    event_name = chunk["event"]
                    data_val = chunk["data"]

                    if event_name == "envelope" and isinstance(data_val, dict):
                        data_val["trace_id"] = trace_id
                        if _legacy_response_needs_finn_rescue(
                            finn,
                            request.query,
                            context_payload,
                            response_text=data_val.get("response"),
                            action=data_val.get("action"),
                            draft=data_val.get("draft"),
                            state=data_val.get("state"),
                        ):
                            rescue = await _build_finn_core_rescue_envelope(
                                finn=finn,
                                user_id=user_id,
                                query=request.query,
                                context_payload=context_payload,
                            )
                            rescue = await _prepare_finn_envelope(
                                finn,
                                user_id,
                                rescue,
                                trace_id,
                                prompt=request.query,
                                context_payload=context_payload,
                                route_source="finn_core_rescue_stream",
                                legacy_rescue_reason="legacy_stream_non_transactional_misroute_or_generic_failure",
                                latency_ms=(time.perf_counter() - started_at) * 1000,
                            )
                            yield _sse_event("envelope", rescue)
                            return

                    yield _sse_event(event_name, data_val)
            except Exception as legacy_exc:
                logger.warning("⚠️ Legacy assistant stream failed; trying FINN core rescue | Trace: %s | Error: %s", trace_id, legacy_exc)
                rescue = await _build_finn_core_rescue_envelope(
                    finn=finn,
                    user_id=user_id,
                    query=request.query,
                    context_payload=context_payload,
                )
                rescue = await _prepare_finn_envelope(
                    finn,
                    user_id,
                    rescue,
                    trace_id,
                    prompt=request.query,
                    context_payload=context_payload,
                    route_source="finn_core_rescue_stream_exception",
                    legacy_rescue_reason="legacy_stream_exception",
                    latency_ms=(time.perf_counter() - started_at) * 1000,
                )
                yield _sse_event("envelope", rescue)
                return
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
            finn = FinnPlanService(db, trace_id=trace_id)
            fallback_action = payload.get("action") if isinstance(payload.get("action"), dict) else None
            result = await finn.execute_issued_action(user_id, str(action_id), fallback_action=fallback_action)
            _invalidate_mission_control_cache(user_id)
            return result
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ AI Assistant Action Error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Fout bij Finn action")
    return await engine.execute_pending_action(action_id, user_id, trace_id=trace_id)

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
    request: Request = None,
):
    trace_id = getattr(request.state, "trace_id", None) if request else None
    cached = _get_cached_mission_control(current_user["id"])
    if cached:
        return cached
    finn = FinnPlanService(db, trace_id=trace_id)
    response = await finn.build_mission_control_response(
        current_user["id"],
        {"page": "assistant", "scope": "mission_control"},
    )
    await finn.issue_response_actions(current_user["id"], response)
    _store_cached_mission_control(current_user["id"], response)
    return response
