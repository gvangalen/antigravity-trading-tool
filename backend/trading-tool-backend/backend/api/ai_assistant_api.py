import logging
import os
import re
import time
import uuid
from copy import deepcopy
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks, Request
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
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
    AssistantAnalyticsEvent,
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
from backend.services.finn_product_analytics_service import finn_product_analytics
from backend.services.locale_service import localize_finn_payload, resolve_locale
from backend.services.trader_profile_service import (
    build_trader_profile_context,
    build_trader_profile_summary,
    has_trader_profile,
    normalize_trader_profile_preferences,
)
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.infrastructure.repositories.setup_repository import SetupRepository
from backend.infrastructure.repositories.report_repository import ReportRepository
from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
from backend.infrastructure.repositories.strategy_repository import StrategyRepository
from backend.infrastructure.repositories.conversation_state_repository import ConversationStateRepository
from backend.infrastructure.repositories.assistant_context_repository import AssistantContextRepository
from backend.services.ai_action_engine import AiActionEngine

if TYPE_CHECKING:
    from backend.services.ai_assistant_service import AiAssistantService
    from backend.services.finn_plan_service import FinnPlanService

router = APIRouter()
logger = logging.getLogger(__name__)
MISSION_CONTROL_CACHE_TTL_SECONDS = int(os.getenv("MISSION_CONTROL_CACHE_TTL_SECONDS", "20"))
_mission_control_cache: Dict[int, Dict[str, Any]] = {}


async def _issue_finn_response_actions_safely(
    finn: "FinnPlanService",
    db: Optional[AsyncSession],
    user_id: int,
    payload: dict,
    *,
    trace_id: Optional[str] = None,
    route_source: str = "finn",
) -> None:
    try:
        await finn.issue_response_actions(user_id, payload)
    except (DBAPIError, SQLAlchemyError) as exc:
        logger.warning(
            "Skipping FINN response action issuance after database failure on %s for user %s (trace_id=%s): %s",
            route_source,
            user_id,
            trace_id,
            exc,
        )
        if db is not None:
            await db.rollback()


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
    context_payload["locale"] = resolve_locale(preferences, context_payload)
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


def _legacy_draft_action_label(draft_type: str, locale: str) -> str:
    labels = {
        "setup": {
            "nl": "Setup opslaan",
            "en": "Save setup",
            "de": "Setup speichern",
        },
        "strategy": {
            "nl": "Strategie opslaan",
            "en": "Save strategy",
            "de": "Strategie speichern",
        },
        "bot": {
            "nl": "Bot opslaan",
            "en": "Save bot",
            "de": "Bot speichern",
        },
    }
    return labels.get(draft_type, {}).get(locale) or labels.get(draft_type, {}).get("en") or "Save draft"


async def _ensure_pending_action_ids(
    db: AsyncSession,
    user_id: int,
    response: Optional[dict],
    *,
    locale: str = "nl",
    trace_id: Optional[str] = None,
) -> dict:
    payload = deepcopy(response or {})
    engine = AiActionEngine(db)
    actions = payload.get("actions") if isinstance(payload.get("actions"), list) else []
    draft = payload.get("draft") if isinstance(payload.get("draft"), dict) else None

    normalized_actions: List[Dict[str, Any]] = []
    for raw_action in actions:
        if not isinstance(raw_action, dict):
            continue
        action = dict(raw_action)
        action_type = str(action.get("type") or "").strip()
        existing_action_id = action.get("action_id") or action.get("id")
        if not existing_action_id and action_type in {"add_to_watchlist", "remove_from_watchlist"}:
            registration_payload = {"symbol": str(action.get("symbol") or "").upper()}
            pending_action_id = await engine.register_pending_action(
                user_id,
                action_type,
                registration_payload,
                trace_id=trace_id,
            )
            action["action_id"] = pending_action_id
            action["id"] = pending_action_id
        normalized_actions.append(action)

    if not normalized_actions and draft:
        draft_type = str(draft.get("type") or "").strip().lower()
        draft_payload = draft.get("payload") if isinstance(draft.get("payload"), dict) else None
        supported_draft_types = {"setup": "setup", "strategy": "strategy", "bot": "bot"}
        mapped_action_type = supported_draft_types.get(draft_type)
        if mapped_action_type and draft_payload:
            pending_action_id = await engine.register_pending_action(
                user_id,
                mapped_action_type,
                dict(draft_payload),
                trace_id=trace_id,
            )
            normalized_actions = [{
                "type": mapped_action_type,
                "action_id": pending_action_id,
                "id": pending_action_id,
                "label": _legacy_draft_action_label(draft_type, locale),
                "requires_confirmation": True,
            }]

    if normalized_actions:
        payload["actions"] = normalized_actions
        payload["action"] = normalized_actions[0]
        payload["can_confirm"] = True

    return payload


KNOWN_FINN_ASSETS = ("BTC", "ETH", "SOL")
PROFILE_VALUE_LABELS = {
    "swing_trader": "swing trader",
    "day_trader": "day trader",
    "scalper": "scalper",
    "investor": "investeerder",
    "dca_investor": "DCA-investeerder",
    "1h": "1H",
    "4h": "4H",
    "1d": "1D",
    "1w": "1W",
    "1m": "1M",
    "15m": "15m",
    "5m": "5m",
    "bitcoin": "BTC",
    "crypto_general": "crypto",
    "fomo": "FOMO / jagen",
    "takes_profit_too_early": "winst te vroeg nemen",
    "holds_losers_too_long": "verliezers te lang laten lopen",
    "overtrades": "overtraden",
}


def _extract_asset_from_query(query: str) -> Optional[str]:
    upper = str(query or "").upper()
    for symbol in KNOWN_FINN_ASSETS:
        if re.search(rf"\b{re.escape(symbol)}\b", upper):
            return symbol
    return None


def _looks_like_watchlist_mutation(query: str) -> bool:
    q = str(query or "").lower()
    has_watchlist = "watchlist" in q or "volglijst" in q
    has_mutation = any(term in q for term in [
        "voeg", "toe", "add", "zet", "plaats", "verwijder", "haal", "remove",
    ])
    return has_watchlist and has_mutation


def _looks_like_setup_strategy_listing_request(query: str) -> bool:
    q = str(query or "").lower()
    has_listing_intent = any(term in q for term in ["laat", "toon", "geef", "welke", "wat zijn", "overzicht"])
    has_entity = any(term in q for term in [
        "actieve setups",
        "mijn setups",
        " set-ups",
        "setups",
        "actieve strategie",
        "actieve strategieën",
        "mijn strategie",
        "mijn strategieën",
        "strategieën",
        "strategies",
    ])
    return has_listing_intent and has_entity


def _humanize_profile_values(values: Optional[list]) -> str:
    return ", ".join(PROFILE_VALUE_LABELS.get(str(value), str(value)) for value in (values or []))


def _build_watchlist_mutation_envelope(query: str, context_payload: Optional[dict] = None) -> Optional[Dict[str, Any]]:
    q = str(query or "").lower()
    context_payload = context_payload or {}
    symbol = _extract_asset_from_query(query) or str(context_payload.get("symbol") or context_payload.get("asset") or "").upper() or None
    if not symbol:
        return {
            "response": "Noem eerst het asset dat je aan je watchlist wilt toevoegen of eruit wilt halen, bijvoorbeeld BTC, ETH of SOL.",
            "intent": "watchlist_mutation",
            "flow": "general_help",
            "actions": [],
            "suggested_actions": ["Voeg BTC toe aan mijn watchlist", "Voeg ETH toe aan mijn watchlist"],
        }

    is_remove = any(term in q for term in ["verwijder", "haal", "remove"])
    action_type = "remove_from_watchlist" if is_remove else "add_to_watchlist"
    response = (
        f"Ik kan {symbol} {'uit' if is_remove else 'aan'} je watchlist {'halen' if is_remove else 'toevoegen'}. "
        "Bevestig dat via de actie hieronder."
    )
    return {
        "response": response,
        "intent": "watchlist_mutation",
        "flow": "general_help",
        "actions": [{
            "type": action_type,
            "symbol": symbol,
            "label": f"{'Verwijder' if is_remove else 'Voeg'} {symbol} {'uit' if is_remove else 'aan'} watchlist",
        }],
        "suggested_actions": [],
    }


async def _build_setup_strategy_listing_envelope(
    db: AsyncSession,
    user_id: int,
) -> Dict[str, Any]:
    setup_repo = SetupRepository(db)
    strategy_repo = StrategyRepository(db)
    setups = await setup_repo.get_top_setups(user_id, 3)
    strategies = await strategy_repo.query_strategies(user_id, {})

    setup_lines = []
    for setup in setups[:3]:
        symbol = str(setup.get("symbol") or "").upper()
        timeframe = setup.get("timeframe") or "?"
        name = setup.get("name") or f"{symbol} setup"
        setup_lines.append(f"- Setup #{setup.get('id')}: {name} ({symbol} · {timeframe})")

    strategy_lines = []
    for strategy in strategies[:3]:
        symbol = str(strategy.get("setup_symbol") or "").upper()
        timeframe = strategy.get("setup_timeframe") or "?"
        name = strategy.get("name") or f"{symbol} strategie"
        strategy_lines.append(f"- Strategie #{strategy.get('id')}: {name} ({symbol} · {timeframe})")

    if not setup_lines and not strategy_lines:
        response = (
            "Je hebt nog geen opgeslagen setups of strategieën. "
            "Begin met een asset in je watchlist of vraag Finn om eerst een setup voor je te maken."
        )
    else:
        sections = []
        if setup_lines:
            sections.append("Je recente setups:\n" + "\n".join(setup_lines))
        if strategy_lines:
            sections.append("Je recente strategieën:\n" + "\n".join(strategy_lines))
        response = "\n\n".join(sections)

    return {
        "response": response,
        "intent": "entity_list",
        "flow": "general_help",
        "state": {
            "current_flow": "general_help",
            "setup_count": len(setups),
            "strategy_count": len(strategies),
        },
        "actions": [],
    }


def _extract_profile_update_from_query(query: str) -> Dict[str, Any]:
    q = str(query or "").lower()
    payload: Dict[str, Any] = {}

    trader_types = []
    if "swing trader" in q or "swingtrader" in q:
        trader_types.append("swing_trader")
    if "day trader" in q or "daytrader" in q:
        trader_types.append("day_trader")
    if "scalper" in q:
        trader_types.append("scalper")
    if "investeerder" in q or re.search(r"\binvestor\b", q):
        trader_types.append("investor")
    if "dca" in q and "invest" in q:
        trader_types.append("dca_investor")
    if trader_types:
        payload["trader_types"] = trader_types

    timeframe_map = {
        "4h": "4h",
        "4u": "4h",
        "1d": "1d",
        "daily": "1d",
        "dag": "1d",
        "1w": "1w",
        "week": "1w",
        "1m": "1m",
        "maand": "1m",
        "1h": "1h",
        "15m": "15m",
        "5m": "5m",
    }
    primary_timeframes = []
    for needle, canonical in timeframe_map.items():
        if needle in q and canonical not in primary_timeframes:
            primary_timeframes.append(canonical)
    if primary_timeframes:
        payload["primary_timeframes"] = primary_timeframes

    asset_focus = []
    if "btc" in q or "bitcoin" in q:
        asset_focus.append("bitcoin")
    elif any(token in q for token in ["eth", "sol", "crypto", "altcoin"]):
        asset_focus.append("crypto_general")
    if asset_focus:
        payload["asset_focus"] = asset_focus

    behavior_flags = []
    if "fomo" in q:
        behavior_flags.append("fomo")
    if "te vroeg winst" in q or "profit too early" in q:
        behavior_flags.append("takes_profit_too_early")
    if "verliezers te lang" in q or "hold losers too long" in q:
        behavior_flags.append("holds_losers_too_long")
    if "overtrade" in q or "overtraden" in q:
        behavior_flags.append("overtrades")
    if behavior_flags:
        payload["behavior_flags"] = behavior_flags

    return normalize_trader_profile_preferences(payload)


def _looks_like_profile_capture(query: str) -> bool:
    q = str(query or "").lower()
    identity_cues = [
        "ik ben een",
        "ik ben ",
        "mijn profiel",
        "ik wil ",
        "ik trade",
        "ik handel",
    ]
    if not any(cue in q for cue in identity_cues):
        return False
    return has_trader_profile(_extract_profile_update_from_query(query))


def _looks_like_profile_explain(query: str) -> bool:
    q = str(query or "").lower()
    return (
        "wat is mijn profiel" in q
        or "hoe gebruik je dat in je advies" in q
        or ("mijn profiel" in q and any(term in q for term in ["gebruik", "advies", "samenvat", "uitleg"]))
    )


def _looks_like_explicit_setup_creation_request(query: str) -> bool:
    q = str(query or "").lower()
    if "setup" not in q:
        return False
    if any(term in q for term in [
        "maak een setup",
        "maak setup",
        "setup voor",
        "setup aanmaken",
        "nieuwe setup",
        "setup maken",
        "dca setup",
    ]):
        return True
    create_terms = [
        "maak",
        "maken",
        "aanmaken",
        "creeer",
        "creeër",
        "bouw",
        "wil",
        "kan je",
        "kun je",
        "help me",
        "help mij",
        "start",
    ]
    setup_modifiers = [
        "dca",
        "trade",
        "swing",
        "entry",
        "trend",
        "blueprint",
    ]
    return any(term in q for term in create_terms) and any(term in q for term in setup_modifiers)


def _should_prefer_legacy_setup_flow(query: str, context_payload: Optional[dict] = None) -> bool:
    context_payload = context_payload or {}
    current_flow = str(context_payload.get("current_flow") or "").lower()
    if current_flow == "setup_creation":
        return True
    return False


def _should_use_modern_setup_creation_flow(query: str, context_payload: Optional[dict] = None) -> bool:
    context_payload = context_payload or {}
    current_flow = str(context_payload.get("current_flow") or "").lower()
    if current_flow == "setup_creation":
        return True
    if not _looks_like_explicit_setup_creation_request(query):
        return False
    page = str(context_payload.get("page") or "").strip("/").lower()
    step = str(
        context_payload.get("step")
        or context_payload.get("onboarding_step")
        or context_payload.get("onboardingStep")
        or ""
    ).lower()
    return page == "setup" or step == "setup"


def _is_legacy_transactional_flow_name(flow_name: Optional[str]) -> bool:
    return str(flow_name or "").strip().lower() in {
        "setup_creation",
        "bot_creation",
        "indicator_config",
    }


def _is_modern_transactional_state_record(state: Optional[dict]) -> bool:
    if not isinstance(state, dict):
        return False
    slots = state.get("slots")
    if not isinstance(slots, dict):
        return False
    if slots.get("state_bucket") == "transactional_state":
        return True
    if isinstance(slots.get("draft"), dict):
        return True
    return bool(slots.get("version"))


def _modern_transactional_flow_name(state: Optional[dict], context_payload: Optional[dict] = None) -> Optional[str]:
    flow_name = str((state or {}).get("current_flow") or (context_payload or {}).get("current_flow") or "").strip().lower()
    if flow_name in {"setup_creation", "strategy_creation", "bot_creation", "indicator_config", "plan_creation"}:
        return flow_name
    return None


def _clear_modern_transactional_context(context_payload: Optional[dict]) -> None:
    if not isinstance(context_payload, dict):
        return
    context_payload.pop("finn_draft", None)
    context_payload.pop("finn_state", None)
    if _modern_transactional_flow_name(None, context_payload):
        context_payload.pop("current_flow", None)


def _looks_like_explicit_new_plan_request(query: str) -> bool:
    q = str(query or "").lower()
    return any(trigger in q for trigger in [
        "maak een dca",
        "maak een wekelijkse",
        "maak een maandelijkse",
        "maak een dagelijkse",
        "wekelijkse dca",
        "maandelijkse dca",
        "dagelijkse dca",
        "elke week",
        "iedere week",
        "elke maand",
        "iedere maand",
        "dca van",
    ])


def _build_profile_saved_envelope(profile: Dict[str, Any]) -> Dict[str, Any]:
    summary = build_trader_profile_summary(profile)
    lines = []
    if profile.get("trader_types"):
        lines.append(f"stijl: {_humanize_profile_values(profile['trader_types'])}")
    if profile.get("primary_timeframes"):
        lines.append(f"timeframes: {_humanize_profile_values(profile['primary_timeframes'])}")
    if profile.get("asset_focus"):
        lines.append(f"focus: {_humanize_profile_values(profile['asset_focus'])}")
    if profile.get("behavior_flags"):
        lines.append(f"coachingpunten: {_humanize_profile_values(profile['behavior_flags'])}")
    details = "; ".join(lines) if lines else summary
    return {
        "response": (
            "Ik heb je traderprofiel bijgewerkt. "
            f"Ik gebruik dit nu in coaching, uitleg en waarschuwingen. {details}."
        ),
        "intent": "profile_updated",
        "flow": "general_help",
        "state": {
            "current_flow": "profile_updated",
            "profile_summary": summary,
        },
        "actions": [],
    }


def _build_profile_explain_envelope(profile: Dict[str, Any]) -> Dict[str, Any]:
    summary = build_trader_profile_summary(profile)
    if not has_trader_profile(profile):
        return {
            "response": (
                "Ik zie nog geen ingevuld traderprofiel. Vul eerst je stijl, timeframes of focus in, "
                "dan kan ik coaching en waarschuwingen daarop afstemmen."
            ),
            "intent": "profile_explain",
            "flow": "general_help",
            "actions": [],
        }
    return {
        "response": (
            f"Je huidige profiel is: {summary}. "
            "Ik gebruik dat om uitleg, coaching, frictie en prioriteiten beter op jouw handelsstijl af te stemmen."
        ),
        "intent": "profile_explain",
        "flow": "general_help",
        "state": {
            "current_flow": "profile_explain",
            "profile_summary": summary,
        },
        "actions": [],
    }


async def _continue_transactional_follow_up(
    finn: Any,
    user_id: int,
    query: str,
    context_payload: Optional[dict],
) -> Optional[Dict[str, Any]]:
    payload = context_payload or {}
    draft = payload.get("finn_draft") if isinstance(payload.get("finn_draft"), dict) else None
    active_flow = _modern_transactional_flow_name(payload.get("finn_state"), payload)
    if not draft or not active_flow or not finn._looks_like_transactional_follow_up(query, draft):
        return None
    if active_flow != "plan_creation" and (finn.looks_like_plan_request(query, None) or _looks_like_explicit_new_plan_request(query)):
        _clear_modern_transactional_context(payload)
        return None
    if active_flow != "strategy_creation" and finn.looks_like_strategy_request(query, {}):
        _clear_modern_transactional_context(payload)
        return None
    if active_flow != "bot_creation" and finn.looks_like_bot_request(query, {}):
        _clear_modern_transactional_context(payload)
        return None
    if active_flow != "indicator_config" and finn.looks_like_indicator_config_request(query, {}):
        _clear_modern_transactional_context(payload)
        return None

    if active_flow == "setup_creation":
        return finn.build_setup_response(query, payload)
    if active_flow == "strategy_creation":
        return await finn.build_strategy_response_for_user(user_id, query, payload)
    if active_flow == "bot_creation":
        return await finn.build_bot_response_for_user(user_id, query, payload)
    if active_flow == "indicator_config":
        return await finn.build_indicator_config_response_for_user(user_id, query, payload)
    return finn.build_response(query, payload)


def _attach_trader_profile_metadata(response: Optional[dict], context_payload: Optional[dict]) -> dict:
    payload = dict(response or {})
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    analysis["trader_profile_used"] = bool((context_payload or {}).get("trader_profile_used"))
    analysis["trader_profile_summary"] = (context_payload or {}).get("trader_profile_summary") or ""
    analysis["profile_match_mode"] = (context_payload or {}).get("profile_match_mode") or "profile_missing_fallback"
    analysis["profile_match_reason"] = (context_payload or {}).get("profile_match_reason") or ""
    analysis["profile_conflict_detected"] = bool((context_payload or {}).get("profile_conflict_detected"))
    payload["analysis"] = analysis
    return payload


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


def _audit_success_label(response: Optional[dict]) -> str:
    response = response or {}
    text = str(response.get("response") or "").lower()
    if "kon geen analyse ophalen" in text:
        return "failure"
    if text.startswith("⚠️") or text.startswith("warning"):
        return "degraded"
    return "success"


def _normalize_finn_response_contract(response: Optional[dict]) -> dict:
    payload = deepcopy(response or {})
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    state_analysis = state.get("analysis") if isinstance(state.get("analysis"), dict) else {}

    summary = (
        payload.get("summary")
        or analysis.get("summary")
        or state_analysis.get("summary")
        or analysis.get("headline")
        or state_analysis.get("headline")
        or payload.get("response")
    )
    risk_summary = (
        payload.get("risk_summary")
        or analysis.get("risk_summary")
        or state_analysis.get("risk_summary")
        or analysis.get("portfolio_risk", {}).get("message")
        or state_analysis.get("portfolio_risk", {}).get("message")
        or analysis.get("review_reason")
        or state_analysis.get("review_reason")
    )
    next_best_action = (
        payload.get("next_best_action")
        or analysis.get("next_best_action")
        or state_analysis.get("next_best_action")
        or (analysis.get("next_best_actions") or [None])[0]
        or (state_analysis.get("next_best_actions") or [None])[0]
    )
    review_reason = (
        payload.get("review_reason")
        or analysis.get("review_reason")
        or state_analysis.get("review_reason")
        or analysis.get("adherence_reason")
        or state_analysis.get("adherence_reason")
    )

    if isinstance(next_best_action, dict):
        next_best_action = (
            next_best_action.get("label")
            or next_best_action.get("prompt")
            or next_best_action.get("title")
        )

    payload["summary"] = str(summary).strip() if summary else None
    payload["risk_summary"] = str(risk_summary).strip() if risk_summary else None
    payload["next_best_action"] = str(next_best_action).strip() if next_best_action else None
    payload["review_reason"] = str(review_reason).strip() if review_reason else None
    return payload


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


def _record_behavioral_response_events(
    *,
    user_id: int,
    response: dict,
    context_payload: Optional[dict],
    route_source: str,
    trace_id: str,
) -> None:
    payload = context_payload or {}
    analysis = response.get("analysis") if isinstance(response.get("analysis"), dict) else {}
    state = response.get("state") if isinstance(response.get("state"), dict) else {}
    base_metadata = {
        "intent": response.get("intent"),
        **_trader_profile_event_metadata(payload),
    }
    base_event = {
        "user_id": user_id,
        "session_id": payload.get("session_id"),
        "surface": route_source,
        "page": payload.get("page"),
        "asset": payload.get("symbol") or payload.get("asset"),
        "flow_type": response.get("flow") or state.get("current_flow"),
        "bot_id": state.get("bot_id") or payload.get("bot_id"),
        "setup_id": state.get("setup_id") or payload.get("setup_id"),
        "strategy_id": state.get("strategy_id") or payload.get("strategy_id"),
        "trace_id": trace_id,
        "next_best_action": response.get("next_best_action"),
    }
    profile_guidance = analysis.get("profile_guidance")
    if profile_guidance:
        _record_finn_product_event(
            event_name="behavioral_intervention_seen",
            metadata={
                **base_metadata,
                "behavior_label": "profile_guidance",
                "intervention_type": "profile_guidance",
                "intervention_copy": str(profile_guidance),
            },
            **base_event,
        )
    profile_alignment = analysis.get("profile_habit_alignment")
    if isinstance(profile_alignment, dict):
        primary_alignment = profile_alignment.get("primary_alignment")
        if isinstance(primary_alignment, dict) and primary_alignment.get("flag"):
            _record_finn_product_event(
                event_name="behavioral_intervention_seen",
                metadata={
                    **base_metadata,
                    "behavior_flag": str(primary_alignment.get("flag")),
                    "behavior_label": str(primary_alignment.get("label") or primary_alignment.get("flag")),
                    "intervention_type": "profile_habit_alignment",
                    "intervention_copy": str(primary_alignment.get("summary") or ""),
                    "evidence_strength": primary_alignment.get("evidence_strength"),
                    "matched_sources": list(primary_alignment.get("matched_sources") or []),
                    "matched_sources_count": len(primary_alignment.get("matched_sources") or []),
                },
                **base_event,
            )
    pending_friction = state.get("pending_behavioral_memory_friction")
    if isinstance(pending_friction, dict):
        _record_finn_product_event(
            event_name="behavioral_intervention_seen",
            metadata={
                **base_metadata,
                "behavior_flag": str((pending_friction.get("type") or "").replace("profile_", "")),
                "behavior_label": str(pending_friction.get("type") or "behavioral_memory_friction"),
                "intervention_type": "pending_behavioral_memory_friction",
                "intervention_copy": str(pending_friction.get("message") or ""),
                "requires_ack": bool(pending_friction.get("requires_ack")),
                "source": pending_friction.get("source"),
            },
            **base_event,
        )


def _legacy_response_is_generic_failure(response_text: Optional[str]) -> bool:
    text = str(response_text or "").strip().lower()
    if not text:
        return True
    return (
        "kon geen analyse ophalen" in text
        or "probeer opnieuw" in text and text.startswith("⚠️")
        or "interne authenticatiefout" in text
        or "insufficient_quota" in text
        or "ai quota bereikt" in text
    )


def _query_prefers_non_transactional_finn_response(
    finn: Any,
    query: str,
    context_payload: Optional[dict],
) -> bool:
    context_payload = context_payload or {}
    return any([
        finn.looks_like_general_capability_request(query),
        finn.looks_like_product_refresh_help_request(query),
        finn.looks_like_product_help_request(query, context_payload),
        finn.looks_like_education_request(query),
        finn.looks_like_plan_adherence_review_request(query),
        finn.looks_like_outcome_tracking_request(query),
        finn.looks_like_governed_action_review_request(query, context_payload),
        finn.looks_like_outcome_memory_request(query),
        finn.looks_like_personal_performance_request(query),
        finn.looks_like_trade_journal_intelligence_request(query),
        finn.looks_like_personal_coach_request(query),
        finn.looks_like_portfolio_intelligence_request(query, context_payload),
        finn.looks_like_priority_engine_request(query, context_payload),
        finn.looks_like_portfolio_operating_system_request(query),
        finn.looks_like_decision_review_request(query, context_payload),
        finn.looks_like_ultra_implicit_review_prompt(query),
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
    finn: Any,
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
    current_flow = str((state or {}).get("current_flow") or "").lower()
    if current_flow in {"setup_creation", "strategy_creation", "bot_creation", "indicator_config"}:
        return _legacy_response_is_generic_failure(response_text)
    if _query_prefers_non_transactional_finn_response(finn, query, context_payload):
        return True
    if _legacy_response_is_generic_failure(response_text):
        return True
    if not _query_prefers_non_transactional_finn_response(finn, query, context_payload):
        return False
    return current_flow in {"setup_creation", "strategy_creation", "bot_creation", "indicator_config"}


async def _build_finn_core_rescue_envelope(
    *,
    finn: Any,
    user_id: int,
    query: str,
    context_payload: Optional[dict],
) -> dict:
    context_payload = context_payload or {}
    if finn.looks_like_general_capability_request(query):
        return await finn.build_general_capability_response(user_id, query, context_payload)
    if finn.looks_like_product_refresh_help_request(query):
        return await finn.build_product_refresh_help_response(user_id, query, context_payload)
    if finn.looks_like_product_help_request(query, context_payload):
        return await finn.build_product_help_response(user_id, query, context_payload)
    if finn.looks_like_education_request(query):
        return await finn.build_education_response(user_id, query, context_payload)
    if finn.looks_like_plan_adherence_review_request(query):
        return await finn.build_plan_adherence_review_response(user_id, query, context_payload)
    if finn.looks_like_outcome_tracking_request(query):
        return await finn.build_outcome_tracking_response(user_id, query, context_payload)
    if finn.looks_like_governed_action_review_request(query, context_payload):
        return await finn.build_governed_action_review_response(user_id, query, context_payload)
    if finn.looks_like_outcome_memory_request(query):
        return await finn.build_outcome_memory_response(user_id, query, context_payload)
    if finn.looks_like_personal_coach_request(query):
        return await finn.build_personal_coach_response(user_id, query, context_payload)
    if finn.looks_like_personal_performance_request(query):
        return await finn.build_personal_performance_response(user_id, query, context_payload)
    if finn.looks_like_trade_journal_intelligence_request(query):
        return await finn.build_trade_journal_intelligence_response(user_id, query, context_payload)
    if finn.looks_like_portfolio_intelligence_request(query, context_payload):
        return await finn.build_portfolio_intelligence_response(user_id, query, context_payload)
    if finn.looks_like_priority_engine_request(query, context_payload):
        return await finn.build_priority_engine_response(user_id, query, context_payload)
    if finn.looks_like_portfolio_operating_system_request(query):
        return await finn.build_portfolio_operating_system_response(user_id, query, context_payload)
    if finn.looks_like_decision_review_request(query, context_payload):
        return await finn.build_decision_review_response(user_id, query, context_payload)
    if finn.should_route_ultra_implicit_prompt_to_decision_review(query, context_payload):
        return await finn.build_decision_review_response(user_id, query, context_payload)
    if finn.looks_like_ultra_implicit_review_prompt(query):
        return await finn.build_quick_general_help_response(user_id, query, context_payload)
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
    from backend.services.ai_assistant_service import AiAssistantService
    from backend.services.ai_gateway import AiGateway

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


def _new_finn_plan_service(db: AsyncSession, *, trace_id: Optional[str] = None):
    from backend.services.finn_plan_service import FinnPlanService

    return FinnPlanService(db, trace_id=trace_id)


async def _finalize_finn_response(
    finn: Any,
    user_id: int,
    response: dict,
    trace_id: str,
    *,
    db: Optional[AsyncSession] = None,
    persist_state: bool = True,
    prompt: Optional[str] = None,
    context_payload: Optional[dict] = None,
    route_source: str = "finn",
    legacy_rescue_reason: Optional[str] = None,
    latency_ms: Optional[float] = None,
) -> AssistantChatResponse:
    response["trace_id"] = trace_id
    if db is not None:
        response = await _ensure_pending_action_ids(
            db,
            user_id,
            response,
            locale=(context_payload or {}).get("locale") or "nl",
            trace_id=trace_id,
        )
    response = finn._build_response_analysis_metadata(response, context_payload, route_source=route_source)
    response = _attach_trader_profile_metadata(response, context_payload)
    response = _normalize_finn_response_contract(response)
    response = await localize_finn_payload(response, (context_payload or {}).get("locale") or "nl")
    _redact_assistant_reasoning(response)
    await _issue_finn_response_actions_safely(
        finn,
        db,
        user_id,
        response,
        trace_id=trace_id,
        route_source=route_source,
    )
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
    _record_finn_product_event(
        user_id=user_id,
        event_name="finn_response_received",
        session_id=(context_payload or {}).get("session_id"),
        surface=route_source,
        page=(context_payload or {}).get("page"),
        asset=(context_payload or {}).get("symbol") or (context_payload or {}).get("asset"),
        flow_type=response.get("flow") or (response.get("state") or {}).get("current_flow"),
        bot_id=(response.get("state") or {}).get("bot_id") or (context_payload or {}).get("bot_id"),
        setup_id=(response.get("state") or {}).get("setup_id") or (context_payload or {}).get("setup_id"),
        strategy_id=(response.get("state") or {}).get("strategy_id") or (context_payload or {}).get("strategy_id"),
        trace_id=trace_id,
        next_best_action=response.get("next_best_action"),
        metadata={
            "intent": response.get("intent"),
            **_trader_profile_event_metadata(context_payload),
        },
    )
    if (context_payload or {}).get("trader_profile_used"):
        _record_finn_product_event(
            user_id=user_id,
            event_name="finn_profile_context_used",
            session_id=(context_payload or {}).get("session_id"),
            surface=route_source,
            page=(context_payload or {}).get("page"),
            asset=(context_payload or {}).get("symbol") or (context_payload or {}).get("asset"),
            flow_type=response.get("flow") or (response.get("state") or {}).get("current_flow"),
            bot_id=(response.get("state") or {}).get("bot_id") or (context_payload or {}).get("bot_id"),
            setup_id=(response.get("state") or {}).get("setup_id") or (context_payload or {}).get("setup_id"),
            strategy_id=(response.get("state") or {}).get("strategy_id") or (context_payload or {}).get("strategy_id"),
            trace_id=trace_id,
            next_best_action=response.get("next_best_action"),
            metadata=_trader_profile_event_metadata(context_payload),
        )
    if (context_payload or {}).get("profile_conflict_detected"):
        _record_finn_product_event(
            user_id=user_id,
            event_name="finn_profile_conflict_detected",
            session_id=(context_payload or {}).get("session_id"),
            surface=route_source,
            page=(context_payload or {}).get("page"),
            asset=(context_payload or {}).get("symbol") or (context_payload or {}).get("asset"),
            flow_type=response.get("flow") or (response.get("state") or {}).get("current_flow"),
            bot_id=(response.get("state") or {}).get("bot_id") or (context_payload or {}).get("bot_id"),
            setup_id=(response.get("state") or {}).get("setup_id") or (context_payload or {}).get("setup_id"),
            strategy_id=(response.get("state") or {}).get("strategy_id") or (context_payload or {}).get("strategy_id"),
            trace_id=trace_id,
            next_best_action=response.get("next_best_action"),
            metadata=_trader_profile_event_metadata(context_payload),
        )
    _record_behavioral_response_events(
        user_id=user_id,
        response=response,
        context_payload=context_payload,
        route_source=route_source,
        trace_id=trace_id,
    )
    return AssistantChatResponse(**response)


async def _prepare_finn_envelope(
    finn: Any,
    user_id: int,
    envelope: dict,
    trace_id: str,
    *,
    db: Optional[AsyncSession] = None,
    persist_state: bool = True,
    prompt: Optional[str] = None,
    context_payload: Optional[dict] = None,
    route_source: str = "finn_stream",
    legacy_rescue_reason: Optional[str] = None,
    latency_ms: Optional[float] = None,
) -> dict:
    envelope["trace_id"] = trace_id
    if db is not None:
        envelope = await _ensure_pending_action_ids(
            db,
            user_id,
            envelope,
            locale=(context_payload or {}).get("locale") or "nl",
            trace_id=trace_id,
        )
    envelope = finn._build_response_analysis_metadata(envelope, context_payload, route_source=route_source)
    envelope = _attach_trader_profile_metadata(envelope, context_payload)
    envelope = _normalize_finn_response_contract(envelope)
    envelope = await localize_finn_payload(envelope, (context_payload or {}).get("locale") or "nl")
    _redact_assistant_reasoning(envelope)
    await _issue_finn_response_actions_safely(
        finn,
        db,
        user_id,
        envelope,
        trace_id=trace_id,
        route_source=route_source,
    )
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
    _record_finn_product_event(
        user_id=user_id,
        event_name="finn_response_received",
        session_id=(context_payload or {}).get("session_id"),
        surface=route_source,
        page=(context_payload or {}).get("page"),
        asset=(context_payload or {}).get("symbol") or (context_payload or {}).get("asset"),
        flow_type=envelope.get("flow") or (envelope.get("state") or {}).get("current_flow"),
        bot_id=(envelope.get("state") or {}).get("bot_id") or (context_payload or {}).get("bot_id"),
        setup_id=(envelope.get("state") or {}).get("setup_id") or (context_payload or {}).get("setup_id"),
        strategy_id=(envelope.get("state") or {}).get("strategy_id") or (context_payload or {}).get("strategy_id"),
        trace_id=trace_id,
        next_best_action=envelope.get("next_best_action"),
        metadata={
            "intent": envelope.get("intent"),
            **_trader_profile_event_metadata(context_payload),
        },
    )
    if (context_payload or {}).get("trader_profile_used"):
        _record_finn_product_event(
            user_id=user_id,
            event_name="finn_profile_context_used",
            session_id=(context_payload or {}).get("session_id"),
            surface=route_source,
            page=(context_payload or {}).get("page"),
            asset=(context_payload or {}).get("symbol") or (context_payload or {}).get("asset"),
            flow_type=envelope.get("flow") or (envelope.get("state") or {}).get("current_flow"),
            bot_id=(envelope.get("state") or {}).get("bot_id") or (context_payload or {}).get("bot_id"),
            setup_id=(envelope.get("state") or {}).get("setup_id") or (context_payload or {}).get("setup_id"),
            strategy_id=(envelope.get("state") or {}).get("strategy_id") or (context_payload or {}).get("strategy_id"),
            trace_id=trace_id,
            next_best_action=envelope.get("next_best_action"),
            metadata=_trader_profile_event_metadata(context_payload),
        )
    if (context_payload or {}).get("profile_conflict_detected"):
        _record_finn_product_event(
            user_id=user_id,
            event_name="finn_profile_conflict_detected",
            session_id=(context_payload or {}).get("session_id"),
            surface=route_source,
            page=(context_payload or {}).get("page"),
            asset=(context_payload or {}).get("symbol") or (context_payload or {}).get("asset"),
            flow_type=envelope.get("flow") or (envelope.get("state") or {}).get("current_flow"),
            bot_id=(envelope.get("state") or {}).get("bot_id") or (context_payload or {}).get("bot_id"),
            setup_id=(envelope.get("state") or {}).get("setup_id") or (context_payload or {}).get("setup_id"),
            strategy_id=(envelope.get("state") or {}).get("strategy_id") or (context_payload or {}).get("strategy_id"),
            trace_id=trace_id,
            next_best_action=envelope.get("next_best_action"),
            metadata=_trader_profile_event_metadata(context_payload),
        )
    _record_behavioral_response_events(
        user_id=user_id,
        response=envelope,
        context_payload=context_payload,
        route_source=route_source,
        trace_id=trace_id,
    )
    return envelope


async def _finalize_legacy_response(
    *,
    service: Any,
    response: Optional[str],
    action: Optional[dict],
    draft: Optional[dict],
    state: Optional[dict],
    reasoning: Optional[str],
    suggested_actions: Optional[list],
    session_id: Optional[str],
    finn: Any,
    user_id: int,
    trace_id: str,
    db: Optional[AsyncSession],
    query: str,
    context_payload: Optional[dict],
    started_at: float,
) -> AssistantChatResponse:
    intent = service._classify_intent(query)
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
        query,
        context_payload,
        response_text=response,
        action=action,
        draft=draft,
        state=state,
    ):
        rescue = await _build_finn_core_rescue_envelope(
            finn=finn,
            user_id=user_id,
            query=query,
            context_payload=context_payload,
        )
        return await _finalize_finn_response(
            finn,
            user_id,
            rescue,
            trace_id,
            db=db,
            prompt=query,
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
        "missing_fields": (state or {}).get("missing_fields") or (state or {}).get("missing_slots") or [],
        "next_question": (state or {}).get("next_question"),
        "can_confirm": False,
    }
    if db is not None:
        legacy_response = await _ensure_pending_action_ids(
            db,
            user_id,
            legacy_response,
            locale=(context_payload or {}).get("locale") or "nl",
            trace_id=trace_id,
        )
    legacy_response = finn._build_response_analysis_metadata(
        legacy_response,
        context_payload,
        route_source="legacy",
    )
    legacy_response = _attach_trader_profile_metadata(legacy_response, context_payload)
    legacy_response = _normalize_finn_response_contract(legacy_response)
    _log_finn_prompt_audit(
        trace_id=trace_id,
        user_id=user_id,
        prompt=query,
        route_source="legacy_assistant",
        detected_intent=intent,
        intent_confidence=None,
        selected_flow=(state or {}).get("current_flow"),
        selected_entity=_audit_selected_entity(legacy_response, context_payload),
        context_payload=context_payload,
        used_draft=bool(draft),
        draft_summary=_audit_draft_summary(draft),
        response_type=_audit_response_type(legacy_response),
        success=_audit_success_label(legacy_response),
        mode=(legacy_response.get("analysis") or {}).get("mode") or finn._response_mode_for_flow((state or {}).get("current_flow"), draft),
        context_confidence=(legacy_response.get("analysis") or {}).get("context_confidence"),
        draft_rejected_reason=(context_payload.get("_finn_sanitization") or {}).get("draft_rejected_reason"),
        latency_ms=(time.perf_counter() - started_at) * 1000,
    )
    _record_finn_product_event(
        user_id=user_id,
        event_name="finn_response_received",
        session_id=session_id,
        surface="legacy_assistant",
        page=context_payload.get("page"),
        asset=context_payload.get("symbol") or context_payload.get("asset"),
        flow_type=(state or {}).get("current_flow"),
        bot_id=(state or {}).get("bot_id") or context_payload.get("bot_id"),
        setup_id=(state or {}).get("setup_id") or context_payload.get("setup_id"),
        strategy_id=(state or {}).get("strategy_id") or context_payload.get("strategy_id"),
        trace_id=trace_id,
        next_best_action=legacy_response.get("next_best_action"),
        metadata={
            "intent": intent,
            **_trader_profile_event_metadata(context_payload),
        },
    )
    _record_behavioral_response_events(
        user_id=user_id,
        response=legacy_response,
        context_payload=context_payload,
        route_source="legacy_assistant",
        trace_id=trace_id,
    )
    return AssistantChatResponse(
        response=legacy_response.get("response") or response,
        intent=legacy_response.get("intent") or intent,
        action=legacy_response.get("action"),
        draft=legacy_response.get("draft"),
        state=legacy_response.get("state"),
        reasoning=reasoning,
        suggested_actions=legacy_response.get("suggested_actions") or suggested_actions,
        trace_id=trace_id,
        session_id=session_id,
        flow=legacy_response.get("flow"),
        missing_fields=legacy_response.get("missing_fields") or [],
        invalid_fields=legacy_response.get("invalid_fields") or [],
        next_question=legacy_response.get("next_question"),
        can_confirm=bool(legacy_response.get("can_confirm")),
        actions=legacy_response.get("actions") or [],
        summary=legacy_response.get("summary"),
        risk_summary=legacy_response.get("risk_summary"),
        next_best_action=legacy_response.get("next_best_action"),
        review_reason=legacy_response.get("review_reason"),
    )


@router.post("/assistant/chat", response_model=AssistantChatResponse)
async def assistant_chat(
    request: AssistantChatRequest,
    raw_request: Request,
    x_trace_id: Optional[str] = Header(None),
    current_user: dict = Depends(get_current_user),
    service: Any = Depends(get_assistant_service),
    db: AsyncSession = Depends(get_db),
):
    trace_id = x_trace_id or f"trdm-trace-{uuid.uuid4().hex[:8]}-{hex(int(time.time()))[2:]}"
    started_at = time.perf_counter()
    try:
        user_id = current_user["id"]
        finn = _new_finn_plan_service(db)
        context_payload = await finn.hydrate_context(user_id, _assistant_context_payload(request.context))
        context_payload = finn.sanitize_context_for_query(request.query, context_payload)
        context_payload = await _enrich_with_trader_profile(db, user_id, context_payload, query=request.query)
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
        if _looks_like_profile_capture(request.query):
            user_repo = UserRepository(db)
            profile_patch = _extract_profile_update_from_query(request.query)
            current_user_row = await user_repo.get_by_id(user_id)
            current_prefs = getattr(current_user_row, "ai_preferences", {}) or {}
            merged_profile = normalize_trader_profile_preferences({**current_prefs, **profile_patch})
            await user_repo.update_ai_preferences(user_id, {
                "trader_types": merged_profile.get("trader_types", []),
                "primary_timeframes": merged_profile.get("primary_timeframes", []),
                "asset_focus": merged_profile.get("asset_focus", []),
                "behavior_flags": merged_profile.get("behavior_flags", []),
            })
            finn_response = _build_profile_saved_envelope(merged_profile)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload
            )
        if _looks_like_profile_explain(request.query):
            user_row = await UserRepository(db).get_by_id(user_id)
            prefs = getattr(user_row, "ai_preferences", {}) or {}
            finn_response = _build_profile_explain_envelope(normalize_trader_profile_preferences(prefs))
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload
            )
        if _looks_like_setup_strategy_listing_request(request.query):
            finn_response = await _build_setup_strategy_listing_envelope(db, user_id)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload
            )
        if _looks_like_watchlist_mutation(request.query):
            finn_response = _build_watchlist_mutation_envelope(request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, db=db, prompt=request.query, context_payload=context_payload
            )
        active_legacy_state = await service.state_repo.get_state(user_id)
        active_legacy_flow = str((active_legacy_state or {}).get("current_flow") or "").lower()
        should_resume_legacy_transaction = (
            _is_legacy_transactional_flow_name(active_legacy_flow)
            and not _is_modern_transactional_state_record(active_legacy_state)
        )
        if should_resume_legacy_transaction:
            context_payload["current_flow"] = active_legacy_flow
        if _should_prefer_legacy_setup_flow(request.query, context_payload) or should_resume_legacy_transaction:
            if _should_prefer_legacy_setup_flow(request.query, context_payload):
                _clear_modern_transactional_context(context_payload)
            response, action, draft, state, reasoning, suggested_actions, actual_session_id = await service.get_chat_response(
                user_id, request.query, request.history, context_payload, trace_id=trace_id, session_id=request.session_id
            )
            return await _finalize_legacy_response(
                service=service,
                response=response,
                action=action,
                draft=draft,
                state=state,
                reasoning=reasoning,
                suggested_actions=suggested_actions,
                session_id=actual_session_id or request.session_id,
                finn=finn,
                user_id=user_id,
                trace_id=trace_id,
                db=db,
                query=request.query,
                context_payload=context_payload,
                started_at=started_at,
            )
        follow_up = await _continue_transactional_follow_up(finn, user_id, request.query, context_payload)
        if follow_up:
            return await _finalize_finn_response(
                finn, user_id, follow_up, trace_id, persist_state=True, prompt=request.query, context_payload=context_payload
            )
        if finn.looks_like_daily_score_refresh_request(request.query):
            finn_response = await finn.build_daily_score_refresh_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload
            )
        if finn.looks_like_product_refresh_help_request(request.query):
            finn_response = await finn.build_product_refresh_help_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000
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
        if finn.looks_like_plan_adherence_review_request(request.query):
            finn_response = await finn.build_plan_adherence_review_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000
            )
        if finn.looks_like_outcome_tracking_request(request.query):
            finn_response = await finn.build_outcome_tracking_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000
            )
        if finn.looks_like_governed_action_review_request(request.query, context_payload):
            finn_response = await finn.build_governed_action_review_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000
            )
        if finn.looks_like_outcome_memory_request(request.query):
            finn_response = await finn.build_outcome_memory_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000
            )
        if finn.looks_like_personal_coach_request(request.query):
            finn_response = await finn.build_personal_coach_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000
            )
        if finn.looks_like_personal_performance_request(request.query):
            finn_response = await finn.build_personal_performance_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000
            )
        if finn.looks_like_trade_journal_intelligence_request(request.query):
            finn_response = await finn.build_trade_journal_intelligence_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000
            )
        if finn.looks_like_portfolio_intelligence_request(request.query, context_payload):
            finn_response = await finn.build_portfolio_intelligence_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000
            )
        if finn.looks_like_priority_engine_request(request.query, context_payload):
            finn_response = await finn.build_priority_engine_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000
            )
        if finn.looks_like_portfolio_operating_system_request(request.query):
            finn_response = await finn.build_portfolio_operating_system_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000
            )
        if finn.looks_like_decision_review_request(request.query, context_payload):
            finn_response = await finn.build_decision_review_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000
            )
        if finn.should_route_ultra_implicit_prompt_to_decision_review(request.query, context_payload):
            finn_response = await finn.build_decision_review_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000
            )
        if finn.looks_like_ultra_implicit_review_prompt(request.query):
            finn_response = await finn.build_quick_general_help_response(user_id, request.query, context_payload)
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
        if _should_use_modern_setup_creation_flow(request.query, context_payload):
            finn_response = finn.build_setup_response(request.query, context_payload)
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
        if finn.looks_like_daily_coach_request(request.query):
            finn_response = await finn.build_daily_coach_response(user_id, request.query, context_payload)
            return await _finalize_finn_response(
                finn, user_id, finn_response, trace_id, prompt=request.query, context_payload=context_payload
            )

        try:
            response, action, draft, state, reasoning, suggested_actions, actual_session_id = await service.get_chat_response(
                user_id, request.query, request.history, context_payload, trace_id=trace_id, session_id=request.session_id
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
        legacy_response = _attach_trader_profile_metadata(legacy_response, context_payload)
        legacy_response = _normalize_finn_response_contract(legacy_response)
        _log_finn_prompt_audit(
            trace_id=trace_id,
            user_id=user_id,
            prompt=request.query,
            route_source="legacy_assistant",
            detected_intent=intent,
            intent_confidence=None,
            selected_flow=(state or {}).get("current_flow"),
            selected_entity=_audit_selected_entity(legacy_response, context_payload),
            context_payload=context_payload,
            used_draft=bool(draft),
            draft_summary=_audit_draft_summary(draft),
            response_type=_audit_response_type(legacy_response),
            success=_audit_success_label(legacy_response),
            mode=(legacy_response.get("analysis") or {}).get("mode") or finn._response_mode_for_flow((state or {}).get("current_flow"), draft),
            context_confidence=(legacy_response.get("analysis") or {}).get("context_confidence"),
            draft_rejected_reason=(context_payload.get("_finn_sanitization") or {}).get("draft_rejected_reason"),
            latency_ms=(time.perf_counter() - started_at) * 1000,
        )
        _record_finn_product_event(
            user_id=user_id,
            event_name="finn_response_received",
            session_id=actual_session_id or request.session_id,
            surface="legacy_assistant",
            page=context_payload.get("page"),
            asset=context_payload.get("symbol") or context_payload.get("asset"),
            flow_type=(state or {}).get("current_flow"),
            bot_id=(state or {}).get("bot_id") or context_payload.get("bot_id"),
            setup_id=(state or {}).get("setup_id") or context_payload.get("setup_id"),
            strategy_id=(state or {}).get("strategy_id") or context_payload.get("strategy_id"),
            trace_id=trace_id,
            next_best_action=legacy_response.get("next_best_action"),
            metadata={
                "intent": intent,
                **_trader_profile_event_metadata(context_payload),
            },
        )
        _record_behavioral_response_events(
            user_id=user_id,
            response=legacy_response,
            context_payload=context_payload,
            route_source="legacy_assistant",
            trace_id=trace_id,
        )
        return AssistantChatResponse(
            response=legacy_response.get("response") or response,
            intent=intent,
            action=action,
            draft=draft,
            state=legacy_response.get("state"),
            reasoning=reasoning,
            suggested_actions=suggested_actions,
            trace_id=trace_id,
            session_id=actual_session_id,
            summary=legacy_response.get("summary"),
            risk_summary=legacy_response.get("risk_summary"),
            next_best_action=legacy_response.get("next_best_action"),
            review_reason=legacy_response.get("review_reason"),
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
        data_str = json.dumps(data_val, ensure_ascii=False, default=str)
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
    service: Any = Depends(get_assistant_service),
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
            finn = _new_finn_plan_service(db)
            context_payload = await finn.hydrate_context(user_id, _assistant_context_payload(request.context))
            context_payload = finn.sanitize_context_for_query(request.query, context_payload)
            context_payload = await _enrich_with_trader_profile(db, user_id, context_payload, query=request.query)
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
            if _looks_like_profile_capture(request.query):
                user_repo = UserRepository(db)
                profile_patch = _extract_profile_update_from_query(request.query)
                current_user_row = await user_repo.get_by_id(user_id)
                current_prefs = getattr(current_user_row, "ai_preferences", {}) or {}
                merged_profile = normalize_trader_profile_preferences({**current_prefs, **profile_patch})
                await user_repo.update_ai_preferences(user_id, {
                    "trader_types": merged_profile.get("trader_types", []),
                    "primary_timeframes": merged_profile.get("primary_timeframes", []),
                    "asset_focus": merged_profile.get("asset_focus", []),
                    "behavior_flags": merged_profile.get("behavior_flags", []),
                })
                envelope = _build_profile_saved_envelope(merged_profile)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload)
                yield _sse_event("envelope", envelope)
                return

            if _looks_like_profile_explain(request.query):
                user_row = await UserRepository(db).get_by_id(user_id)
                prefs = getattr(user_row, "ai_preferences", {}) or {}
                envelope = _build_profile_explain_envelope(normalize_trader_profile_preferences(prefs))
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload)
                yield _sse_event("envelope", envelope)
                return

            if _looks_like_setup_strategy_listing_request(request.query):
                envelope = await _build_setup_strategy_listing_envelope(db, user_id)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload)
                yield _sse_event("envelope", envelope)
                return

            if _looks_like_watchlist_mutation(request.query):
                envelope = _build_watchlist_mutation_envelope(request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, db=db, prompt=request.query, context_payload=context_payload)
                yield _sse_event("envelope", envelope)
                return

            active_legacy_state = await service.state_repo.get_state(user_id)
            active_legacy_flow = str((active_legacy_state or {}).get("current_flow") or "").lower()
            should_resume_legacy_transaction = (
                _is_legacy_transactional_flow_name(active_legacy_flow)
                and not _is_modern_transactional_state_record(active_legacy_state)
            )
            if should_resume_legacy_transaction:
                context_payload["current_flow"] = active_legacy_flow
            if _should_prefer_legacy_setup_flow(request.query, context_payload) or should_resume_legacy_transaction:
                if _should_prefer_legacy_setup_flow(request.query, context_payload):
                    _clear_modern_transactional_context(context_payload)
                async for chunk in service.get_chat_response_stream(
                    user_id,
                    request.query,
                    request.history,
                    context_payload,
                    trace_id=trace_id,
                    background_tasks=background_tasks,
                ):
                    if await raw_request.is_disconnected():
                        logger.warning(f"🔌 Client disconnected mid-stream | Trace: {trace_id}. Aborting stream generator.")
                        return
                    yield chunk
                return

            follow_up = await _continue_transactional_follow_up(finn, user_id, request.query, context_payload)
            if follow_up:
                envelope = await _prepare_finn_envelope(
                    finn, user_id, follow_up, trace_id, persist_state=True, prompt=request.query, context_payload=context_payload
                )
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_daily_score_refresh_request(request.query):
                envelope = await finn.build_daily_score_refresh_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_product_refresh_help_request(request.query):
                envelope = await finn.build_product_refresh_help_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000)
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

            if finn.looks_like_plan_adherence_review_request(request.query):
                envelope = await finn.build_plan_adherence_review_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_outcome_tracking_request(request.query):
                envelope = await finn.build_outcome_tracking_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_governed_action_review_request(request.query, context_payload):
                envelope = await finn.build_governed_action_review_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_outcome_memory_request(request.query):
                envelope = await finn.build_outcome_memory_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_personal_coach_request(request.query):
                envelope = await finn.build_personal_coach_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_personal_performance_request(request.query):
                envelope = await finn.build_personal_performance_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_trade_journal_intelligence_request(request.query):
                envelope = await finn.build_trade_journal_intelligence_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_portfolio_intelligence_request(request.query, context_payload):
                envelope = await finn.build_portfolio_intelligence_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_priority_engine_request(request.query, context_payload):
                envelope = await finn.build_priority_engine_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_portfolio_operating_system_request(request.query):
                envelope = await finn.build_portfolio_operating_system_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_decision_review_request(request.query, context_payload):
                envelope = await finn.build_decision_review_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000)
                yield _sse_event("envelope", envelope)
                return

            if finn.should_route_ultra_implicit_prompt_to_decision_review(request.query, context_payload):
                envelope = await finn.build_decision_review_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload, latency_ms=(time.perf_counter() - started_at) * 1000)
                yield _sse_event("envelope", envelope)
                return

            if finn.looks_like_ultra_implicit_review_prompt(request.query):
                envelope = await finn.build_quick_general_help_response(user_id, request.query, context_payload)
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

            if finn.looks_like_daily_coach_request(request.query):
                envelope = await finn.build_daily_coach_response(user_id, request.query, context_payload)
                envelope = await _prepare_finn_envelope(finn, user_id, envelope, trace_id, prompt=request.query, context_payload=context_payload)
                yield _sse_event("envelope", envelope)
                return

            try:
                async for chunk in service.get_chat_response_stream(
                    user_id, request.query, request.history, context_payload,
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

@router.post("/assistant/insight", response_model=AssistantInsightResponse)
async def get_insight(
    context: dict,
    current_user: dict = Depends(get_current_user),
    service: Any = Depends(get_assistant_service)
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
            finn = _new_finn_plan_service(db, trace_id=trace_id)
            result = await finn.execute_issued_action(user_id, str(action_id))
            _invalidate_mission_control_cache(user_id)
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
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    trace_id = getattr(request.state, "trace_id", None) if request else None
    cached = _get_cached_mission_control(current_user["id"])
    if cached:
        return cached
    finn = _new_finn_plan_service(db, trace_id=trace_id)
    response = await finn.build_mission_control_response(
        current_user["id"],
        {"page": "assistant", "scope": "mission_control"},
    )
    await _issue_finn_response_actions_safely(
        finn,
        db,
        current_user["id"],
        response,
        trace_id=trace_id,
        route_source="assistant_mission_control",
    )
    response = await _enrich_with_trader_profile(db, current_user["id"], response)
    _store_cached_mission_control(current_user["id"], response)
    return response
