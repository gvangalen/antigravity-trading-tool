import hashlib
import json
import re
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.conversation_state_repository import ConversationStateRepository
from backend.infrastructure.repositories.exchange_repository import ExchangeRepository
from backend.infrastructure.repositories.indicator_config_repository import IndicatorConfigRepository
from backend.infrastructure.repositories.macro_data_repository import MacroDataRepository
from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.infrastructure.repositories.technical_data_repository import TechnicalDataRepository
from backend.schemas.bot_schema import BotConfigCreateSchema, BotConfigUpdateSchema
from backend.schemas.trading_schema import SetupCreateSchema, StrategyCreateSchema
from backend.services.bot_service import BotService
from backend.services.indicator_config_service import IndicatorConfigService
from backend.services.macro_data_service import MacroDataService
from backend.services.score_service import ScoreService
from backend.services.setup_service import SetupService
from backend.services.strategy_service import StrategyService
from backend.services.technical_data_service import TechnicalDataService
from backend.utils.scoring_utils import normalize_indicator_name


SUPPORTED_ASSETS = {"BTC", "ETH", "SOL"}
KNOWN_ASSET_CANDIDATES = ("BTC", "ETH", "SOL", "DOGE", "XRP", "ADA", "BNB", "AVAX", "LINK", "MATIC", "PEPE")
NUMBER_WITH_DELIMITER = r"([0-9][0-9.,]*)(?=\s|,|/|$)"
FINN_STATE_VERSION = 2
WEEKDAYS = {
    "maandag": "monday",
    "dinsdag": "tuesday",
    "woensdag": "wednesday",
    "donderdag": "thursday",
    "vrijdag": "friday",
    "zaterdag": "saturday",
    "zondag": "sunday",
    "monday": "monday",
    "tuesday": "tuesday",
    "wednesday": "wednesday",
    "thursday": "thursday",
    "friday": "friday",
    "saturday": "saturday",
    "sunday": "sunday",
}
WEEKDAY_NUMBERS = {
    "monday": 1,
    "tuesday": 2,
    "wednesday": 3,
    "thursday": 4,
    "friday": 5,
    "saturday": 6,
    "sunday": 7,
}
NO_BOT_PHRASES = ("geen bot", "zonder bot", "niet automatisch", "manual only", "manual-only", "alleen handmatig")
INDICATOR_FIXED_BUCKETS = [
    (0.0, 20.0),
    (20.0, 40.0),
    (40.0, 60.0),
    (60.0, 80.0),
    (80.0, 100.0),
]


def empty_plan_draft() -> Dict[str, Any]:
    return {
        "plan_type": None,
        "asset": None,
        "setup": {
            "name": None,
            "timeframe": None,
            "macro_score_range": None,
            "technical_score_range": None,
            "market_score_range": None,
        },
        "strategy": {
            "base_amount_eur": None,
            "execution_mode": "fixed",
            "decision_curve": None,
            "direction": "long",
            "entry_type": None,
            "market_execution_ack": False,
            "entry": None,
            "stop_loss": None,
            "targets": None,
        },
        "dca": {
            "frequency": None,
            "day": None,
            "month_day": None,
            "dca_mode": "standard",
            "buy_score_threshold": None,
        },
        "bot": {
            "create_bot": None,
            "automation": None,
            "mode": "manual",
            "is_live": False,
            "risk_profile": None,
            "total_budget_eur": 0,
            "daily_limit_eur": 0,
            "min_order_eur": 0,
            "max_order_eur": 0,
            "max_asset_exposure_pct": 100,
        },
    }


def empty_plan_patch() -> Dict[str, Any]:
    return {
        "plan_type": None,
        "asset": None,
        "setup": {
            "name": None,
            "timeframe": None,
            "macro_score_range": None,
            "technical_score_range": None,
            "market_score_range": None,
        },
        "strategy": {
            "base_amount_eur": None,
            "execution_mode": None,
            "decision_curve": None,
            "direction": None,
            "entry_type": None,
            "entry": None,
            "stop_loss": None,
            "targets": None,
        },
        "dca": {
            "frequency": None,
            "day": None,
            "month_day": None,
        },
        "bot": {
            "create_bot": None,
            "automation": None,
            "mode": None,
            "is_live": None,
            "risk_profile": None,
            "total_budget_eur": None,
            "daily_limit_eur": None,
            "min_order_eur": None,
            "max_order_eur": None,
            "max_asset_exposure_pct": None,
        },
    }


def empty_strategy_draft() -> Dict[str, Any]:
    return {
        "draft_kind": "strategy",
        "operation": "create",
        "setup_id": None,
        "strategy_id": None,
        "setup_type": None,
        "asset": None,
        "timeframe": None,
        "strategy": {
            "base_amount_eur": None,
            "execution_mode": "fixed",
            "decision_curve": None,
            "direction": "long",
            "entry_type": None,
            "entry": None,
            "stop_loss": None,
            "targets": None,
            "automation": "manual_only",
            "risk_profile": "balanced",
        },
    }


def empty_bot_draft() -> Dict[str, Any]:
    return {
        "draft_kind": "bot",
        "operation": "create",
        "bot_id": None,
        "strategy_id": None,
        "existing_bot_id": None,
        "existing_bot_snapshot": None,
        "changes": [],
        "asset": None,
        "setup_type": None,
        "timeframe": None,
        "bot": {
            "name": None,
            "mode": "manual",
            "is_live": False,
            "live_trading_ack": False,
            "risk_profile": "balanced",
            "cadence": "daily",
            "base_currency": "EUR",
            "budget_total_eur": 0,
            "budget_daily_limit_eur": 0,
            "budget_min_order_eur": 0,
            "budget_max_order_eur": 0,
            "max_asset_exposure_pct": 100,
        },
    }


def empty_indicator_config_draft() -> Dict[str, Any]:
    return {
        "draft_kind": "indicator_config",
        "operation": "configure",
        "category": "macro",
        "indicator": None,
        "display_name": None,
        "symbol": None,
        "score_mode": None,
        "weight": 1.0,
        "activate_node": True,
        "rules": [],
        "existing_config_snapshot": None,
        "node_already_active": False,
        "has_user_override": False,
        "custom_rules_touched": False,
        "custom_rules_complete": False,
        "custom_rule_buckets": [],
        "indicator_options": [],
        "changes": [],
    }


def _deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        elif value is not None:
            merged[key] = value
    return merged


def _number(value: str) -> Optional[float]:
    if value is None:
        return None
    cleaned = str(value).strip().replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_score_range(text: str, label: str) -> Optional[List[int]]:
    pattern = rf"{label}\s*(?:score)?\s*(?:van|tussen|=|:)?\s*(\d{{1,3}})\s*(?:-|tot|en|–)\s*(\d{{1,3}})"
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    lo = max(0, min(100, int(match.group(1))))
    hi = max(0, min(100, int(match.group(2))))
    return [lo, hi]


def _extract_targets(text: str) -> Optional[List[float]]:
    target_match = re.search(
        r"(?:targets?|tp)\s*(?:op|van|=|:)?\s*([0-9][0-9.,]*(?:\s*(?:,|/|\ben\b|\band\b|\s)\s*[0-9][0-9.,]*)*)",
        text,
        re.IGNORECASE,
    )
    if not target_match:
        return None
    targets = []
    normalized = re.sub(r"\b(?:en|and)\b", ",", target_match.group(1), flags=re.IGNORECASE)
    for raw in re.split(r"[,/\s]+", normalized.strip()):
        value = _number(raw)
        if value is not None:
            targets.append(value)
    return targets or None


def _asset_mentions(text: str) -> List[str]:
    seen = []
    upper = (text or "").upper()
    for symbol in KNOWN_ASSET_CANDIDATES:
        if re.search(rf"\b{re.escape(symbol)}\b", upper) and symbol not in seen:
            seen.append(symbol)
    return seen


class FinnPlanService:
    def __init__(self, db_session: AsyncSession):
        self.session = db_session

    def is_cancel_request(self, query: str) -> bool:
        q = (query or "").lower()
        cancel_patterns = [
            r"\bannuleer\b",
            r"\bvergeet\b",
            r"\bcancel\b",
            r"\bstop\s+(?:hiermee|dit|deze|plan|setup|trade|dca)\b",
        ]
        return any(re.search(pattern, q) for pattern in cancel_patterns)

    async def hydrate_context(self, user_id: int, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        hydrated = dict(context or {})
        if hydrated.get("finn_draft") or not self.session:
            return hydrated

        state = await ConversationStateRepository(self.session).get_state(user_id)
        slots = (state or {}).get("slots") or {}
        draft = slots.get("draft")
        if state and state.get("current_flow") in {"plan_creation", "strategy_creation", "bot_creation", "indicator_config"} and isinstance(draft, dict):
            hydrated["finn_draft"] = draft
            hydrated["finn_state"] = {
                "version": slots.get("version"),
                "updated_at": slots.get("updated_at"),
                "current_flow": state.get("current_flow"),
            }
        return hydrated

    async def persist_response_state(self, user_id: int, response: Dict[str, Any]) -> None:
        if not self.session:
            return
        repo = ConversationStateRepository(self.session)
        if response.get("intent") in {"plan_creation_cancelled", "strategy_creation_cancelled", "bot_creation_cancelled", "indicator_config_cancelled"}:
            await repo.clear_state(user_id)
            return
        if response.get("flow") not in {"plan_creation", "strategy_creation", "bot_creation", "indicator_config"} or not isinstance(response.get("draft"), dict):
            return

        draft = response["draft"]
        await repo.save_state(
            user_id,
            current_flow=response.get("flow"),
            asset=draft.get("asset"),
            slots={
                "version": FINN_STATE_VERSION,
                "draft": draft,
                "missing_fields": response.get("missing_fields", []),
                "invalid_fields": response.get("invalid_fields", []),
                "can_confirm": response.get("can_confirm", False),
                "updated_at": datetime.utcnow().isoformat(),
            },
        )

    async def clear_state(self, user_id: int) -> None:
        if self.session:
            await ConversationStateRepository(self.session).clear_state(user_id)

    async def build_cancel_response(self, user_id: int, context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        context = context or {}
        draft = context.get("finn_draft") if isinstance(context.get("finn_draft"), dict) else None
        flow = None

        if draft:
            if draft.get("draft_kind") == "strategy":
                flow = "strategy_creation"
            elif draft.get("draft_kind") == "bot":
                flow = "bot_creation"
            elif draft.get("draft_kind") == "indicator_config":
                flow = "indicator_config"
            elif draft.get("plan_type") or draft.get("asset") or isinstance(draft.get("_clarification"), dict):
                flow = "plan_creation"

        if not flow and self.session:
            state = await ConversationStateRepository(self.session).get_state(user_id)
            if state and state.get("current_flow") in {"plan_creation", "strategy_creation", "bot_creation", "indicator_config"}:
                flow = state.get("current_flow")

        if flow == "indicator_config":
            return {
                "response": "Prima, ik heb deze indicator-configuratie gestopt. Er is niets aangepast.",
                "intent": "indicator_config_cancelled",
                "flow": None,
                "draft": None,
                "missing_fields": [],
                "invalid_fields": [],
                "next_question": None,
                "can_confirm": False,
                "actions": [],
            }
        if flow == "bot_creation":
            return {
                "response": "Prima, ik heb deze bot-aanmaak gestopt. Er is niets aangemaakt.",
                "intent": "bot_creation_cancelled",
                "flow": None,
                "draft": None,
                "missing_fields": [],
                "invalid_fields": [],
                "next_question": None,
                "can_confirm": False,
                "actions": [],
            }
        if flow == "strategy_creation":
            return {
                "response": "Prima, ik heb deze strategie-aanmaak gestopt. Er is niets aangemaakt.",
                "intent": "strategy_creation_cancelled",
                "flow": None,
                "draft": None,
                "missing_fields": [],
                "invalid_fields": [],
                "next_question": None,
                "can_confirm": False,
                "actions": [],
            }
        if flow == "plan_creation":
            return {
                "response": "Prima, ik heb deze plan-aanmaak gestopt. Er is niets aangemaakt.",
                "intent": "plan_creation_cancelled",
                "flow": None,
                "draft": None,
                "missing_fields": [],
                "invalid_fields": [],
                "next_question": None,
                "can_confirm": False,
                "actions": [],
            }
        return None

    def looks_like_plan_request(self, query: str, draft: Optional[Dict[str, Any]] = None) -> bool:
        q = (query or "").lower()
        if draft and draft.get("plan_type"):
            return True
        if draft and draft.get("draft_kind") == "strategy":
            return False
        if self.looks_like_daily_coach_request(query):
            return False
        if self.looks_like_status_request(query):
            return False
        intent_words = [
            "maak", "aanmaken", "creeer", "creeër", "bouw", "instellen",
            "ik wil", "wil een", "wil elke", "wil iedere", "maak een",
            "misschien", "twijfel", "iets met",
        ]
        plan_words = [
            "setup", "strategie", "strategy", "dca", "trade", "traden",
            "entry", "stop loss", "stoploss", "target", "accumuleren",
            "wekelijks", "dagelijks", "maandelijks", "elke week",
            "iedere week", "elke dag", "iedere dag", "elke maand",
            "iedere maand", "kopen", "koop", "buy", "long", "short",
            "agressief", "aggressive", "breakout",
        ]
        if any(word in q for word in intent_words) and any(word in q for word in plan_words):
            return True

        asset_mentions = _asset_mentions(query)
        vague_asset_words = ["misschien", "twijfel", "iets met"]
        return bool(asset_mentions) and (
            any(word in q for word in plan_words)
            or any(word in q for word in vague_asset_words)
            or len(asset_mentions) > 1
        )

    def looks_like_strategy_request(self, query: str, context: Optional[Dict[str, Any]] = None) -> bool:
        q = (query or "").lower()
        context = context or {}
        draft = context.get("finn_draft") if isinstance(context.get("finn_draft"), dict) else {}
        if draft.get("draft_kind") == "strategy":
            return True
        if self.looks_like_status_request(query):
            return False
        has_strategy_word = any(word in q for word in ["strategie", "strategy"])
        has_setup_ref = bool(context.get("setup_id")) or bool(re.search(r"\bsetup\s*#?\s*\d+\b", q))
        has_create_intent = any(word in q for word in ["maak", "aanmaken", "creeer", "creeër", "bouw", "instellen", "wil"])
        return has_strategy_word and (has_setup_ref or has_create_intent)

    def looks_like_bot_request(self, query: str, context: Optional[Dict[str, Any]] = None) -> bool:
        q = (query or "").lower()
        context = context or {}
        draft = context.get("finn_draft") if isinstance(context.get("finn_draft"), dict) else {}
        if draft.get("draft_kind") == "bot":
            return True
        if self.looks_like_status_request(query):
            return False
        if any(phrase in q for phrase in NO_BOT_PHRASES):
            return False
        has_bot_word = bool(re.search(r"\bbot\b", q))
        has_bot_ref = bool(re.search(r"\bbot\s*#?\s*\d+\b", q))
        has_update_intent = any(word in q for word in ["pas", "wijzig", "update", "bijwerk", "bijwerken", "verander", "aanpassen"])
        has_strategy_ref = bool(context.get("strategy_id")) or bool(re.search(r"\bstrateg(?:ie|y)\s*#?\s*\d+\b", q))
        has_create_intent = any(word in q for word in ["maak", "aanmaken", "creeer", "creeër", "bouw", "instellen", "wil"])
        return has_bot_word and (has_bot_ref or has_strategy_ref or has_create_intent or has_update_intent)

    def looks_like_indicator_config_request(self, query: str, context: Optional[Dict[str, Any]] = None) -> bool:
        q = (query or "").lower()
        context = context or {}
        draft = context.get("finn_draft") if isinstance(context.get("finn_draft"), dict) else {}
        if draft.get("draft_kind") == "indicator_config":
            return True
        if self.looks_like_status_request(query):
            return False
        has_category = any(word in q for word in ["macro", "technical", "technisch", "technische", "indicator", "indicatoren", "node", "score", "scoring", "contrarian", "standard", "standaard"])
        has_config_intent = any(word in q for word in ["voeg", "toevoegen", "zet", "maak", "configureer", "config", "gebruik", "weight", "weging", "gewicht", "reset", "herstel"])
        known_indicator_hint = any(word in q for word in ["btc dominance", "bitcoin dominance", "fear", "greed", "dxy", "vix", "dominance"])
        return has_config_intent and (has_category or known_indicator_hint)

    def looks_like_indicator_insight_request(self, query: str) -> bool:
        q = (query or "").lower()
        has_data_or_indicator = any(word in q for word in [
            "indicator", "indicatoren", "macro", "technical", "technisch",
            "market data", "marktdata", "market score", "macro score", "technical score",
            "welke data",
        ])
        has_explain_or_coach = any(word in q for word in [
            "waarom", "uitleg", "leg uit", "verklaar", "blokkeert", "blokkeerd",
            "trekt", "omhoog", "omlaag", "bijdrage", "contributor", "contributors",
            "genoeg", "mis", "mist", "ontbreekt", "kijk", "gebruikt",
            "amper", "weinig", "raad", "advies", "aanraden", "welke", "welke data",
        ])
        if self.looks_like_indicator_config_request(query) and not has_explain_or_coach:
            return False
        return has_data_or_indicator and has_explain_or_coach

    def looks_like_daily_coach_request(self, query: str) -> bool:
        q = (query or "").lower()
        has_today = any(word in q for word in [
            "vandaag", "today", "nu", "daily", "dagelijkse", "dagcheck", "cockpit",
            "brief", "briefing", "dagstart", "morning", "mijn dag",
        ])
        has_decision_intent = any(phrase in q for phrase in [
            "wat moet ik", "wat moet finn", "wat doe ik", "wat nu", "moet ik kopen",
            "mag ik kopen", "moet mijn bot", "waar moet ik op letten", "dagelijkse check",
            "trading coach", "coach me", "plan check", "geef mijn daily brief",
            "daily brief", "dagelijkse briefing", "start mijn dag", "prioriteiten vandaag",
            "mijn prioriteiten", "prioriteiten",
        ])
        has_trading_context = any(word in q for word in [
            "setup", "plan", "bot", "trade", "dca", "btc", "eth", "sol", "market", "markt",
        ])
        return has_today and (has_decision_intent or has_trading_context or "kopen" in q)

    def looks_like_status_request(self, query: str) -> bool:
        q = (query or "").lower()
        has_status = any(word in q for word in [
            "actief", "active", "inactive", "inactief", "waarom koopt",
            "waarom niet", "moet ik kopen", "mag ik kopen", "plan actief",
            "blokkeert", "blokkeerd", "blocked", "score blokkeert",
        ])
        has_market_or_plan = any(word in q for word in [
            "setup", "plan", "bot", "trade", "dca", "markt", "market", "btc", "eth", "sol",
        ])
        return has_status and has_market_or_plan

    def build_response(self, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        context = context or {}
        previous = context.get("finn_draft") if isinstance(context.get("finn_draft"), dict) else {}
        draft = _deep_merge(empty_plan_draft(), previous)

        q = (query or "").strip()
        q_lower = q.lower()

        unsure_patterns = [r"\bgeen\s+idee\b", r"\bweet\s+ik\s+niet\b", r"\bwat\s+denk\s+jij\b"]
        is_unsure = any(re.search(pattern, q_lower) for pattern in unsure_patterns)

        if self.is_cancel_request(q_lower):
            return {
                "response": "Prima, ik heb deze plan-aanmaak gestopt. Er is niets aangemaakt.",
                "intent": "plan_creation_cancelled",
                "flow": None,
                "draft": empty_plan_draft(),
                "missing_fields": [],
                "invalid_fields": [],
                "next_question": None,
                "can_confirm": False,
                "actions": [],
            }

        extracted = self._extract_from_query(q)
        draft = _deep_merge(draft, extracted)
        self._apply_defaults(draft)

        validation = self._validate(draft)
        message = self._build_message(draft, validation)
        
        if is_unsure:
            next_q = validation["next_question"]
            if next_q == "bot.risk_profile":
                message = "Zal ik hem op 'balanced' zetten?"
                draft["bot"]["risk_profile"] = "balanced"
                validation = self._validate(draft)
            elif next_q == "strategy.base_amount_eur":
                message = "Zal ik als basisbedrag €100 gebruiken?"
                draft["strategy"]["base_amount_eur"] = 100.0
                validation = self._validate(draft)
            elif next_q == "setup.name":
                asset = draft.get("asset") or "Asset"
                message = f"Ik stel voor om het '{asset} Blueprint' te noemen. Akkoord?"
                draft["setup"]["name"] = f"{asset} Blueprint"
                validation = self._validate(draft)
        actions = []
        if validation["can_confirm"]:
            action_payload = deepcopy(draft)
            action_id = self._action_id(action_payload)
            actions.append({
                "id": action_id,
                "type": "create_plan",
                "label": "Plan aanmaken",
                "payload": action_payload,
                "risk_level": self._action_risk(draft),
                "requires_confirmation": True,
                "autonomy_level": "confirm_required",
                "guardrails": self._guardrails(draft),
            })

        return {
            "response": message,
            "intent": "plan_creation",
            "flow": "plan_creation",
            "draft": draft,
            "state": self._flow_state(draft, validation),
            "reasoning": self._reasoning(draft, validation),
            "missing_fields": validation["missing_fields"],
            "invalid_fields": validation["invalid_fields"],
            "next_question": validation["next_question"],
            "can_confirm": validation["can_confirm"],
            "actions": actions,
        }

    def build_strategy_response(self, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        context = context or {}
        previous = context.get("finn_draft") if isinstance(context.get("finn_draft"), dict) and context["finn_draft"].get("draft_kind") == "strategy" else {}
        draft = _deep_merge(empty_strategy_draft(), previous)
        self._apply_strategy_context(draft, context)

        q = (query or "").strip()
        q_lower = q.lower()
        explicit_create_intent = self._has_explicit_strategy_create_intent(q_lower)
        explicit_update_intent = self._has_explicit_strategy_update_intent(q_lower)
        if self.is_cancel_request(q):
            return {
                "response": "Prima, ik heb deze strategie-aanmaak gestopt. Er is niets aangemaakt.",
                "intent": "strategy_creation_cancelled",
                "flow": None,
                "draft": empty_strategy_draft(),
                "missing_fields": [],
                "invalid_fields": [],
                "next_question": None,
                "can_confirm": False,
                "actions": [],
            }

        if explicit_create_intent and not explicit_update_intent:
            draft["operation"] = "create"
            draft["strategy_id"] = None
            draft.pop("changes", None)

        setup_id_match = re.search(r"\bsetup\s*#?\s*(\d+)\b", q, re.IGNORECASE)
        if setup_id_match:
            draft["setup_id"] = int(setup_id_match.group(1))
        strategy_id_match = re.search(r"\bstrateg(?:ie|y)\s*#?\s*(\d+)\b", q, re.IGNORECASE)
        if strategy_id_match:
            draft["strategy_id"] = int(strategy_id_match.group(1))
            draft["operation"] = "update"
        if explicit_update_intent:
            draft["operation"] = "update"
            if not draft.get("strategy_id") and draft.get("existing_strategy_id"):
                draft["strategy_id"] = draft.get("existing_strategy_id")

        extracted = self._extract_from_query(q)
        if extracted.get("plan_type"):
            draft["setup_type"] = extracted["plan_type"]
        if extracted.get("asset"):
            draft["asset"] = extracted["asset"]
        setup_patch = extracted.get("setup") or {}
        if setup_patch.get("timeframe"):
            draft["timeframe"] = setup_patch["timeframe"]
        strategy_patch = extracted.get("strategy") or {}
        for field in ["base_amount_eur", "execution_mode", "decision_curve", "direction", "entry_type", "entry", "stop_loss", "targets"]:
            if strategy_patch.get(field) is not None:
                draft["strategy"][field] = strategy_patch[field]
        if re.search(r"\b(?:bevestig|akkoord|ok|ja)\b.*\bmarket\b|\bmarket\b.*\b(?:bevestig|akkoord|ok|ja)\b", q_lower):
            draft["strategy"]["market_execution_ack"] = True
        bot_patch = extracted.get("bot") or {}
        if bot_patch.get("automation"):
            draft["strategy"]["automation"] = bot_patch["automation"]
        if bot_patch.get("risk_profile"):
            draft["strategy"]["risk_profile"] = bot_patch["risk_profile"]
        if bot_patch.get("create_bot") is True and not draft["strategy"].get("automation"):
            draft["strategy"]["automation"] = "bot_assisted"

        self._apply_strategy_defaults(draft)
        validation = self._validate_strategy_draft(draft)
        message = self._build_strategy_message(draft, validation)

        actions = []
        if validation["can_confirm"]:
            action_payload = deepcopy(draft)
            actions.append({
                "id": self._strategy_action_id(action_payload),
                "type": "create_strategy",
                "label": "Strategie bijwerken" if draft.get("operation") == "update" else "Strategie aanmaken",
                "payload": action_payload,
                "risk_level": "medium" if draft.get("setup_type") == "trade" else "low",
                "requires_confirmation": True,
                "autonomy_level": "confirm_required",
                "guardrails": {
                    "requires_confirmation": True,
                    "can_execute_without_user": False,
                    "execution_allowed": "strategy_creation_only",
                },
            })

        return {
            "response": message,
            "intent": "strategy_creation",
            "flow": "strategy_creation",
            "draft": draft,
            "state": self._strategy_flow_state(draft, validation),
            "reasoning": self._strategy_reasoning(draft, validation),
            "missing_fields": validation["missing_fields"],
            "invalid_fields": validation["invalid_fields"],
            "next_question": validation["next_question"],
            "can_confirm": validation["can_confirm"],
            "actions": actions,
        }

    async def build_strategy_response_for_user(self, user_id: int, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        response = self.build_strategy_response(query, context)
        if response.get("intent") == "strategy_creation_cancelled" or not self.session:
            return response

        draft = response.get("draft") if isinstance(response.get("draft"), dict) else {}
        await self._hydrate_strategy_draft_from_db(user_id, draft)

        strategy_service = StrategyService(self.session)
        validation = self._validate_strategy_draft(draft)
        existing_strategy = None
        if draft.get("setup_id"):
            existing_strategy = await strategy_service.get_strategy_by_setup(int(draft["setup_id"]), user_id)

        if existing_strategy and draft.get("operation") != "update":
            draft["strategy_id"] = None
            draft["existing_strategy_id"] = existing_strategy.get("id")
            duplicate_validation = {
                "missing_fields": [],
                "invalid_fields": [{"field": "setup_id", "reason": "voor deze setup bestaat al een strategie"}],
                "next_question": "strategy.update_existing",
                "can_confirm": False,
            }
            response.update({
                "response": (
                    f"Deze setup heeft al strategie #{existing_strategy.get('id')}. "
                    "Ik maak daarom geen tweede strategie aan. Zeg bijvoorbeeld 'pas de strategie aan met 150 euro' "
                    "als je deze bestaande strategie wilt bijwerken."
                ),
                "draft": draft,
                "state": self._strategy_flow_state(draft, duplicate_validation),
                "reasoning": self._strategy_reasoning(draft, duplicate_validation),
                "missing_fields": duplicate_validation["missing_fields"],
                "invalid_fields": duplicate_validation["invalid_fields"],
                "next_question": duplicate_validation["next_question"],
                "can_confirm": duplicate_validation["can_confirm"],
                "actions": [],
            })
            return response

        if existing_strategy and draft.get("operation") == "update":
            existing_for_diff = await self._load_strategy_snapshot_for_diff(user_id, draft, strategy_service)
            self._merge_existing_strategy_into_draft(draft, existing_for_diff or existing_strategy)
            draft["changes"] = self._strategy_changes(existing_for_diff or existing_strategy, draft)
            validation = self._validate_strategy_draft(draft)

        setup_options = []
        if "setup_id" in validation["missing_fields"]:
            setup_options = await self._strategy_setup_options(user_id, draft)

        actions = []
        if validation["can_confirm"]:
            action_payload = deepcopy(draft)
            actions.append({
                "id": self._strategy_action_id(action_payload),
                "type": "create_strategy",
                "label": "Strategie bijwerken" if draft.get("operation") == "update" else "Strategie aanmaken",
                "payload": action_payload,
                "risk_level": "medium" if draft.get("setup_type") == "trade" else "low",
                "requires_confirmation": True,
                "autonomy_level": "confirm_required",
                "guardrails": {
                    "requires_confirmation": True,
                    "can_execute_without_user": False,
                    "execution_allowed": "strategy_update" if draft.get("operation") == "update" else "strategy_creation_only",
                },
            })

        response.update({
            "response": self._build_strategy_message(draft, validation, setup_options=setup_options),
            "draft": draft,
            "state": self._strategy_flow_state(draft, validation, setup_options=setup_options),
            "reasoning": self._strategy_reasoning(draft, validation),
            "missing_fields": validation["missing_fields"],
            "invalid_fields": validation["invalid_fields"],
            "next_question": validation["next_question"],
            "can_confirm": validation["can_confirm"],
            "actions": actions,
        })
        return response

    def build_bot_response(self, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        context = context or {}
        previous = context.get("finn_draft") if isinstance(context.get("finn_draft"), dict) and context["finn_draft"].get("draft_kind") == "bot" else {}
        draft = _deep_merge(empty_bot_draft(), previous)

        if context.get("strategy_id") and not draft.get("strategy_id"):
            draft["strategy_id"] = context.get("strategy_id")

        q = (query or "").strip()
        q_lower = q.lower()
        explicit_indicator_input = bool(self._extract_indicator_name_hint(q, draft.get("category") or "macro"))
        if self.is_cancel_request(q):
            return {
                "response": "Prima, ik heb deze bot-flow gestopt. Er is niets aangemaakt of bijgewerkt.",
                "intent": "bot_creation_cancelled",
                "flow": None,
                "draft": empty_bot_draft(),
                "missing_fields": [],
                "invalid_fields": [],
                "next_question": None,
                "can_confirm": False,
                "actions": [],
            }

        if previous and self._is_new_bot_start_without_target(q):
            draft = empty_bot_draft()
            if context.get("strategy_id"):
                draft["strategy_id"] = context.get("strategy_id")

        if draft.get("existing_bot_id") and any(word in q_lower for word in ["ja", "ok", "prima", "bijwerken", "update", "aanpassen"]):
            draft["operation"] = "update"
            draft["bot_id"] = draft.get("existing_bot_id")

        bot_id_match = re.search(r"\bbot\s*#?\s*(\d+)\b", q, re.IGNORECASE)
        if bot_id_match:
            new_bot_id = int(bot_id_match.group(1))
            if draft.get("bot_id") and int(draft["bot_id"]) != new_bot_id:
                draft = empty_bot_draft()
            draft["operation"] = "update"
            draft["bot_id"] = new_bot_id

        if any(word in q_lower for word in ["pas", "wijzig", "update", "bijwerk", "bijwerken", "verander", "aanpassen"]):
            draft["operation"] = "update" if draft.get("bot_id") or draft.get("existing_bot_id") else draft.get("operation", "create")

        strategy_id_match = re.search(r"\bstrateg(?:ie|y)\s*#?\s*(\d+)\b", q, re.IGNORECASE)
        if strategy_id_match:
            new_strategy_id = int(strategy_id_match.group(1))
            if draft.get("strategy_id") and int(draft["strategy_id"]) != new_strategy_id:
                self._reset_bot_strategy_binding(draft)
            draft["strategy_id"] = new_strategy_id

        bot = draft["bot"]
        touched_bot_fields = set(draft.get("_touched_bot_fields") or [])
        name_match = re.search(r"(?:noem|naam|heet)\s+(?:hem|deze)?\s*[\"']?([^\"'.]+)[\"']?", q, re.IGNORECASE)
        if name_match:
            name = name_match.group(1).strip()
            if 2 <= len(name) <= 80:
                bot["name"] = name
                touched_bot_fields.add("name")

        bot_patch = self._extract_from_query(q).get("bot") or {}
        for field, value in bot_patch.items():
            if value is not None:
                mapping = {
                    "total_budget_eur": "budget_total_eur",
                    "daily_limit_eur": "budget_daily_limit_eur",
                    "min_order_eur": "budget_min_order_eur",
                    "max_order_eur": "budget_max_order_eur",
                }
                mapped_field = mapping.get(field, field)
                bot[mapped_field] = value
                touched_bot_fields.add(mapped_field)

        if "hourly" in q_lower or "elk uur" in q_lower:
            bot["cadence"] = "hourly"
            touched_bot_fields.add("cadence")
        elif "weekly" in q_lower or "wekelijks" in q_lower:
            bot["cadence"] = "weekly"
            touched_bot_fields.add("cadence")
        elif "monthly" in q_lower or "maandelijks" in q_lower:
            bot["cadence"] = "monthly"
            touched_bot_fields.add("cadence")
        elif "daily" in q_lower or "dagelijks" in q_lower:
            bot["cadence"] = "daily"
            touched_bot_fields.add("cadence")

        for key, pattern in [
            ("budget_total_eur", r"(?:totaal\s*)?budget\s*(?:aan\s+)?(?:van|naar|=|:)?\s*(?:€|eur|euro)?\s*([0-9][0-9.,]*)"),
            ("budget_daily_limit_eur", r"(?:daglimiet|daily limit)\s*(?:van|=|:)?\s*(?:€|eur|euro)?\s*([0-9][0-9.,]*)"),
            ("budget_min_order_eur", r"(?:min(?:imum)? order|min order)\s*(?:van|=|:)?\s*(?:€|eur|euro)?\s*([0-9][0-9.,]*)"),
            ("budget_max_order_eur", r"(?:max(?:imum)? order|max order)\s*(?:van|=|:)?\s*(?:€|eur|euro)?\s*([0-9][0-9.,]*)"),
        ]:
            match = re.search(pattern, q_lower)
            if match:
                bot[key] = _number(match.group(1))
                touched_bot_fields.add(key)

        amount = re.search(r"(?:€|eur|euro)\s*([0-9][0-9.,]*)|([0-9][0-9.,]*)\s*(?:€|eur|euro)", q_lower)
        if amount and "budget" in q_lower and not bot.get("budget_total_eur"):
            bot["budget_total_eur"] = _number(amount.group(1) or amount.group(2))
            touched_bot_fields.add("budget_total_eur")

        if any(phrase in q_lower for phrase in ["live akkoord", "ik bevestig live", "live bevestig", "live risico akkoord"]):
            bot["live_trading_ack"] = True
            touched_bot_fields.add("live_trading_ack")

        self._apply_bot_name_default(draft)
        draft["_touched_bot_fields"] = sorted(touched_bot_fields)

        validation = self._validate_bot_draft(draft)
        actions = []
        if validation["can_confirm"]:
            action_payload = deepcopy(draft)
            actions.append({
                "id": self._bot_action_id(action_payload),
                "type": "create_bot",
                "label": "Bot bijwerken" if draft.get("operation") == "update" else "Bot aanmaken",
                "payload": action_payload,
                "risk_level": "high" if bot.get("is_live") else "medium",
                "requires_confirmation": True,
                "autonomy_level": "confirm_required",
                "guardrails": {
                    "requires_confirmation": True,
                    "can_execute_without_user": False,
                    "execution_allowed": "bot_update" if draft.get("operation") == "update" else "bot_creation_only",
                    "live_trading": bool(bot.get("is_live")),
                },
            })

        return {
            "response": self._build_bot_message(draft, validation),
            "intent": "bot_creation",
            "flow": "bot_creation",
            "draft": draft,
            "state": self._bot_flow_state(draft, validation),
            "reasoning": self._bot_reasoning(draft, validation),
            "missing_fields": validation["missing_fields"],
            "invalid_fields": validation["invalid_fields"],
            "next_question": validation["next_question"],
            "can_confirm": validation["can_confirm"],
            "actions": actions,
        }

    async def build_bot_response_for_user(self, user_id: int, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        response = self.build_bot_response(query, context)
        if response.get("intent") == "bot_creation_cancelled" or not self.session:
            return response

        draft = response.get("draft") if isinstance(response.get("draft"), dict) else {}
        await self._hydrate_existing_bot_draft_from_db(user_id, draft)
        await self._hydrate_bot_draft_from_db(user_id, draft)
        await self._apply_live_bot_preflight(user_id, draft)
        validation = self._validate_bot_draft(draft)

        existing_bot = await self._existing_bot_for_strategy(user_id, draft.get("strategy_id"))
        if existing_bot and draft.get("operation") == "update":
            draft["existing_bot_id"] = existing_bot.get("id")
            draft["bot_id"] = draft.get("bot_id") or existing_bot.get("id")
            await self._hydrate_existing_bot_draft_from_db(user_id, draft)
            await self._apply_live_bot_preflight(user_id, draft)
            validation = self._validate_bot_draft(draft)
        elif existing_bot:
            draft["existing_bot_id"] = existing_bot.get("id")
            duplicate_validation = {
                "missing_fields": [],
                "invalid_fields": [{"field": "strategy_id", "reason": "voor deze strategie bestaat al een bot"}],
                "next_question": "bot.update_existing",
                "can_confirm": False,
            }
            response.update({
                "response": (
                    f"Strategie #{draft.get('strategy_id')} heeft al bot #{existing_bot.get('id')}. "
                    "Ik maak daarom geen tweede bot aan. Open de bot-instellingen om deze bot bij te werken."
                ),
                "draft": draft,
                "state": self._bot_flow_state(draft, duplicate_validation),
                "reasoning": self._bot_reasoning(draft, duplicate_validation),
                "missing_fields": duplicate_validation["missing_fields"],
                "invalid_fields": duplicate_validation["invalid_fields"],
                "next_question": duplicate_validation["next_question"],
                "can_confirm": False,
                "actions": [],
            })
            return response

        strategy_options = []
        if "strategy_id" in validation["missing_fields"]:
            strategy_options = await self._bot_strategy_options(user_id, draft)

        actions = []
        if validation["can_confirm"]:
            action_payload = deepcopy(draft)
            actions.append({
                "id": self._bot_action_id(action_payload),
                "type": "create_bot",
                "label": "Bot bijwerken" if draft.get("operation") == "update" else "Bot aanmaken",
                "payload": action_payload,
                "risk_level": "high" if draft["bot"].get("is_live") else "medium",
                "requires_confirmation": True,
                "autonomy_level": "confirm_required",
                "guardrails": {
                    "requires_confirmation": True,
                    "can_execute_without_user": False,
                    "execution_allowed": "bot_update" if draft.get("operation") == "update" else "bot_creation_only",
                    "live_trading": bool(draft["bot"].get("is_live")),
                },
            })

        response.update({
            "response": self._build_bot_message(draft, validation, strategy_options=strategy_options),
            "draft": draft,
            "state": self._bot_flow_state(draft, validation, strategy_options=strategy_options),
            "reasoning": self._bot_reasoning(draft, validation),
            "missing_fields": validation["missing_fields"],
            "invalid_fields": validation["invalid_fields"],
            "next_question": validation["next_question"],
            "can_confirm": validation["can_confirm"],
            "actions": actions,
        })
        return response

    async def build_indicator_config_response_for_user(self, user_id: int, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        context = context or {}
        previous = (
            context.get("finn_draft")
            if isinstance(context.get("finn_draft"), dict) and context["finn_draft"].get("draft_kind") == "indicator_config"
            else {}
        )
        draft = _deep_merge(empty_indicator_config_draft(), previous)

        q = (query or "").strip()
        q_lower = q.lower()
        mentioned_assets = _asset_mentions(q)
        explicit_indicator_input = bool(self._extract_indicator_name_hint(q, draft.get("category") or "macro"))
        if self.is_cancel_request(q):
            return {
                "response": "Prima, ik heb deze indicator-configuratie gestopt. Er is niets aangepast.",
                "intent": "indicator_config_cancelled",
                "flow": None,
                "draft": empty_indicator_config_draft(),
                "missing_fields": [],
                "invalid_fields": [],
                "next_question": None,
                "can_confirm": False,
                "actions": [],
            }

        if any(word in q_lower for word in ["reset", "herstel standaard", "terug naar standaard", "standaard terug", "default"]):
            draft["operation"] = "reset"
            draft["activate_node"] = False
            draft["score_mode"] = None
            draft["weight"] = None
            draft["custom_rules_touched"] = False
            draft["custom_rules_complete"] = False
            draft["custom_rule_buckets"] = []
        elif draft.get("operation") == "reset" and any(word in q_lower for word in ["standard", "standaard", "contrarian", "custom", "weight", "weging", "gewicht"]):
            draft["operation"] = "configure"

        if any(word in q_lower for word in ["technical", "technisch", "technische"]):
            draft["category"] = "technical"
        elif "macro" in q_lower or not draft.get("category"):
            draft["category"] = "macro"
        if draft.get("category") == "technical" and not draft.get("symbol") and not (draft.get("operation") == "reset" and not mentioned_assets and not context.get("symbol") and not context.get("setup_symbol")):
            draft["symbol"] = (context.get("symbol") or context.get("setup_symbol") or "BTC").upper()
        if draft.get("category") == "technical" and mentioned_assets:
            draft["symbol"] = mentioned_assets[0]

        mode = self._extract_indicator_score_mode(q_lower)
        if mode and draft.get("operation") != "reset":
            draft["score_mode"] = mode
        weight = self._extract_indicator_weight(q_lower)
        if weight is not None and draft.get("operation") != "reset":
            draft["weight"] = weight
        if any(word in q_lower for word in ["niet toevoegen", "niet activeren", "alleen config", "alleen instellingen"]):
            draft["activate_node"] = False
        elif any(word in q_lower for word in ["toevoegen", "voeg", "activeer", "node active", "node_active"]):
            draft["activate_node"] = True

        explicit_indicator = self._extract_indicator_name_hint(q, draft.get("category") or "macro")
        if explicit_indicator:
            draft["indicator"] = explicit_indicator

        await self._hydrate_indicator_config_draft(user_id, draft, q, explicit_indicator_input=explicit_indicator_input)
        custom_rules = self._extract_indicator_custom_bucket_rules(q, draft.get("rules") or [])
        if custom_rules is not None and draft.get("operation") != "reset":
            previous_buckets = set(draft.get("custom_rule_buckets") or [])
            current_buckets = set(custom_rules["provided_buckets"])
            provided_buckets = sorted(previous_buckets | current_buckets)
            draft["score_mode"] = "custom"
            draft["rules"] = custom_rules["rules"]
            draft["custom_rules_touched"] = True
            draft["custom_rule_buckets"] = provided_buckets
            draft["custom_rules_complete"] = len(provided_buckets) == len(INDICATOR_FIXED_BUCKETS)
            draft["missing_custom_buckets"] = [
                f"{int(lo)}-{int(hi)}"
                for lo, hi in INDICATOR_FIXED_BUCKETS
                if f"{int(lo)}-{int(hi)}" not in provided_buckets
            ]
            draft["changes"] = self._indicator_config_changes_from_snapshot(draft)
        if draft.get("operation") == "reset":
            draft["score_mode"] = None
            draft["weight"] = None
            draft["changes"] = self._indicator_reset_changes_from_snapshot(draft)
        validation = self._validate_indicator_config_draft(draft)

        actions = []
        if validation["can_confirm"]:
            action_payload = deepcopy(draft)
            actions.append({
                "id": self._indicator_config_action_id(action_payload),
                "type": "configure_indicator",
                "label": "Indicator resetten" if draft.get("operation") == "reset" else ("Indicator bijwerken" if draft.get("operation") == "update" else "Indicator toevoegen"),
                "payload": action_payload,
                "risk_level": "low",
                "requires_confirmation": True,
                "autonomy_level": "confirm_required",
                "guardrails": {
                    "requires_confirmation": True,
                    "can_execute_without_user": False,
                    "execution_allowed": "indicator_config_only",
                    "no_ai_generated_scoring": True,
                },
            })

        return {
            "response": self._build_indicator_config_message(draft, validation),
            "intent": "indicator_config",
            "flow": "indicator_config",
            "draft": draft,
            "state": self._indicator_config_flow_state(draft, validation),
            "reasoning": self._indicator_config_reasoning(draft, validation),
            "missing_fields": validation["missing_fields"],
            "invalid_fields": validation["invalid_fields"],
            "next_question": validation["next_question"],
            "can_confirm": validation["can_confirm"],
            "actions": actions,
        }

    async def build_status_response(self, user_id: int, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        context = context or {}
        q = (query or "").upper()
        asset = None
        for symbol in SUPPORTED_ASSETS:
            if re.search(rf"\b{symbol}\b", q):
                asset = symbol
                break
        draft = context.get("finn_draft") if isinstance(context.get("finn_draft"), dict) else None
        if not asset and draft:
            asset = draft.get("asset")
        asset = asset or "BTC"

        daily_scores = None
        active_setups = []
        if self.session:
            score_repo = ScoreRepository(self.session)
            daily_scores = await self._fetch_daily_scores_with_runtime_refresh(user_id, asset)
            active_setups = await score_repo.fetch_active_setups(user_id)

        if draft and draft.get("asset") == asset:
            analysis = self._evaluate_draft_against_scores(draft, daily_scores)
            response = self._status_message(asset, analysis, source="draft")
        else:
            matching_setups = [s for s in active_setups if str(s.get("symbol", "")).upper() == asset]
            best_setup = next((s for s in matching_setups if s.get("is_active")), None) or (matching_setups[0] if matching_setups else None)
            analysis = self._evaluate_setup_row(best_setup, daily_scores)
            response = self._status_message(asset, analysis, source="saved_setup")

        return {
            "response": response,
            "intent": "plan_status",
            "flow": "plan_status",
            "draft": draft,
            "missing_fields": [],
            "invalid_fields": [],
            "next_question": None,
            "can_confirm": False,
            "actions": [],
            "state": {
                "status": "answered",
                "current_flow": "plan_status",
                "asset": asset,
                "analysis": analysis,
                "autonomy_level": "advice_only",
            },
            "reasoning": {
                "confidence_score": 0.55 if analysis.get("confidence") == "medium" else 0.25,
                "risk_detected": not bool(analysis.get("is_active")),
                "reasons": self._analysis_reasons(analysis),
                "coaching_level": "plan_check",
            },
        }

    async def build_indicator_insight_response(
        self,
        user_id: int,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = context or {}
        q = (query or "").lower()
        asset = self._asset_from_query_or_context(query, context)
        categories = self._indicator_insight_categories(q)

        daily_scores = None
        macro_rows: List[Any] = []
        technical_rows: List[Any] = []
        market_rows: List[Any] = []
        market_snapshot = None
        available: Dict[str, List[Dict[str, Any]]] = {"macro": [], "technical": [], "market": []}
        configs: Dict[str, Dict[str, Any]] = {}

        if self.session:
            score_repo = ScoreRepository(self.session)
            macro_repo = MacroDataRepository(self.session)
            technical_repo = TechnicalDataRepository(self.session)
            market_repo = MarketDataRepository(self.session)
            config_service = IndicatorConfigService(IndicatorConfigRepository(self.session))

            daily_scores = await score_repo.fetch_daily_scores(user_id, asset)
            if "macro" in categories:
                macro_rows = await macro_repo.get_active_day_macro_data(user_id)
                available["macro"] = self._available_indicator_options(await macro_repo.get_global_indicators("macro"))
            if "technical" in categories:
                technical_rows = await technical_repo.get_day_data(user_id, asset)
                available["technical"] = self._available_indicator_options(await technical_repo.get_all_indicators())
            if "market" in categories:
                market_rows = await market_repo.get_active_day_indicators(user_id, asset)
                market_snapshot = await market_repo.get_latest_market_data(asset)
                available["market"] = self._available_indicator_options(await market_repo.get_global_indicators("market"))

            for category, rows in [("macro", macro_rows), ("technical", technical_rows), ("market", market_rows)]:
                for row in rows:
                    name = self._indicator_name(row, category)
                    if not name:
                        continue
                    key = f"{category}:{normalize_indicator_name(name)}"
                    try:
                        config = await config_service.get_indicator_config(category, normalize_indicator_name(name), user_id)
                        configs[key] = {
                            "score_mode": config.score_mode,
                            "weight": config.weight,
                            "rules_count": len(config.rules),
                        }
                    except Exception:
                        configs[key] = {"score_mode": "unknown", "weight": None, "rules_count": 0}

        analysis = self._build_indicator_insight_analysis(
            asset=asset,
            categories=categories,
            daily_scores=daily_scores,
            macro_rows=macro_rows,
            technical_rows=technical_rows,
            market_rows=market_rows,
            market_snapshot=market_snapshot,
            available=available,
            configs=configs,
        )
        response = self._indicator_insight_message(asset, analysis)
        reasons = self._indicator_insight_reasons(analysis)

        return {
            "response": response,
            "intent": "indicator_insight",
            "flow": "indicator_insight",
            "draft": None,
            "missing_fields": [],
            "invalid_fields": [],
            "next_question": None,
            "can_confirm": False,
            "actions": [],
            "state": {
                "status": "answered",
                "current_flow": "indicator_insight",
                "asset": asset,
                "analysis": analysis,
                "autonomy_level": "advice_only",
            },
            "reasoning": {
                "confidence_score": 0.72 if daily_scores else 0.45,
                "risk_detected": bool(analysis.get("warnings")),
                "reasons": reasons,
                "coaching_level": "indicator_insight",
            },
            "suggested_actions": analysis.get("suggested_actions") or [],
        }

    async def build_daily_coach_response(
        self,
        user_id: int,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = context or {}
        if self._should_build_portfolio_daily_coach(query, context):
            return await self.build_portfolio_daily_coach_response(user_id, query, context)

        asset = self._asset_from_query_or_context(query, context)
        daily_scores = None
        setup_analysis: Dict[str, Any] = {
            "is_active": False,
            "confidence": "low",
            "checks": {},
            "has_scores": False,
            "reason": "Geen scoredata of setup gevonden.",
        }
        active_strategy = {"active": False}
        bot_today = {"decisions": [], "scores": {}, "orders": [], "executions": []}
        onboarding_status: Dict[str, bool] = {}
        indicator_analysis = {
            "asset": asset,
            "has_daily_scores": False,
            "categories": {},
            "warnings": [],
            "suggestions": [],
        }

        if self.session:
            score_repo = ScoreRepository(self.session)
            daily_scores = await score_repo.fetch_daily_scores(user_id, asset)
            active_setups = await score_repo.fetch_active_setups(user_id)
            matching_setups = [s for s in active_setups if str(s.get("symbol", "")).upper() == asset]
            best_setup = next((s for s in matching_setups if s.get("is_active")), None) or (matching_setups[0] if matching_setups else None)
            setup_analysis = self._evaluate_setup_row(best_setup, daily_scores)

            try:
                active_strategy = await StrategyService(self.session).get_active_strategy_today(user_id)
            except Exception as exc:
                active_strategy = {"active": False, "error": str(exc)}

            try:
                bot_today = await BotService(self.session).get_bot_today(user_id, symbol=asset)
            except Exception as exc:
                bot_today = {"decisions": [], "scores": {}, "orders": [], "executions": [], "error": str(exc)}

            onboarding_status = await self._fetch_onboarding_status(user_id)

            insight = await self.build_indicator_insight_response(
                user_id,
                f"Welke macro technical market data gebruikt Finn voor {asset} vandaag?",
                context,
            )
            indicator_analysis = (insight.get("state") or {}).get("analysis") or indicator_analysis

        analysis = self._build_daily_coach_analysis(
            asset=asset,
            daily_scores=daily_scores,
            setup_analysis=setup_analysis,
            active_strategy=active_strategy,
            bot_today=bot_today,
            indicator_analysis=indicator_analysis,
            onboarding_status=onboarding_status,
        )
        response = self._daily_coach_message(analysis)

        return {
            "response": response,
            "intent": "daily_coach",
            "flow": "daily_coach",
            "draft": None,
            "missing_fields": [],
            "invalid_fields": [],
            "next_question": None,
            "can_confirm": False,
            "actions": [],
            "state": {
                "status": "answered",
                "current_flow": "daily_coach",
                "asset": asset,
                "analysis": analysis,
                "autonomy_level": "advice_only",
            },
            "reasoning": {
                "confidence_score": 0.78 if analysis.get("has_scores") else 0.45,
                "risk_detected": analysis.get("stance") != "plan_is_active",
                "reasons": analysis.get("reasons") or [],
                "coaching_level": "daily_cockpit",
            },
            "suggested_actions": analysis.get("suggested_actions") or [],
        }

    async def build_portfolio_daily_coach_response(
        self,
        user_id: int,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = context or {}
        asset_analyses: List[Dict[str, Any]] = []

        if self.session:
            score_repo = ScoreRepository(self.session)
            active_setups = await score_repo.fetch_active_setups(user_id)
            onboarding_status = await self._fetch_onboarding_status(user_id)
            best_setups_by_asset: Dict[str, Dict[str, Any]] = {}
            for setup in active_setups:
                symbol = str(setup.get("symbol") or "").upper()
                if symbol not in SUPPORTED_ASSETS:
                    continue
                current = best_setups_by_asset.get(symbol)
                if not current or (setup.get("is_active") and not current.get("is_active")):
                    best_setups_by_asset[symbol] = setup

            for asset in sorted(best_setups_by_asset.keys()):
                setup = best_setups_by_asset[asset]
                daily_scores = await self._fetch_daily_scores_with_runtime_refresh(user_id, asset)
                setup_analysis = self._evaluate_setup_row(setup, daily_scores)
                try:
                    bot_today = await BotService(self.session).get_bot_today(user_id, symbol=asset)
                except Exception as exc:
                    bot_today = {"decisions": [], "scores": {}, "orders": [], "executions": [], "error": str(exc)}
                try:
                    insight = await self.build_indicator_insight_response(
                        user_id,
                        f"Welke macro technical market data gebruikt Finn voor {asset} vandaag?",
                        {**context, "symbol": asset},
                    )
                    indicator_analysis = (insight.get("state") or {}).get("analysis") or {}
                except Exception as exc:
                    indicator_analysis = {
                        "asset": asset,
                        "has_daily_scores": bool(daily_scores),
                        "categories": {},
                        "warnings": [f"Indicatoranalyse voor {asset} kon niet worden geladen: {exc}"],
                        "suggestions": [],
                    }

                asset_analyses.append(self._build_daily_coach_analysis(
                    asset=asset,
                    daily_scores=daily_scores,
                    setup_analysis=setup_analysis,
                    active_strategy={"active": False, "portfolio_scope": True},
                    bot_today=bot_today,
                    indicator_analysis=indicator_analysis,
                    onboarding_status=onboarding_status,
                ))

        analysis = self._build_portfolio_daily_coach_analysis(asset_analyses)
        response = self._portfolio_daily_coach_message(analysis)

        return {
            "response": response,
            "intent": "daily_coach",
            "flow": "daily_coach",
            "draft": None,
            "missing_fields": [],
            "invalid_fields": [],
            "next_question": None,
            "can_confirm": False,
            "actions": [],
            "state": {
                "status": "answered",
                "current_flow": "daily_coach",
                "scope": "portfolio",
                "analysis": analysis,
                "autonomy_level": "advice_only",
            },
            "reasoning": {
                "confidence_score": 0.76 if analysis.get("has_any_scores") else 0.45,
                "risk_detected": bool(analysis.get("blocked_assets") or analysis.get("warning_assets")),
                "reasons": analysis.get("reasons") or [],
                "coaching_level": "portfolio_daily_cockpit",
            },
            "suggested_actions": analysis.get("suggested_actions") or [],
        }

    def _extract_from_query(self, query: str) -> Dict[str, Any]:
        q = query.lower()
        patch = empty_plan_patch()

        has_dca_language = any(word in q for word in [
            "dca", "accumuleer", "accumuleren", "periodiek", "wekelijks",
            "dagelijks", "maandelijks", "elke week", "iedere week",
            "elke dag", "iedere dag", "elke maand", "iedere maand",
        ])
        has_trade_language = any(word in q for word in [
            "trade", "entry", "stop loss", "stoploss", "target", "breakout",
            "swing", "short", "market order", "markt order", "limiet", "limit",
        ])

        if has_dca_language or re.search(r"\b(?:toch|bedoel|bedoelde|nee)\s+(?:een\s+)?dca\b", q):
            patch["plan_type"] = "dca"
        if has_trade_language or re.search(r"\b(?:toch|bedoel|bedoelde|nee)\s+(?:een\s+)?trade\b", q):
            patch["plan_type"] = "trade"
        if has_dca_language and has_trade_language:
            patch["plan_type"] = None

        if any(word in q for word in ["market order", "markt order", "market execution", "direct kopen", "nu kopen"]):
            patch["plan_type"] = "trade"
            patch["strategy"]["entry_type"] = "market"
        elif "breakout" in q:
            patch["plan_type"] = "trade"
            patch["strategy"]["entry_type"] = "breakout"
        elif any(word in q for word in ["limit", "limiet", "entry"]) or re.search(r"\b(?:bij|rond)\s*\d", q):
            patch["strategy"]["entry_type"] = "limit"

        if re.search(r"\bshort\b", q):
            patch["plan_type"] = "trade"
            patch["strategy"]["direction"] = "short"
            patch["_clarification"] = {
                "field": "strategy.direction",
                "reason": "short trades worden nog niet ondersteund; kies long of annuleer deze trade",
            }
        elif re.search(r"\blong\b", q):
            patch["strategy"]["direction"] = "long"
            patch["_clarification"] = False

        found_symbols = _asset_mentions(query)
        supported_symbols = [symbol for symbol in found_symbols if symbol in SUPPORTED_ASSETS]
        unsupported_symbols = [symbol for symbol in found_symbols if symbol not in SUPPORTED_ASSETS]
        if len(found_symbols) == 1 and supported_symbols:
            patch["asset"] = supported_symbols[0]
            if not isinstance(patch.get("_clarification"), dict):
                patch["_clarification"] = False
        elif found_symbols:
            patch["_clarification"] = {
                "field": "asset",
                "reason": "kies één ondersteund asset: BTC, ETH of SOL",
                "mentions": found_symbols,
                "unsupported": unsupported_symbols,
            }

        timeframe = re.search(r"\b(1M|1W|1D|4H|1H|15M|5M)\b", query.upper())
        if timeframe:
            patch["setup"]["timeframe"] = timeframe.group(1)

        if "dagelijks" in q or "daily" in q or "elke dag" in q or "iedere dag" in q:
            patch["dca"]["frequency"] = "daily"
        elif "wekelijks" in q or "weekly" in q or "elke week" in q or "iedere week" in q:
            patch["dca"]["frequency"] = "weekly"
        elif "maandelijks" in q or "monthly" in q or "elke maand" in q or "iedere maand" in q:
            patch["dca"]["frequency"] = "monthly"

        for raw, normalized in WEEKDAYS.items():
            if raw in q:
                patch["dca"]["day"] = normalized
                if not patch["dca"]["frequency"]:
                    patch["dca"]["frequency"] = "weekly"
                break

        month_day = re.search(r"(?:dag|day)\s*(\d{1,2})", q)
        if month_day:
            patch["dca"]["month_day"] = int(month_day.group(1))
            if not patch["dca"]["frequency"]:
                patch["dca"]["frequency"] = "monthly"

        if "custom" in q or "smart" in q or "slim" in q:
            patch["dca"]["dca_mode"] = "custom"
        elif "standaard" in q or "standard" in q:
            patch["dca"]["dca_mode"] = "standard"

        threshold = re.search(r"(?:onder|below|score)\s*(\d{1,2})", q)
        if threshold:
            patch["dca"]["buy_score_threshold"] = int(threshold.group(1))

        amount = re.search(r"(?:€|eur|euro)\s*([0-9][0-9.,]*)|([0-9][0-9.,]*)\s*(?:€|eur|euro)", q)
        if amount:
            value = _number(amount.group(1) or amount.group(2))
            if value:
                patch["strategy"]["base_amount_eur"] = value

        entry = re.search(rf"entry\s*(?:op|=|:)?\s*{NUMBER_WITH_DELIMITER}", q)
        if entry:
            patch["strategy"]["entry"] = _number(entry.group(1))
        elif has_trade_language:
            entry_hint = re.search(
                rf"(?:breakout\s+)?(?:boven|above|bij|rond)\s*{NUMBER_WITH_DELIMITER}",
                q,
            )
            if entry_hint:
                patch["strategy"]["entry"] = _number(entry_hint.group(1))

        stop = re.search(r"stop\s*(?:loss)?|stoploss", q)
        if stop:
            after = q[stop.end():]
            value_match = re.search(rf"(?:op|=|:)?\s*{NUMBER_WITH_DELIMITER}", after)
            if value_match:
                patch["strategy"]["stop_loss"] = _number(value_match.group(1))

        targets = _extract_targets(query)
        if targets:
            patch["strategy"]["targets"] = targets

        macro = _extract_score_range(query, "macro")
        technical = _extract_score_range(query, "technical")
        market = _extract_score_range(query, "market")
        if macro:
            patch["setup"]["macro_score_range"] = macro
        if technical:
            patch["setup"]["technical_score_range"] = technical
        if market:
            patch["setup"]["market_score_range"] = market

        quoted_name = re.search(r"(?:noem|naam|heet)\s+(?:hem|haar|deze)?\s*[\"']?([^\"'.]+)[\"']?", q, re.IGNORECASE)
        if quoted_name:
            name = quoted_name.group(1).strip()
            if 2 <= len(name) <= 80:
                patch["setup"]["name"] = name

        if "bot" in q or "bot-assisted" in q or "bot assisted" in q or "met bot" in q:
            patch["bot"]["create_bot"] = True
            patch["bot"]["automation"] = "bot_assisted"
        if "semi-auto" in q or "semi auto" in q or "semi automatisch" in q:
            patch["bot"]["create_bot"] = True
            patch["bot"]["automation"] = "bot_assisted"
            patch["bot"]["mode"] = "semi-auto"
        if re.search(r"\bauto(?:matisch)?\b", q) and "niet automatisch" not in q and not any(word in q for word in ["semi-auto", "semi auto", "semi automatisch"]):
            patch["bot"]["create_bot"] = True
            patch["bot"]["automation"] = "bot_assisted"
            patch["bot"]["mode"] = "auto"
        if any(word in q for word in ["geen bot", "zonder bot", "niet automatisch", "manual only", "manual-only", "handmatig", "alleen handmatig"]):
            patch["bot"]["create_bot"] = False
            patch["bot"]["automation"] = "manual_only"
            patch["bot"]["mode"] = "manual"
        if "live" in q:
            patch["bot"]["create_bot"] = True
            patch["bot"]["automation"] = "bot_assisted"
            patch["bot"]["is_live"] = True
        if "paper" in q:
            patch["bot"]["create_bot"] = True
            patch["bot"]["automation"] = "bot_assisted"
            patch["bot"]["is_live"] = False
        if "agressief" in q or "aggressive" in q:
            patch["bot"]["risk_profile"] = "aggressive"
        elif "conservatief" in q or "conservative" in q:
            patch["bot"]["risk_profile"] = "conservative"

        return patch

    def _apply_defaults(self, draft: Dict[str, Any]) -> None:
        if draft.get("asset"):
            draft["asset"] = str(draft["asset"]).upper()
        if draft.get("plan_type") in {"dca", "trade"} and draft["bot"].get("create_bot") is None:
            draft["bot"]["create_bot"] = True
        if draft.get("plan_type") == "trade" and not draft["strategy"].get("direction"):
            draft["strategy"]["direction"] = "long"
        if draft.get("plan_type") == "trade" and not draft["strategy"].get("entry_type"):
            draft["strategy"]["entry_type"] = "limit"
        if draft["bot"].get("automation") is None:
            draft["bot"]["automation"] = "bot_assisted" if draft["bot"].get("create_bot") else "manual_only"
        if not draft["setup"].get("timeframe"):
            draft["setup"]["timeframe"] = "1W" if draft.get("plan_type") == "dca" else None
        draft["setup"]["macro_score_range"] = draft["setup"].get("macro_score_range") or [30, 70]
        draft["setup"]["technical_score_range"] = draft["setup"].get("technical_score_range") or [40, 80]
        draft["setup"]["market_score_range"] = draft["setup"].get("market_score_range") or [20, 60]
        if not draft["setup"].get("name") and draft.get("asset") and draft.get("plan_type"):
            label = "Smart DCA" if draft["plan_type"] == "dca" else "Trade Plan"
            draft["setup"]["name"] = f"{draft['asset']} {label}"
        if draft.get("plan_type") == "dca" and draft["dca"].get("frequency") == "weekly" and not draft["dca"].get("day"):
            draft["dca"]["day"] = "monday"
        if draft["bot"].get("create_bot") and not draft["bot"].get("risk_profile"):
            draft["bot"]["risk_profile"] = "balanced"

    def _action_id(self, payload: Dict[str, Any]) -> str:
        normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return f"finn-plan-{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:24]}"

    def _action_risk(self, draft: Dict[str, Any]) -> str:
        if draft.get("bot", {}).get("is_live"):
            return "high"
        if draft.get("plan_type") == "trade":
            return "medium"
        return "low"

    def _guardrails(self, draft: Dict[str, Any]) -> Dict[str, Any]:
        bot = draft.get("bot") or {}
        return {
            "requires_confirmation": True,
            "execution_allowed": "paper_or_manual_only" if not bot.get("is_live") else "live_requires_explicit_user_confirm",
            "live_trading": bool(bot.get("is_live")),
            "can_execute_without_user": False,
            "budget": {
                "total_eur": float(bot.get("total_budget_eur") or 0),
                "daily_limit_eur": float(bot.get("daily_limit_eur") or 0),
                "max_asset_exposure_pct": float(bot.get("max_asset_exposure_pct") or 100),
            },
        }

    def _flow_state(self, draft: Dict[str, Any], validation: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "ready_for_confirmation" if validation["can_confirm"] else "collecting",
            "current_flow": "plan_creation",
            "asset": draft.get("asset"),
            "plan_type": draft.get("plan_type"),
            "next_question": validation["next_question"],
            "autonomy_level": "confirm_required",
            "guardrails": self._guardrails(draft),
            "version": FINN_STATE_VERSION,
        }

    def _reasoning(self, draft: Dict[str, Any], validation: Dict[str, Any]) -> Dict[str, Any]:
        reasons = []
        if validation["missing_fields"]:
            reasons.append(f"Ontbrekende velden: {', '.join(validation['missing_fields'])}")
        if validation["invalid_fields"]:
            reasons.append(f"Ongeldige velden: {', '.join(item['field'] for item in validation['invalid_fields'])}")
        if not reasons:
            reasons.append("Alle verplichte planvelden zijn aanwezig en validatie is geslaagd.")
        return {
            "confidence_score": 0.9 if validation["can_confirm"] else 0.55,
            "risk_detected": bool(validation["invalid_fields"]) or bool(draft.get("bot", {}).get("is_live")),
            "reasons": reasons,
            "coaching_level": "plan_creation",
        }

    def _apply_strategy_context(self, draft: Dict[str, Any], context: Dict[str, Any]) -> None:
        if context.get("setup_id") and not draft.get("setup_id"):
            draft["setup_id"] = context.get("setup_id")
        if context.get("strategy_id") and not draft.get("strategy_id"):
            draft["strategy_id"] = context.get("strategy_id")
            draft["operation"] = "update"
        if context.get("setup_type") and not draft.get("setup_type"):
            draft["setup_type"] = str(context.get("setup_type")).lower()
        if context.get("setup_symbol") and not draft.get("asset"):
            draft["asset"] = str(context.get("setup_symbol")).upper()
        elif context.get("symbol") and not draft.get("asset"):
            draft["asset"] = str(context.get("symbol")).upper()
        if context.get("setup_timeframe") and not draft.get("timeframe"):
            draft["timeframe"] = context.get("setup_timeframe")
        elif context.get("timeframe") and not draft.get("timeframe"):
            draft["timeframe"] = context.get("timeframe")

    def _apply_strategy_defaults(self, draft: Dict[str, Any]) -> None:
        if draft.get("operation") not in {"create", "update"}:
            draft["operation"] = "create"
        if draft.get("asset"):
            draft["asset"] = str(draft["asset"]).upper()
        if draft.get("setup_type"):
            draft["setup_type"] = str(draft["setup_type"]).lower()
        if draft.get("setup_type") == "trade" and not draft["strategy"].get("entry_type"):
            draft["strategy"]["entry_type"] = "limit"
        if draft.get("setup_type") == "trade" and not draft["strategy"].get("direction"):
            draft["strategy"]["direction"] = "long"
        if not draft["strategy"].get("automation"):
            draft["strategy"]["automation"] = "manual_only"
        if not draft["strategy"].get("risk_profile"):
            draft["strategy"]["risk_profile"] = "balanced"

    async def _hydrate_bot_draft_from_db(self, user_id: int, draft: Dict[str, Any]) -> None:
        if not self.session or not isinstance(draft, dict) or not draft.get("strategy_id"):
            return
        strategy = await StrategyService(self.session).repository.get_raw_strategy_with_setup(int(draft["strategy_id"]), user_id)
        if not strategy:
            draft["_strategy_lookup_error"] = "strategie niet gevonden"
            return
        draft.pop("_strategy_lookup_error", None)
        data = json.loads(strategy.get("data")) if isinstance(strategy.get("data"), str) else (strategy.get("data") or {})
        draft["asset"] = str(strategy.get("setup_symbol") or data.get("symbol") or "").upper() or None
        draft["setup_type"] = (strategy.get("setup_type") or strategy.get("existing_setup_type") or data.get("setup_type") or "").lower() or None
        draft["timeframe"] = strategy.get("setup_timeframe") or data.get("timeframe")
        self._apply_bot_name_default(draft)

    async def _hydrate_existing_bot_draft_from_db(self, user_id: int, draft: Dict[str, Any]) -> None:
        if not self.session or not isinstance(draft, dict):
            return
        bot_id = draft.get("bot_id")
        if not bot_id:
            return
        existing = await BotService(self.session).repository.get_bot_config(user_id, int(bot_id))
        if not existing:
            draft["_bot_lookup_error"] = "bot niet gevonden"
            return
        draft.pop("_bot_lookup_error", None)
        bot = draft.get("bot") or {}
        draft["operation"] = "update"
        draft["bot_id"] = int(existing["id"])
        draft["existing_bot_id"] = int(existing["id"])
        draft["strategy_id"] = draft.get("strategy_id") or existing.get("strategy_id")
        draft["asset"] = str(existing.get("symbol") or "").upper() or draft.get("asset")
        draft["setup_type"] = existing.get("setup_type") or draft.get("setup_type")
        draft["timeframe"] = existing.get("timeframe") or draft.get("timeframe")

        snapshot = self._bot_snapshot(existing)
        draft["existing_bot_snapshot"] = snapshot
        for key, value in snapshot.items():
            if key in bot and (bot.get(key) in [None, ""] or key not in draft.get("_touched_bot_fields", [])):
                bot[key] = value
        draft["changes"] = self._bot_changes(draft)

    async def _apply_live_bot_preflight(self, user_id: int, draft: Dict[str, Any]) -> None:
        bot = draft.get("bot") or {}
        draft["_live_exchange_ready"] = True
        if not bot.get("is_live") or not self.session:
            return
        keys = await ExchangeRepository(self.session).get_active_keys(user_id)
        draft["_live_exchange_ready"] = bool(keys)

    def _bot_snapshot(self, bot_row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "name": bot_row.get("name"),
            "mode": bot_row.get("mode") or "manual",
            "is_live": bool(bot_row.get("is_live")),
            "risk_profile": bot_row.get("risk_profile") or "balanced",
            "cadence": bot_row.get("cadence") or "daily",
            "base_currency": bot_row.get("base_currency") or "EUR",
            "budget_total_eur": float(bot_row.get("budget_total_eur") or 0),
            "budget_daily_limit_eur": float(bot_row.get("budget_daily_limit_eur") or 0),
            "budget_min_order_eur": float(bot_row.get("budget_min_order_eur") or 0),
            "budget_max_order_eur": float(bot_row.get("budget_max_order_eur") or 0),
            "max_asset_exposure_pct": float(bot_row.get("max_asset_exposure_pct") or 100),
        }

    def _bot_changes(self, draft: Dict[str, Any]) -> List[Dict[str, Any]]:
        snapshot = draft.get("existing_bot_snapshot") if isinstance(draft.get("existing_bot_snapshot"), dict) else {}
        if not snapshot:
            return []
        bot = draft.get("bot") or {}
        changes = []
        for field in [
            "name", "mode", "is_live", "risk_profile", "cadence", "base_currency",
            "budget_total_eur", "budget_daily_limit_eur", "budget_min_order_eur",
            "budget_max_order_eur", "max_asset_exposure_pct",
        ]:
            old = snapshot.get(field)
            new = bot.get(field)
            if old != new:
                changes.append({"field": field, "from": old, "to": new})
        return changes

    def _reset_bot_strategy_binding(self, draft: Dict[str, Any]) -> None:
        draft["existing_bot_id"] = None
        draft["asset"] = None
        draft["setup_type"] = None
        draft["timeframe"] = None
        draft.pop("_strategy_lookup_error", None)
        bot = draft.get("bot") or {}
        bot["name"] = None

    def _bot_name_label(self, bot: Dict[str, Any]) -> str:
        mode = str(bot.get("mode") or "manual").lower()
        if bot.get("is_live"):
            return "Live"
        if mode == "auto":
            return "Auto"
        if mode == "semi-auto":
            return "Semi-Auto"
        return "Paper"

    def _is_generated_bot_name(self, name: Any) -> bool:
        if not isinstance(name, str):
            return False
        return bool(re.match(r"^Finn (?:Strategy \d+|[A-Z0-9-]{2,10}) (?:Paper|Live|Auto|Semi-Auto) Bot$", name.strip()))

    def _apply_bot_name_default(self, draft: Dict[str, Any]) -> None:
        bot = draft.get("bot") or {}
        if not draft.get("strategy_id"):
            return
        current_name = bot.get("name")
        if current_name and not self._is_generated_bot_name(current_name):
            return
        label = self._bot_name_label(bot)
        subject = draft.get("asset") or f"Strategy {draft['strategy_id']}"
        bot["name"] = f"Finn {subject} {label} Bot"

    async def _existing_bot_for_strategy(self, user_id: int, strategy_id: Optional[int]) -> Optional[Dict[str, Any]]:
        if not self.session or not strategy_id:
            return None
        result = await self.session.execute(
            text("""
                SELECT id, name, mode, is_live, risk_profile
                FROM bot_configs
                WHERE user_id = :user_id AND strategy_id = :strategy_id
                ORDER BY id ASC
                LIMIT 1
            """),
            {"user_id": user_id, "strategy_id": int(strategy_id)},
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None

    async def _bot_strategy_options(self, user_id: int, draft: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.session:
            return []
        strategies = await StrategyService(self.session).query_strategies(user_id, {})
        asset = (draft.get("asset") or "").upper()
        options = []
        for strategy in strategies:
            if asset and str(strategy.get("symbol") or "").upper() != asset:
                continue
            existing_bot = await self._existing_bot_for_strategy(user_id, strategy.get("id"))
            if existing_bot:
                continue
            options.append({
                "id": strategy.get("id"),
                "name": strategy.get("name"),
                "symbol": strategy.get("symbol"),
                "setup_type": strategy.get("setup_type"),
                "timeframe": strategy.get("timeframe"),
            })
            if len(options) >= 5:
                break
        return options

    def _has_explicit_strategy_create_intent(self, q_lower: str) -> bool:
        return bool(
            re.search(r"\b(?:maak|aanmaken|creeer|creeër|bouw|instellen)\b", q_lower)
            or re.search(r"\b(?:nieuwe|nieuw|tweede)\s+strateg(?:ie|y)\b", q_lower)
            or re.search(r"\bstrateg(?:ie|y)\s+(?:aanmaken|maken)\b", q_lower)
        )

    def _has_explicit_strategy_update_intent(self, q_lower: str) -> bool:
        return bool(
            re.search(r"\b(?:wijzig|update|bijwerken|verander)\b", q_lower)
            or re.search(r"\b(?:aanpassen|aangepast)\b", q_lower)
            or re.search(r"\bpas\b.+\baan\b", q_lower)
        )

    async def _hydrate_strategy_draft_from_db(self, user_id: int, draft: Dict[str, Any]) -> None:
        if not self.session or not isinstance(draft, dict):
            return
        strategy_service = StrategyService(self.session)
        strategy_id = draft.get("strategy_id")
        if strategy_id:
            existing = await strategy_service.repository.get_raw_strategy_with_setup(int(strategy_id), user_id)
            if not existing:
                draft["_strategy_lookup_error"] = "strategie niet gevonden"
                return
            setup_id = existing.get("setup_id")
            if setup_id and not draft.get("setup_id"):
                draft["setup_id"] = setup_id
            draft["operation"] = "update"
            self._merge_existing_strategy_into_draft(draft, strategy_service._format_strategy_row(existing) or {})

        setup_id = draft.get("setup_id")
        if not setup_id:
            return
        setup_row = await SetupService(self.session).repository.get_setup_by_id(int(setup_id), user_id)
        if not setup_row:
            draft["_setup_lookup_error"] = "setup niet gevonden"
            return
        if not draft.get("setup_type"):
            draft["setup_type"] = str(setup_row.get("setup_type") or "").lower() or None
        if not draft.get("asset"):
            draft["asset"] = str(setup_row.get("symbol") or "").upper() or None
        if not draft.get("timeframe"):
            draft["timeframe"] = setup_row.get("timeframe")
        self._apply_strategy_defaults(draft)

    async def _load_strategy_snapshot_for_diff(
        self,
        user_id: int,
        draft: Dict[str, Any],
        strategy_service: StrategyService,
    ) -> Optional[Dict[str, Any]]:
        strategy_id = draft.get("strategy_id")
        if not strategy_id:
            return None
        existing = await strategy_service.repository.get_raw_strategy_with_setup(int(strategy_id), user_id)
        if not existing:
            return None
        return strategy_service._format_strategy_row(existing)

    def _merge_existing_strategy_into_draft(self, draft: Dict[str, Any], existing: Dict[str, Any]) -> None:
        if not existing:
            return
        draft["operation"] = "update"
        draft["strategy_id"] = draft.get("strategy_id") or existing.get("id")
        draft["setup_id"] = draft.get("setup_id") or existing.get("setup_id")
        draft["setup_type"] = draft.get("setup_type") or existing.get("setup_type")
        draft["asset"] = draft.get("asset") or existing.get("symbol")
        draft["timeframe"] = draft.get("timeframe") or existing.get("timeframe")
        strategy = draft.get("strategy") or {}
        defaults = {
            "base_amount_eur": existing.get("base_amount"),
            "execution_mode": existing.get("execution_mode") or "fixed",
            "direction": existing.get("direction") or "long",
            "entry_type": existing.get("entry_type") or existing.get("trade_execution_mode"),
            "market_execution_ack": False,
            "entry": existing.get("entry"),
            "stop_loss": existing.get("stop_loss"),
            "targets": existing.get("targets"),
            "automation": existing.get("automation") or "manual_only",
            "risk_profile": existing.get("risk_profile") or "balanced",
        }
        for field, value in defaults.items():
            if strategy.get(field) is None and value is not None:
                strategy[field] = value
        draft["strategy"] = strategy
        self._apply_strategy_defaults(draft)

    def _strategy_changes(self, existing: Dict[str, Any], draft: Dict[str, Any]) -> List[Dict[str, Any]]:
        strategy = draft.get("strategy") or {}
        data = self._strategy_existing_data(existing)
        existing_map = {
            "base_amount_eur": self._first_present(existing.get("base_amount"), data.get("base_amount"), data.get("base_amount_eur")),
            "execution_mode": self._first_present(existing.get("execution_mode"), data.get("execution_mode")),
            "entry_type": self._first_present(existing.get("entry_type"), existing.get("trade_execution_mode"), data.get("entry_type"), data.get("trade_execution_mode")),
            "entry": self._first_present(existing.get("entry"), data.get("entry")),
            "stop_loss": self._first_present(existing.get("stop_loss"), data.get("stop_loss")),
            "targets": self._first_present(existing.get("targets"), data.get("targets")),
        }
        changes = []
        for field, before in existing_map.items():
            after = strategy.get(field)
            if self._is_emptyish(before) and self._is_emptyish(after):
                continue
            if self._normalized_compare_value(before) != self._normalized_compare_value(after):
                changes.append({"field": field, "from": before, "to": after})
        return changes

    def _strategy_existing_data(self, existing: Dict[str, Any]) -> Dict[str, Any]:
        raw_data = existing.get("data") if isinstance(existing, dict) else None
        if isinstance(raw_data, str):
            try:
                parsed = json.loads(raw_data)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return raw_data if isinstance(raw_data, dict) else {}

    def _first_present(self, *values: Any) -> Any:
        for value in values:
            if value is not None and value != "":
                return value
        return None

    def _is_emptyish(self, value: Any) -> bool:
        return value is None or value == "" or value == [] or value == {}

    def _normalized_compare_value(self, value: Any) -> Any:
        if isinstance(value, float):
            return round(value, 8)
        if isinstance(value, list):
            return [self._normalized_compare_value(item) for item in value]
        return value

    async def _strategy_setup_options(self, user_id: int, draft: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self.session:
            return []
        setup_type = draft.get("setup_type")
        rows = await SetupService(self.session).repository.get_all_setups(
            user_id,
            setup_type if setup_type in {"dca", "trade"} else None,
        )
        asset = (draft.get("asset") or "").upper()
        options = []
        for row in rows:
            if asset and str(row.get("symbol") or "").upper() != asset:
                continue
            options.append({
                "id": row.get("id"),
                "name": row.get("name"),
                "symbol": row.get("symbol"),
                "timeframe": row.get("timeframe"),
                "setup_type": row.get("setup_type"),
            })
            if len(options) >= 5:
                break
        return options

    def _validate_strategy_draft(self, draft: Dict[str, Any]) -> Dict[str, Any]:
        missing: List[str] = []
        invalid: List[Dict[str, str]] = []

        if draft.get("_setup_lookup_error"):
            invalid.append({"field": "setup_id", "reason": draft["_setup_lookup_error"]})
        if draft.get("_strategy_lookup_error"):
            invalid.append({"field": "strategy_id", "reason": draft["_strategy_lookup_error"]})
        if draft.get("operation") == "update" and not draft.get("strategy_id"):
            missing.append("strategy_id")
        if not draft.get("setup_id"):
            missing.append("setup_id")
        if draft.get("setup_type") not in {"dca", "trade"}:
            missing.append("setup_type")
        if not draft.get("asset"):
            missing.append("asset")
        if not draft.get("timeframe"):
            missing.append("timeframe")

        strategy = draft.get("strategy") or {}
        amount = strategy.get("base_amount_eur")
        if amount is None:
            missing.append("strategy.base_amount_eur")
        elif not isinstance(amount, (int, float)) or amount <= 0:
            invalid.append({"field": "strategy.base_amount_eur", "reason": "bedrag moet groter dan 0 zijn"})
        elif amount > 1_000_000:
            invalid.append({"field": "strategy.base_amount_eur", "reason": "bedrag is onrealistisch hoog; gebruik maximaal 1.000.000 euro"})

        if draft.get("setup_type") == "trade":
            if strategy.get("direction") != "long":
                invalid.append({"field": "strategy.direction", "reason": "alleen long trades worden nu ondersteund"})
            if strategy.get("entry_type") not in {"limit", "breakout", "market"}:
                missing.append("strategy.entry_type")
            if strategy.get("entry_type") == "market" and not strategy.get("market_execution_ack"):
                missing.append("strategy.market_execution_ack")
            entry = strategy.get("entry")
            stop_loss = strategy.get("stop_loss")
            targets = strategy.get("targets")
            if entry is None:
                missing.append("strategy.entry")
            if stop_loss is None:
                missing.append("strategy.stop_loss")
            if not targets:
                missing.append("strategy.targets")
            for field, value in [("strategy.entry", entry), ("strategy.stop_loss", stop_loss)]:
                if value is not None and (not isinstance(value, (int, float)) or value <= 0 or value > 10_000_000):
                    invalid.append({"field": field, "reason": "prijs moet groter dan 0 en realistisch zijn"})
            if isinstance(targets, list):
                for target in targets:
                    if not isinstance(target, (int, float)) or target <= 0 or target > 10_000_000:
                        invalid.append({"field": "strategy.targets", "reason": "targets moeten positieve realistische prijzen zijn"})
                        break
            if isinstance(entry, (int, float)) and isinstance(stop_loss, (int, float)) and stop_loss >= entry:
                invalid.append({"field": "strategy.stop_loss", "reason": "voor long trades moet stop-loss lager zijn dan entry"})
            if isinstance(entry, (int, float)) and isinstance(targets, list):
                numeric_targets = [t for t in targets if isinstance(t, (int, float))]
                if [t for t in numeric_targets if t <= entry]:
                    invalid.append({"field": "strategy.targets", "reason": "voor long trades moeten targets boven entry liggen"})
                if len(numeric_targets) > 1 and any(numeric_targets[i] >= numeric_targets[i + 1] for i in range(len(numeric_targets) - 1)):
                    invalid.append({"field": "strategy.targets", "reason": "targets moeten oplopend zijn"})
                if isinstance(stop_loss, (int, float)) and stop_loss < entry:
                    risk = entry - stop_loss
                    reward = max(numeric_targets or [entry]) - entry
                    if risk > 0 and reward / risk < 1:
                        invalid.append({"field": "strategy.risk_reward", "reason": "risk/reward moet minimaal 1:1 zijn"})

        next_question = missing[0] if missing else (invalid[0]["field"] if invalid else None)
        return {
            "missing_fields": missing,
            "invalid_fields": invalid,
            "next_question": next_question,
            "can_confirm": not missing and not invalid,
        }

    def _build_strategy_message(self, draft: Dict[str, Any], validation: Dict[str, Any], setup_options: Optional[List[Dict[str, Any]]] = None) -> str:
        next_question = validation["next_question"]
        if validation["invalid_fields"]:
            issue = validation["invalid_fields"][0]
            return f"Ik zie een probleem met {issue['field']}: {issue['reason']}. Wat wil je hiervoor instellen?"
        if next_question == "setup_id":
            if setup_options:
                lines = ["Voor welke setup wil je deze strategie maken? Ik zie deze opties:"]
                for option in setup_options:
                    lines.append(f"- setup {option.get('id')}: {option.get('name')} ({option.get('symbol')} {option.get('setup_type')} {option.get('timeframe')})")
                return "\n".join(lines)
            return "Voor welke setup wil je deze strategie maken? Noem bijvoorbeeld setup 12 of open eerst de setup."
        if next_question == "strategy_id":
            return "Welke bestaande strategie wil je aanpassen? Noem bijvoorbeeld strategie 12 of open eerst de strategie."
        if next_question == "setup_type":
            return "Is deze strategie voor een DCA-setup of een gewone trade-setup?"
        if next_question == "strategy.base_amount_eur":
            return "Met welk basisbedrag in euro wil je deze strategie uitvoeren?"
        if next_question == "strategy.entry_type":
            return "Wil je een limit entry, breakout trigger of market execution gebruiken?"
        if next_question == "strategy.market_execution_ack":
            return "Market execution kan direct uitvoeren zodra je bevestigt. Zeg 'market akkoord' als je dit echt zo wilt vastleggen."
        if next_question == "strategy.entry":
            return "Welke entry-prijs hoort bij deze strategie?"
        if next_question == "strategy.stop_loss":
            return "Welke stop-loss hoort bij deze strategie?"
        if next_question == "strategy.targets":
            return "Welke target(s) wil je gebruiken? Je mag meerdere targets met komma's geven."
        summary = self._strategy_summary(draft)
        return f"Ik heb je strategie klaarstaan. Controleer dit even en bevestig als het klopt:\n\n{summary}"

    def _strategy_summary(self, draft: Dict[str, Any]) -> str:
        strategy = draft.get("strategy") or {}
        lines = [
            f"- Type: strategie {'bijwerken' if draft.get('operation') == 'update' else 'aanmaken'}",
            f"- Setup: #{draft.get('setup_id')}",
            f"- Strategie: #{draft.get('strategy_id')}" if draft.get("operation") == "update" else None,
            f"- Setup type: {draft.get('setup_type')}",
            f"- Asset: {draft.get('asset')}",
            f"- Timeframe: {draft.get('timeframe')}",
            f"- Bedrag: €{strategy.get('base_amount_eur')}",
        ]
        lines = [line for line in lines if line]
        if draft.get("setup_type") == "trade":
            lines.extend([
                f"- Uitvoering: {strategy.get('entry_type')}",
                f"- Market akkoord: {'ja' if strategy.get('market_execution_ack') else 'nee'}" if strategy.get("entry_type") == "market" else None,
                f"- Entry: {strategy.get('entry')}",
                f"- Stop-loss: {strategy.get('stop_loss')}",
                f"- Targets: {strategy.get('targets')}",
                f"- Automatisering: {strategy.get('automation')}",
            ])
            lines = [line for line in lines if line]
        return "\n".join(lines)

    def _strategy_flow_state(self, draft: Dict[str, Any], validation: Dict[str, Any], setup_options: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        return {
            "status": "ready_for_confirmation" if validation["can_confirm"] else "collecting",
            "current_flow": "strategy_creation",
            "asset": draft.get("asset"),
            "setup_id": draft.get("setup_id"),
            "strategy_id": draft.get("strategy_id"),
            "operation": draft.get("operation") or "create",
            "setup_type": draft.get("setup_type"),
            "setup_options": setup_options or [],
            "changes": draft.get("changes") or [],
            "next_question": validation["next_question"],
            "autonomy_level": "confirm_required",
            "version": FINN_STATE_VERSION,
        }

    def _strategy_reasoning(self, draft: Dict[str, Any], validation: Dict[str, Any]) -> Dict[str, Any]:
        reasons = []
        if validation["missing_fields"]:
            reasons.append(f"Ontbrekende velden: {', '.join(validation['missing_fields'])}")
        if validation["invalid_fields"]:
            reasons.append(f"Ongeldige velden: {', '.join(item['field'] for item in validation['invalid_fields'])}")
        if not reasons:
            reasons.append("Alle verplichte strategievelden zijn aanwezig en validatie is geslaagd.")
        return {
            "confidence_score": 0.9 if validation["can_confirm"] else 0.55,
            "risk_detected": bool(validation["invalid_fields"]),
            "reasons": reasons,
            "coaching_level": "strategy_creation",
        }

    def _strategy_action_id(self, payload: Dict[str, Any]) -> str:
        normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return f"finn-strategy-{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:24]}"

    def _is_new_bot_start_without_target(self, query: str) -> bool:
        q = (query or "").lower()
        if not re.search(r"\bbot\b", q):
            return False
        if re.search(r"\bstrateg(?:ie|y)\s*#?\s*\d+\b", q) or re.search(r"\bbot\s*#?\s*\d+\b", q):
            return False
        if any(word in q for word in ["pas", "wijzig", "update", "bijwerk", "bijwerken", "verander", "aanpassen"]):
            return False
        return any(word in q for word in ["maak", "aanmaken", "creeer", "creeër", "bouw", "instellen", "wil"])

    def _validate_bot_draft(self, draft: Dict[str, Any]) -> Dict[str, Any]:
        missing: List[str] = []
        invalid: List[Dict[str, str]] = []
        bot = draft.get("bot") or {}
        operation = draft.get("operation") or "create"
        if operation == "update" and not draft.get("bot_id"):
            missing.append("bot_id")
        if draft.get("_bot_lookup_error"):
            invalid.append({"field": "bot_id", "reason": draft["_bot_lookup_error"]})
        if not draft.get("strategy_id"):
            missing.append("strategy_id")
        if draft.get("_strategy_lookup_error"):
            invalid.append({"field": "strategy_id", "reason": draft["_strategy_lookup_error"]})
        if draft.get("strategy_id") and not bot.get("name"):
            missing.append("bot.name")

        mode = str(bot.get("mode") or "manual").lower()
        if mode not in {"manual", "semi-auto", "auto"}:
            invalid.append({"field": "bot.mode", "reason": "mode moet manual, semi-auto of auto zijn"})
        risk = str(bot.get("risk_profile") or "balanced").lower()
        if risk not in {"conservative", "balanced", "aggressive"}:
            invalid.append({"field": "bot.risk_profile", "reason": "risk_profile moet conservative, balanced of aggressive zijn"})
        cadence = str(bot.get("cadence") or "daily").lower()
        if cadence not in {"hourly", "daily", "weekly", "monthly"}:
            invalid.append({"field": "bot.cadence", "reason": "cadence moet hourly, daily, weekly of monthly zijn"})

        for field in ["budget_total_eur", "budget_daily_limit_eur", "budget_min_order_eur", "budget_max_order_eur"]:
            value = bot.get(field)
            if value is not None and (not isinstance(value, (int, float)) or value < 0):
                invalid.append({"field": f"bot.{field}", "reason": "budgetwaarde moet 0 of hoger zijn"})

        total = float(bot.get("budget_total_eur") or 0)
        daily = float(bot.get("budget_daily_limit_eur") or 0)
        min_order = float(bot.get("budget_min_order_eur") or 0)
        max_order = float(bot.get("budget_max_order_eur") or 0)
        if daily and total and daily > total:
            invalid.append({"field": "bot.budget_daily_limit_eur", "reason": "daglimiet mag niet hoger zijn dan totaal budget"})
        if min_order and max_order and min_order > max_order:
            invalid.append({"field": "bot.budget_min_order_eur", "reason": "min order mag niet hoger zijn dan max order"})
        if max_order and total and max_order > total:
            invalid.append({"field": "bot.budget_max_order_eur", "reason": "max order mag niet hoger zijn dan totaal budget"})

        if bool(bot.get("is_live")) or mode in {"semi-auto", "auto"}:
            for field, value in [
                ("bot.budget_total_eur", total),
                ("bot.budget_daily_limit_eur", daily),
                ("bot.budget_min_order_eur", min_order),
                ("bot.budget_max_order_eur", max_order),
            ]:
                if value <= 0:
                    missing.append(field)

        if bool(bot.get("is_live")):
            if not bot.get("live_trading_ack"):
                missing.append("bot.live_trading_ack")
            if draft.get("_live_exchange_ready") is False:
                invalid.append({"field": "bot.exchange_keys", "reason": "live bot vereist actieve exchange keys"})

        if operation == "update":
            draft["changes"] = self._bot_changes(draft)
            if not draft.get("changes") and not missing and not invalid:
                invalid.append({"field": "bot.changes", "reason": "geen wijzigingen gevonden om bij te werken"})

        next_question = missing[0] if missing else (invalid[0]["field"] if invalid else None)
        return {
            "missing_fields": missing,
            "invalid_fields": invalid,
            "next_question": next_question,
            "can_confirm": not missing and not invalid,
        }

    def _build_bot_message(self, draft: Dict[str, Any], validation: Dict[str, Any], strategy_options: Optional[List[Dict[str, Any]]] = None) -> str:
        next_question = validation["next_question"]
        if validation["invalid_fields"]:
            issue = validation["invalid_fields"][0]
            return f"Ik zie een probleem met {issue['field']}: {issue['reason']}."
        if next_question == "strategy_id":
            if strategy_options:
                lines = ["Welke strategie wil je aan deze bot koppelen? Kies bijvoorbeeld:"]
                for option in strategy_options:
                    lines.append(f"- strategy {option['id']}: {option.get('name')} ({option.get('symbol')} · {option.get('setup_type')} · {option.get('timeframe')})")
                return "\n".join(lines)
            return "Welke strategie moet deze bot uitvoeren? Geef bijvoorbeeld: strategy 114."
        if next_question == "bot.name":
            return "Welke naam wil je deze bot geven?"
        if next_question and next_question.startswith("bot.budget_"):
            return "Voor live of automatische bots heb ik expliciete budgetlimieten nodig: totaal budget, daglimiet, min order en max order."
        if next_question == "bot.live_trading_ack":
            return "Live trading kan echte orders plaatsen. Bevestig expliciet met: live akkoord."

        bot = draft.get("bot") or {}
        env = "live" if bot.get("is_live") else "paper"
        operation_label = "bijwerken" if draft.get("operation") == "update" else "aanmaken"
        change_lines = []
        if draft.get("operation") == "update":
            for change in draft.get("changes") or []:
                change_lines.append(f"- {change['field']}: {change.get('from')} -> {change.get('to')}")
            if not change_lines:
                change_lines.append("- Geen wijzigingen gevonden")
        return (
            f"Ik heb je bot klaarstaan om te {operation_label}. Controleer dit even en bevestig als het klopt:\n\n"
            f"- Bot: {bot.get('name')}\n"
            f"- Bot ID: {draft.get('bot_id') or 'nieuw'}\n"
            f"- Strategie: #{draft.get('strategy_id')}\n"
            f"- Omgeving: {env}\n"
            f"- Mode: {bot.get('mode')}\n"
            f"- Risk: {bot.get('risk_profile')}\n"
            f"- Cadence: {bot.get('cadence')}\n"
            f"- Budget: €{bot.get('budget_total_eur')} totaal, €{bot.get('budget_daily_limit_eur')} per dag"
            + (("\n\nWijzigingen:\n" + "\n".join(change_lines)) if draft.get("operation") == "update" else "")
        )

    def _bot_flow_state(self, draft: Dict[str, Any], validation: Dict[str, Any], strategy_options: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        return {
            "status": "ready_for_confirmation" if validation["can_confirm"] else "collecting",
            "current_flow": "bot_creation",
            "operation": draft.get("operation") or "create",
            "bot_id": draft.get("bot_id"),
            "strategy_id": draft.get("strategy_id"),
            "existing_bot_id": draft.get("existing_bot_id"),
            "asset": draft.get("asset"),
            "changes": draft.get("changes") or [],
            "strategy_options": strategy_options or [],
            "next_question": validation["next_question"],
            "autonomy_level": "confirm_required",
            "version": FINN_STATE_VERSION,
        }

    def _bot_reasoning(self, draft: Dict[str, Any], validation: Dict[str, Any]) -> Dict[str, Any]:
        reasons = []
        if validation["missing_fields"]:
            reasons.append(f"Ontbrekende velden: {', '.join(validation['missing_fields'])}")
        if validation["invalid_fields"]:
            reasons.append(f"Ongeldige velden: {', '.join(item['field'] for item in validation['invalid_fields'])}")
        if not reasons:
            reasons.append("Alle verplichte botvelden zijn aanwezig en validatie is geslaagd.")
        return {
            "confidence_score": 0.9 if validation["can_confirm"] else 0.55,
            "risk_detected": bool(validation["invalid_fields"]) or bool((draft.get("bot") or {}).get("is_live")),
            "reasons": reasons,
            "coaching_level": "bot_creation",
        }

    def _bot_action_id(self, payload: Dict[str, Any]) -> str:
        normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return f"finn-bot-{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:24]}"

    def _indicator_config_action_id(self, payload: Dict[str, Any]) -> str:
        normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return f"finn-indicator-{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:24]}"

    def _extract_indicator_score_mode(self, q_lower: str) -> Optional[str]:
        if any(word in q_lower for word in ["contrarian", "tegen de markt", "omgekeerd", "andersom", "inverse"]):
            return "contrarian"
        if any(word in q_lower for word in ["standard", "standaard", "normaal"]):
            return "standard"
        if any(word in q_lower for word in ["custom", "aangepast", "eigen regels"]):
            return "custom"
        return None

    def _extract_indicator_weight(self, q_lower: str) -> Optional[float]:
        match = re.search(r"(?:weight|weging|gewicht)\s*(?:van|naar|=|:)?\s*([0-9][0-9.,]*)", q_lower)
        if not match:
            return None
        try:
            return float(match.group(1).replace(",", "."))
        except ValueError:
            return None

    def _extract_indicator_name_hint(self, query: str, category: str) -> Optional[str]:
        q = (query or "").lower()
        aliases = {
            "bitcoin dominance": "btc_dominance",
            "btc dominance": "btc_dominance",
            "btc dominantie": "btc_dominance",
            "fear and greed": "fear_greed_index",
            "fear & greed": "fear_greed_index",
            "fear greed": "fear_greed_index",
            "dollar index": "dxy",
            "dxy": "dxy",
            "vix": "vix",
            "rsi": "rsi",
            "macd": "macd",
            "ema": "ema",
            "ma 200": "ma_200",
            "ma200": "ma_200",
        }
        for phrase, indicator in aliases.items():
            if re.search(rf"\b{re.escape(phrase)}\b", q):
                return indicator

        # Remove intent words and normalize the remaining short phrase. This is
        # only a hint; the DB lookup below remains the source of truth.
        cleaned = re.sub(
            r"\b(?:voeg|toe|toevoegen|aan|voor|met|op|als|naar|macro|technical|technisch|technische|indicator(?:en)?|node|score|scoring|configureer|config|gebruik|maak|zet|standard|standaard|contrarian|custom|weight|weging|gewicht|activeer|btc|eth|sol)\b|\b\d+(?:[.,]\d+)?\b",
            " ",
            q,
        )
        cleaned = re.sub(r"[^a-z0-9_&\s-]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not re.search(r"[a-z]", cleaned):
            return None
        if 2 <= len(cleaned) <= 60:
            return normalize_indicator_name(cleaned)
        return None

    async def _hydrate_indicator_config_draft(
        self,
        user_id: int,
        draft: Dict[str, Any],
        query: str = "",
        *,
        explicit_indicator_input: bool = False,
    ) -> None:
        if not self.session:
            return
        category = (draft.get("category") or "macro").lower()
        indicator = normalize_indicator_name(draft.get("indicator") or "") if draft.get("indicator") else None
        if indicator:
            exact = await self._find_indicator_exact(category, indicator)
            if exact:
                draft["indicator"] = exact["name"]
                draft["display_name"] = exact.get("display_name") or exact["name"]
                draft["indicator_options"] = []
                config_repository = IndicatorConfigRepository(self.session)
                config_service = IndicatorConfigService(config_repository)
                config = await config_service.get_indicator_config(category, exact["name"], user_id)
                _, has_user_override = await config_repository.get_indicator_rules(category, exact["name"], user_id)
                config_rules = [rule.dict() for rule in config.rules]
                node_active = await self._indicator_node_is_active(user_id, category, exact["name"], draft.get("symbol"))
                draft["existing_config_snapshot"] = {
                    "score_mode": config.score_mode or "standard",
                    "weight": float(config.weight or 1.0),
                    "rules": deepcopy(config_rules),
                    "node_active": node_active,
                    "has_user_override": bool(has_user_override),
                }
                draft["has_user_override"] = bool(has_user_override)
                if not draft.get("custom_rules_touched"):
                    draft["rules"] = config_rules
                if draft.get("operation") != "reset" and not draft.get("score_mode"):
                    draft["score_mode"] = config.score_mode or "standard"
                if draft.get("operation") != "reset" and draft.get("weight") is None:
                    draft["weight"] = float(config.weight or 1.0)
                draft["node_already_active"] = node_active
                if draft.get("operation") == "reset":
                    draft["changes"] = self._indicator_reset_changes_from_snapshot(draft)
                else:
                    draft["operation"] = "update" if (has_user_override or node_active) else "create"
                    draft["changes"] = self._indicator_config_changes_from_snapshot(draft)
                return

        options = await self._indicator_options(category, query or indicator or "")
        draft["indicator_options"] = options
        if indicator:
            if options:
                draft["indicator"] = None
                draft["display_name"] = None
            else:
                draft["_indicator_lookup_error"] = "indicator bestaat niet in de bestaande indicator registry"
        if not indicator and len(options) == 1 and explicit_indicator_input:
            draft["indicator"] = options[0]["name"]
            draft["display_name"] = options[0].get("display_name") or options[0]["name"]
            await self._hydrate_indicator_config_draft(user_id, draft, "")

    async def _find_indicator_exact(self, category: str, indicator: str) -> Optional[Dict[str, Any]]:
        result = await self.session.execute(text("""
            SELECT name, display_name, category
            FROM indicators
            WHERE category = :category
              AND active = TRUE
              AND lower(name) = lower(:indicator)
            LIMIT 1
        """), {"category": category, "indicator": indicator})
        row = result.mappings().first()
        return dict(row) if row else None

    async def _indicator_options(self, category: str, query: str) -> List[Dict[str, Any]]:
        raw = (query or "").lower()
        tokens = [
            normalize_indicator_name(token)
            for token in re.findall(r"[a-zA-Z0-9&]+", raw)
            if len(token) >= 2 and token.lower() not in {
                "voeg", "toe", "macro", "indicator", "indicatoren", "node",
                "score", "scoring", "standard", "standaard", "contrarian",
                "custom", "weight", "weging", "gewicht", "gebruik", "maak",
                "technical", "technisch", "technische", "reset", "herstel",
                "default", "terug", "naar", "config", "configureer",
                "als", "met", "voor", "op", "aan",
            }
        ]
        if not tokens:
            result = await self.session.execute(text("""
                SELECT name, display_name, category
                FROM indicators
                WHERE category = :category AND active = TRUE
                ORDER BY display_name ASC NULLS LAST, name ASC
                LIMIT 5
            """), {"category": category})
        else:
            like = f"%{'%'.join(tokens)}%"
            result = await self.session.execute(text("""
                SELECT name, display_name, category
                FROM indicators
                WHERE category = :category
                  AND active = TRUE
                  AND (
                    lower(name) LIKE lower(:like)
                    OR lower(coalesce(display_name, '')) LIKE lower(:like)
                  )
                ORDER BY display_name ASC NULLS LAST, name ASC
                LIMIT 5
            """), {"category": category, "like": like})
        return [dict(row) for row in result.mappings().all()]

    async def _indicator_node_is_active(self, user_id: int, category: str, indicator: str, symbol: Optional[str] = None) -> bool:
        if category == "macro":
            return await MacroDataService(self.session).repository.check_indicator_exists(user_id, indicator)
        if category == "technical":
            result = await self.session.execute(text("""
                SELECT COUNT(*) AS count
                FROM user_indicator_configs
                WHERE user_id = :user_id AND category = 'technical' AND indicator = :indicator
            """), {"user_id": user_id, "indicator": indicator})
            return int(result.scalar() or 0) > 0
        return False

    def _extract_indicator_custom_bucket_rules(self, query: str, current_rules: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        q = (query or "").lower()
        has_bucket_range = any(
            re.search(rf"\b0*{int(lo)}\s*(?:-|–|tot)\s*0*{int(hi)}\b", q)
            for lo, hi in INDICATOR_FIXED_BUCKETS
        )
        if "custom" not in q and not has_bucket_range:
            return None

        found: Dict[tuple, int] = {}
        for lo, hi in INDICATOR_FIXED_BUCKETS:
            lo_pattern = str(int(lo))
            hi_pattern = str(int(hi))
            match = re.search(
                rf"\b0*{lo_pattern}\s*(?:-|–|tot)\s*0*{hi_pattern}\b\s*(?:=|:|score|val|waarde|is|naar)?\s*([0-9]{{1,3}})",
                q,
            )
            if match:
                score = int(match.group(1))
                found[(lo, hi)] = max(10, min(100, score))

        if not found:
            return None

        by_bucket = {
            (round(float(rule.get("range_min", 0)), 4), round(float(rule.get("range_max", 0)), 4)): deepcopy(rule)
            for rule in (current_rules or [])
            if isinstance(rule, dict)
        }
        next_rules = []
        provided_buckets = []
        for lo, hi in INDICATOR_FIXED_BUCKETS:
            key = (round(lo, 4), round(hi, 4))
            rule = by_bucket.get(key) or {
                "range_min": lo,
                "range_max": hi,
                "score": 50,
                "trend": None,
                "interpretation": None,
                "action": None,
            }
            if (lo, hi) in found:
                rule["score"] = found[(lo, hi)]
                provided_buckets.append(f"{int(lo)}-{int(hi)}")
            next_rules.append(rule)
        return {
            "rules": next_rules,
            "provided_buckets": provided_buckets,
        }

    def _indicator_config_changes(self, current_config: Any, draft: Dict[str, Any]) -> List[Dict[str, Any]]:
        changes = []
        current_mode = getattr(current_config, "score_mode", None) or "standard"
        current_weight = float(getattr(current_config, "weight", 1.0) or 1.0)
        next_mode = draft.get("score_mode") or current_mode
        next_weight = float(draft.get("weight") if draft.get("weight") is not None else current_weight)
        if current_mode != next_mode:
            changes.append({"field": "score_mode", "from": current_mode, "to": next_mode})
        if round(current_weight, 8) != round(next_weight, 8):
            changes.append({"field": "weight", "from": current_weight, "to": next_weight})
        return changes

    def _indicator_config_changes_from_snapshot(self, draft: Dict[str, Any]) -> List[Dict[str, Any]]:
        snapshot = draft.get("existing_config_snapshot") if isinstance(draft.get("existing_config_snapshot"), dict) else {}
        if not snapshot:
            return []
        changes = []
        current_mode = snapshot.get("score_mode") or "standard"
        current_weight = float(snapshot.get("weight") or 1.0)
        next_mode = draft.get("score_mode") or current_mode
        next_weight = float(draft.get("weight") if draft.get("weight") is not None else current_weight)
        if current_mode != next_mode:
            changes.append({"field": "score_mode", "from": current_mode, "to": next_mode})
        if round(current_weight, 8) != round(next_weight, 8):
            changes.append({"field": "weight", "from": current_weight, "to": next_weight})
        current_node_active = bool(snapshot.get("node_active"))
        next_node_active = bool(draft.get("activate_node") or current_node_active)
        if current_node_active != next_node_active:
            changes.append({"field": "node_active", "from": current_node_active, "to": next_node_active})

        old_rules = snapshot.get("rules") if isinstance(snapshot.get("rules"), list) else []
        new_rules = draft.get("rules") if isinstance(draft.get("rules"), list) else []
        old_by_bucket = {
            (round(float(rule.get("range_min", 0)), 4), round(float(rule.get("range_max", 0)), 4)): rule.get("score")
            for rule in old_rules
            if isinstance(rule, dict)
        }
        for rule in new_rules:
            if not isinstance(rule, dict):
                continue
            key = (round(float(rule.get("range_min", 0)), 4), round(float(rule.get("range_max", 0)), 4))
            before = old_by_bucket.get(key)
            after = rule.get("score")
            if before is not None and int(float(before)) != int(float(after)):
                changes.append({
                    "field": f"bucket_{int(key[0])}_{int(key[1])}",
                    "from": int(float(before)),
                    "to": int(float(after)),
                })
        return changes

    def _indicator_reset_changes_from_snapshot(self, draft: Dict[str, Any]) -> List[Dict[str, Any]]:
        snapshot = draft.get("existing_config_snapshot") if isinstance(draft.get("existing_config_snapshot"), dict) else {}
        changes = []
        if snapshot.get("has_user_override"):
            changes.append({"field": "score_rules", "from": "user_override", "to": "template_default"})
        current_mode = snapshot.get("score_mode")
        if current_mode and current_mode != "standard":
            changes.append({"field": "score_mode", "from": current_mode, "to": "template"})
        current_weight = float(snapshot.get("weight") or 1.0)
        if round(current_weight, 8) != 1.0:
            changes.append({"field": "weight", "from": current_weight, "to": "template"})
        return changes

    def _validate_indicator_config_draft(self, draft: Dict[str, Any]) -> Dict[str, Any]:
        missing: List[str] = []
        invalid: List[Dict[str, str]] = []

        if draft.get("category") not in {"macro", "technical"}:
            invalid.append({"field": "category", "reason": "category moet macro of technical zijn"})
        if not draft.get("indicator"):
            missing.append("indicator")
        if draft.get("_indicator_lookup_error"):
            invalid.append({"field": "indicator", "reason": draft["_indicator_lookup_error"]})
        mode = draft.get("score_mode")
        if draft.get("operation") != "reset":
            if not mode:
                missing.append("score_mode")
            elif mode not in {"standard", "contrarian", "custom"}:
                invalid.append({"field": "score_mode", "reason": "score_mode moet standard, contrarian of custom zijn"})
        weight = draft.get("weight")
        if draft.get("operation") != "reset":
            if weight is None:
                missing.append("weight")
            elif not isinstance(weight, (int, float)) or float(weight) < 0 or float(weight) > 3:
                invalid.append({"field": "weight", "reason": "weight moet tussen 0.0 en 3.0 liggen"})
        if draft.get("operation") != "reset" and mode == "custom":
            rules = draft.get("rules") if isinstance(draft.get("rules"), list) else []
            if not draft.get("custom_rules_touched"):
                missing.append("rules")
            elif not draft.get("custom_rules_complete"):
                missing.append("rules")
            elif len(rules) != 5:
                invalid.append({"field": "rules", "reason": "custom rules moeten exact 5 vaste buckets bevatten"})
            else:
                expected = [(round(lo, 4), round(hi, 4)) for lo, hi in INDICATOR_FIXED_BUCKETS]
                actual = [
                    (round(float(rule.get("range_min", -1)), 4), round(float(rule.get("range_max", -1)), 4))
                    for rule in rules
                    if isinstance(rule, dict)
                ]
                if actual != expected:
                    invalid.append({"field": "rules", "reason": "custom buckets moeten exact 0-20, 20-40, 40-60, 60-80 en 80-100 zijn"})
                for rule in rules:
                    score = rule.get("score") if isinstance(rule, dict) else None
                    if not isinstance(score, (int, float)) or int(float(score)) < 10 or int(float(score)) > 100:
                        invalid.append({"field": "rules", "reason": "bucket-scores moeten tussen 10 en 100 liggen"})
                        break
        if draft.get("operation") != "reset" and draft.get("category") == "technical" and draft.get("activate_node") and not draft.get("symbol"):
            missing.append("symbol")

        next_question = missing[0] if missing else (invalid[0]["field"] if invalid else None)
        return {
            "missing_fields": missing,
            "invalid_fields": invalid,
            "next_question": next_question,
            "can_confirm": not missing and not invalid,
        }

    def _build_indicator_config_message(self, draft: Dict[str, Any], validation: Dict[str, Any]) -> str:
        if validation["invalid_fields"]:
            issue = validation["invalid_fields"][0]
            if issue["field"] == "rules":
                return "Custom scoring kan alleen met exact de bestaande 5 buckets. Geef alle bucket-scores door of kies standard/contrarian."
            return f"Ik zie een probleem met {issue['field']}: {issue['reason']}."
        if validation["next_question"] == "rules":
            missing = draft.get("missing_custom_buckets") or [f"{int(lo)}-{int(hi)}" for lo, hi in INDICATOR_FIXED_BUCKETS]
            return (
                "Voor custom scoring heb ik exact alle 5 vaste buckets nodig. "
                "Geef bijvoorbeeld: 0-20=10, 20-40=25, 40-60=50, 60-80=75, 80-100=100. "
                f"Ontbreekt nog: {', '.join(missing)}."
            )
        if validation["next_question"] == "indicator":
            options = draft.get("indicator_options") or []
            if options:
                category = draft.get("category") or "macro"
                lines = [f"Welke bestaande {category}-node bedoel je? Ik vind deze opties:"]
                for option in options:
                    lines.append(f"- {option.get('name')}: {option.get('display_name') or option.get('name')}")
                return "\n".join(lines)
            category = draft.get("category") or "macro"
            return f"Welke bestaande {category}-node wil je configureren? Bijvoorbeeld: btc_dominance, fear_greed_index of rsi."
        if validation["next_question"] == "score_mode":
            return "Wil je standard scoring of contrarian scoring gebruiken? Contrarian is voor situaties waarin lage waarden juist koopkans kunnen betekenen."
        if validation["next_question"] == "weight":
            return "Welke weight wil je deze macro-node geven? Gebruik 0.0 t/m 3.0."

        scores = [rule.get("score") for rule in (draft.get("rules") or [])]
        change_lines = [f"- {c['field']}: {c.get('from')} -> {c.get('to')}" for c in (draft.get("changes") or [])]
        operation_label = {
            "create": "Nieuwe indicator-config",
            "update": "Indicator-config bijwerken",
            "reset": "Reset naar standaard",
        }.get(draft.get("operation"), "Indicator-config bijwerken")
        if draft.get("operation") == "reset":
            return (
                "Ik heb deze reset klaarstaan. Ik verwijder alleen jouw user-overrides en val terug op de bestaande template-buckets:\n\n"
                f"- Actie: {operation_label}\n"
                f"- Node: {draft.get('display_name') or draft.get('indicator')} ({draft.get('indicator')})\n"
                + (f"- Asset: {draft.get('symbol')}\n" if draft.get("category") == "technical" and draft.get("symbol") else "")
                + f"- Categorie: {draft.get('category')}"
                + (("\n\nWijzigingen:\n" + "\n".join(change_lines)) if change_lines else "")
            )
        return (
            f"Ik heb deze {draft.get('category')}-config klaarstaan. Ik gebruik alleen de bestaande indicator-node en bestaande score-buckets:\n\n"
            f"- Actie: {operation_label}\n"
            f"- Node: {draft.get('display_name') or draft.get('indicator')} ({draft.get('indicator')})\n"
            + (f"- Asset: {draft.get('symbol')}\n" if draft.get("category") == "technical" else "")
            + f"- Mode: {draft.get('score_mode')}\n"
            f"- Weight: {draft.get('weight')}\n"
            f"- Buckets: {scores}\n"
            f"- Node activeren: {'ja' if draft.get('activate_node') else 'nee'}"
            + ("\n- Status: node is al actief; ik werk alleen de configuratie bij" if draft.get("node_already_active") else "")
            + (("\n\nWijzigingen:\n" + "\n".join(change_lines)) if change_lines else "")
        )

    def _indicator_config_flow_state(self, draft: Dict[str, Any], validation: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "ready_for_confirmation" if validation["can_confirm"] else "collecting",
            "current_flow": "indicator_config",
            "operation": draft.get("operation") or "configure",
            "category": draft.get("category"),
            "indicator": draft.get("indicator"),
            "display_name": draft.get("display_name"),
            "symbol": draft.get("symbol"),
            "score_mode": draft.get("score_mode"),
            "weight": draft.get("weight"),
            "indicator_options": draft.get("indicator_options") or [],
            "node_already_active": draft.get("node_already_active"),
            "has_user_override": draft.get("has_user_override"),
            "changes": draft.get("changes") or [],
            "next_question": validation["next_question"],
            "autonomy_level": "confirm_required",
            "version": FINN_STATE_VERSION,
        }

    def _indicator_config_reasoning(self, draft: Dict[str, Any], validation: Dict[str, Any]) -> Dict[str, Any]:
        reasons = []
        if validation["missing_fields"]:
            reasons.append(f"Ontbrekende velden: {', '.join(validation['missing_fields'])}")
        if validation["invalid_fields"]:
            reasons.append(f"Ongeldige velden: {', '.join(item['field'] for item in validation['invalid_fields'])}")
        if not reasons:
            reasons.append("Bestaande indicator, score-mode, weight en bucket-config zijn gevalideerd.")
        return {
            "confidence_score": 0.9 if validation["can_confirm"] else 0.55,
            "risk_detected": bool(validation["invalid_fields"]),
            "reasons": reasons,
            "coaching_level": "indicator_config",
        }

    def _validate_range(self, field: str, value: Any, invalid: List[Dict[str, str]]) -> None:
        if not isinstance(value, list) or len(value) != 2:
            invalid.append({"field": field, "reason": "range ontbreekt of heeft geen min/max"})
            return
        lo, hi = value
        if not isinstance(lo, int) or not isinstance(hi, int) or lo < 0 or hi > 100 or lo > hi:
            invalid.append({"field": field, "reason": "score range moet 0-100 zijn en min <= max"})

    def _validate(self, draft: Dict[str, Any]) -> Dict[str, Any]:
        missing: List[str] = []
        invalid: List[Dict[str, str]] = []
        clarification = draft.get("_clarification") if isinstance(draft.get("_clarification"), dict) else {}
        priority_question = clarification.get("field") if clarification else None

        if draft.get("plan_type") not in {"dca", "trade"}:
            missing.append("plan_type")
        if not draft.get("asset"):
            missing.append("asset")
        elif draft["asset"] not in SUPPORTED_ASSETS:
            invalid.append({"field": "asset", "reason": "asset wordt nog niet ondersteund"})
        if clarification.get("field") == "asset":
            invalid.append({"field": "asset", "reason": clarification.get("reason", "asset moet verduidelijkt worden")})
        if not draft["setup"].get("name"):
            missing.append("setup.name")
        if not draft["setup"].get("timeframe"):
            missing.append("setup.timeframe")

        self._validate_range("setup.macro_score_range", draft["setup"].get("macro_score_range"), invalid)
        self._validate_range("setup.technical_score_range", draft["setup"].get("technical_score_range"), invalid)
        self._validate_range("setup.market_score_range", draft["setup"].get("market_score_range"), invalid)

        if draft.get("plan_type") == "dca":
            frequency = draft["dca"].get("frequency")
            if frequency not in {"daily", "weekly", "monthly"}:
                missing.append("dca.frequency")
            if frequency == "weekly" and not draft["dca"].get("day"):
                missing.append("dca.day")
            if frequency == "monthly":
                month_day = draft["dca"].get("month_day")
                if month_day is None:
                    missing.append("dca.month_day")
                elif not isinstance(month_day, int) or month_day < 1 or month_day > 28:
                    invalid.append({"field": "dca.month_day", "reason": "gebruik dag 1 t/m 28 voor maandelijkse DCA"})

            if draft["dca"].get("dca_mode") == "custom":
                if draft["dca"].get("buy_score_threshold") is None:
                    missing.append("dca.buy_score_threshold")

        if draft.get("plan_type") == "trade":
            is_long_trade = draft["strategy"].get("direction") == "long"
            if not is_long_trade:
                invalid.append({
                    "field": "strategy.direction",
                    "reason": clarification.get("reason", "alleen long trades worden nu ondersteund")
                    if clarification.get("field") == "strategy.direction"
                    else "alleen long trades worden nu ondersteund",
                })
            if draft["strategy"].get("entry_type") not in {"limit", "breakout", "market"}:
                missing.append("strategy.entry_type")
            entry = draft["strategy"].get("entry")
            stop_loss = draft["strategy"].get("stop_loss")
            targets = draft["strategy"].get("targets")
            if entry is None:
                missing.append("strategy.entry")
            if stop_loss is None:
                missing.append("strategy.stop_loss")
            if not targets:
                missing.append("strategy.targets")
            if draft["bot"].get("create_bot") and not draft["bot"].get("risk_profile"):
                missing.append("bot.risk_profile")
            if is_long_trade and isinstance(entry, (int, float)) and isinstance(stop_loss, (int, float)):
                if stop_loss >= entry:
                    invalid.append({"field": "strategy.stop_loss", "reason": "voor long trades moet stop-loss lager zijn dan entry"})
            if is_long_trade and isinstance(entry, (int, float)) and isinstance(targets, list):
                bad_targets = [t for t in targets if isinstance(t, (int, float)) and t <= entry]
                if bad_targets:
                    invalid.append({"field": "strategy.targets", "reason": "voor long trades moeten targets boven entry liggen"})
                numeric_targets = [t for t in targets if isinstance(t, (int, float))]
                if len(numeric_targets) > 1 and any(numeric_targets[i] >= numeric_targets[i + 1] for i in range(len(numeric_targets) - 1)):
                    invalid.append({"field": "strategy.targets", "reason": "targets moeten oplopend zijn"})
                if isinstance(stop_loss, (int, float)) and stop_loss < entry:
                    risk = entry - stop_loss
                    reward = max(numeric_targets or [entry]) - entry
                    if risk > 0 and reward / risk < 1:
                        invalid.append({"field": "strategy.risk_reward", "reason": "risk/reward moet minimaal 1:1 zijn"})

        amount = draft["strategy"].get("base_amount_eur")
        if amount is None:
            missing.append("strategy.base_amount_eur")
        elif not isinstance(amount, (int, float)) or amount <= 0:
            invalid.append({"field": "strategy.base_amount_eur", "reason": "bedrag moet groter dan 0 zijn"})

        next_question = priority_question or (missing[0] if missing else (invalid[0]["field"] if invalid else None))
        return {
            "missing_fields": missing,
            "invalid_fields": invalid,
            "next_question": next_question,
            "can_confirm": not missing and not invalid,
        }

    def _build_message(self, draft: Dict[str, Any], validation: Dict[str, Any]) -> str:
        next_question = validation["next_question"]
        if next_question == "asset":
            return "Voor welk asset wil je dit plan maken? Ik ondersteun nu BTC, ETH en SOL."
        if validation["invalid_fields"]:
            issue = validation["invalid_fields"][0]
            return f"Ik zie een probleem met {issue['field']}: {issue['reason']}. Wat wil je hiervoor instellen?"

        if next_question == "plan_type":
            return "Bedoel je een DCA-plan om periodiek te accumuleren, of een trade-plan met entry, stop-loss en targets?"
        if next_question == "setup.timeframe":
            return "Welke timeframe hoort bij dit plan? Bijvoorbeeld 1W voor DCA of 4H/1D voor een trade."
        if next_question == "strategy.base_amount_eur":
            return "Met welk basisbedrag in euro wil je dit plan uitvoeren?"
        if next_question == "dca.frequency":
            return "Hoe vaak wil je deze DCA uitvoeren: dagelijks, wekelijks of maandelijks?"
        if next_question == "dca.day":
            return "Op welke weekdag wil je deze DCA uitvoeren?"
        if next_question == "dca.month_day":
            return "Op welke dag van de maand wil je kopen? Gebruik dag 1 t/m 28."
        if next_question == "dca.buy_score_threshold":
            return "Bij welke marktscore wil je extra bijkopen? (bijv. onder de 30)"
        if next_question == "strategy.entry":
            return "Welke entry-prijs hoort bij deze trade?"
        if next_question == "strategy.stop_loss":
            return "Welke stop-loss hoort bij deze trade?"
        if next_question == "strategy.targets":
            return "Welke target(s) wil je gebruiken? Je mag meerdere targets met komma's geven."
        if next_question == "bot.risk_profile":
            return "Welk risicoprofiel wil je hanteren voor deze trade? (conservative, balanced of aggressive)"

        summary = self._summary(draft)
        return f"Ik heb je plan klaarstaan. Controleer dit even en bevestig als het klopt:\n\n{summary}"

    def _asset_from_query_or_context(self, query: str, context: Optional[Dict[str, Any]] = None) -> str:
        q = (query or "").upper()
        for symbol in SUPPORTED_ASSETS:
            if re.search(rf"\b{symbol}\b", q):
                return symbol
        context = context or {}
        for key in ["symbol", "setup_symbol"]:
            value = context.get(key)
            if value and str(value).upper() in SUPPORTED_ASSETS:
                return str(value).upper()
        draft = context.get("finn_draft") if isinstance(context.get("finn_draft"), dict) else {}
        if draft.get("asset") in SUPPORTED_ASSETS:
            return draft["asset"]
        return "BTC"

    def _should_build_portfolio_daily_coach(self, query: str, context: Optional[Dict[str, Any]] = None) -> bool:
        q = (query or "").lower()
        if any(asset in SUPPORTED_ASSETS for asset in _asset_mentions(query)):
            return False
        if any(phrase in q for phrase in ["mijn btc setup", "mijn eth setup", "mijn sol setup"]):
            return False
        portfolio_phrases = [
            "daily brief",
            "briefing",
            "prioriteiten",
            "start mijn dag",
            "dagstart",
            "wat moet ik vandaag doen",
            "wat moet ik doen vandaag",
            "wat moet ik vandaag",
            "wat zijn mijn prioriteiten",
        ]
        return any(phrase in q for phrase in portfolio_phrases)

    async def _fetch_daily_scores_with_runtime_refresh(self, user_id: int, asset: str) -> Optional[Dict[str, Any]]:
        if not self.session:
            return None
        score_repo = ScoreRepository(self.session)
        scores = await score_repo.fetch_daily_scores(user_id, asset)
        if scores:
            return scores
        try:
            await ScoreService(score_repo).get_daily_scores(user_id, asset)
            return await score_repo.fetch_daily_scores(user_id, asset)
        except Exception:
            return scores

    async def _fetch_onboarding_status(self, user_id: int) -> Dict[str, bool]:
        if not self.session:
            return {}
        try:
            result = await self.session.execute(
                text("""
                    SELECT step_key, completed
                    FROM onboarding_steps
                    WHERE user_id = :user_id AND flow = 'default'
                """),
                {"user_id": user_id},
            )
            rows = {str(row["step_key"]): bool(row["completed"]) for row in result.mappings()}
            return {
                "has_market": rows.get("market", False),
                "has_macro": rows.get("macro", False),
                "has_technical": rows.get("technical", False),
                "has_setup": rows.get("setup", False),
                "has_strategy": rows.get("strategy", False),
                "onboarding_complete": all(rows.get(k, False) for k in ["market", "macro", "technical", "setup", "strategy"]),
            }
        except Exception:
            return {}

    def _indicator_insight_categories(self, q: str) -> List[str]:
        categories = []
        if any(word in q for word in ["macro", "macro score"]):
            categories.append("macro")
        if any(word in q for word in ["technical", "technisch", "technische", "technical score"]):
            categories.append("technical")
        if any(word in q for word in ["market", "markt", "market data", "marktdata", "market score"]):
            categories.append("market")
        return categories or ["macro", "technical", "market"]

    def _available_indicator_options(self, rows: Any) -> List[Dict[str, Any]]:
        options = []
        for row in rows or []:
            if isinstance(row, dict):
                name = row.get("name")
                display_name = row.get("display_name") or name
            else:
                name = getattr(row, "name", None)
                display_name = getattr(row, "display_name", None) or name
            if name:
                options.append({"name": str(name), "display_name": str(display_name or name)})
        return options

    def _indicator_name(self, row: Any, category: str) -> Optional[str]:
        if isinstance(row, dict):
            return row.get("indicator") or row.get("name")
        if category == "technical":
            return getattr(row, "indicator", None)
        return getattr(row, "name", None) or getattr(row, "indicator", None)

    def _indicator_value(self, row: Any, key: str, fallback: Any = None) -> Any:
        if isinstance(row, dict):
            return row.get(key, fallback)
        return getattr(row, key, fallback)

    def _to_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _build_indicator_entry(self, row: Any, category: str, configs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        name = self._indicator_name(row, category)
        normalized = normalize_indicator_name(name or "")
        config = configs.get(f"{category}:{normalized}", {})
        score = self._to_float(self._indicator_value(row, "score"))
        value = self._to_float(self._indicator_value(row, "value"))
        if value is None:
            value = self._to_float(self._indicator_value(row, "waarde"))
        interpretation = (
            self._indicator_value(row, "interpretation")
            or self._indicator_value(row, "uitleg")
            or self._indicator_value(row, "advies")
        )
        action = self._indicator_value(row, "action") or self._indicator_value(row, "advies")
        weight = config.get("weight")
        impact_score = score * float(weight) if score is not None and weight is not None else score
        return {
            "name": name,
            "normalized": normalized,
            "value": value,
            "score": score,
            "impact_score": impact_score,
            "trend": self._indicator_value(row, "trend"),
            "interpretation": interpretation,
            "action": action,
            "score_mode": config.get("score_mode", "unknown"),
            "weight": weight,
            "rules_count": config.get("rules_count", 0),
            "timestamp": str(self._indicator_value(row, "timestamp", "")),
        }

    def _category_top_contributors(self, daily_scores: Optional[Dict[str, Any]], category: str) -> List[Any]:
        return self._json_value((daily_scores or {}).get(f"{category}_top_contributors"), [])

    def _summarize_indicator_category(
        self,
        category: str,
        rows: List[Any],
        available: List[Dict[str, Any]],
        configs: Dict[str, Dict[str, Any]],
        daily_scores: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        indicators = [self._build_indicator_entry(row, category, configs) for row in rows or []]
        active_names = {entry["normalized"] for entry in indicators if entry.get("normalized")}
        missing = [
            item for item in available or []
            if normalize_indicator_name(item.get("name", "")) not in active_names
        ]
        weak = [entry for entry in indicators if entry.get("score") is not None and entry["score"] < 40]
        neutral = [entry for entry in indicators if entry.get("score") is not None and 40 <= entry["score"] <= 60]
        strong = [entry for entry in indicators if entry.get("score") is not None and entry["score"] > 60]
        heavy = [entry for entry in indicators if entry.get("weight") is not None and entry["weight"] >= 2.0]
        low_weight = [entry for entry in indicators if entry.get("weight") is not None and entry["weight"] <= 0.25]
        no_data = [entry for entry in indicators if entry.get("score") is None]
        by_impact = sorted(
            indicators,
            key=lambda item: abs((item.get("impact_score") or 0) - 50),
            reverse=True,
        )
        return {
            "category": category,
            "score": self._score_value(daily_scores, category),
            "interpretation": (daily_scores or {}).get(f"{category}_interpretation"),
            "top_contributors": self._category_top_contributors(daily_scores, category),
            "active_count": len(indicators),
            "available_count": len(available or []),
            "coverage_ratio": round((len(indicators) / len(available)) * 100, 1) if available else None,
            "indicators": indicators,
            "weak_indicators": weak,
            "neutral_indicators": neutral,
            "strong_indicators": strong,
            "heavy_weight_indicators": heavy,
            "low_weight_indicators": low_weight,
            "no_data_indicators": no_data,
            "unused_options": missing[:5],
            "impact_leaders": by_impact[:3],
        }

    def _build_indicator_insight_analysis(
        self,
        *,
        asset: str,
        categories: List[str],
        daily_scores: Optional[Dict[str, Any]],
        macro_rows: List[Any],
        technical_rows: List[Any],
        market_rows: List[Any],
        market_snapshot: Any,
        available: Dict[str, List[Dict[str, Any]]],
        configs: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        row_map = {"macro": macro_rows, "technical": technical_rows, "market": market_rows}
        category_summaries = {
            category: self._summarize_indicator_category(
                category,
                row_map.get(category, []),
                available.get(category, []),
                configs,
                daily_scores,
            )
            for category in categories
        }
        warnings = []
        suggestions = []
        for category, summary in category_summaries.items():
            if summary["active_count"] == 0:
                warnings.append(f"{category}: geen actieve indicator-data gevonden")
            if summary["weak_indicators"]:
                names = ", ".join(i["name"] for i in summary["weak_indicators"][:3])
                warnings.append(f"{category}: zwakke indicatoren: {names}")
            if summary["heavy_weight_indicators"]:
                names = ", ".join(i["name"] for i in summary["heavy_weight_indicators"][:3])
                suggestions.append(f"Controleer of de hoge weging bewust is voor {category}: {names}.")
            if summary["unused_options"]:
                names = ", ".join(i["display_name"] for i in summary["unused_options"][:3])
                suggestions.append(f"Je kunt {category} uitbreiden met: {names}.")
            if summary["active_count"] <= 1 and summary["available_count"] > 1:
                suggestions.append(f"Je {category}-laag is dun; met maar {summary['active_count']} actieve indicator is de score kwetsbaar.")

        market = None
        if market_snapshot:
            market = {
                "symbol": asset,
                "price": self._to_float(getattr(market_snapshot, "price", None)),
                "change_24h": self._to_float(getattr(market_snapshot, "change_24h", None)),
                "volume": self._to_float(getattr(market_snapshot, "volume", None)),
                "timestamp": str(getattr(market_snapshot, "timestamp", "")),
            }

        return {
            "asset": asset,
            "has_daily_scores": bool(daily_scores),
            "categories": category_summaries,
            "market_snapshot": market,
            "warnings": warnings,
            "suggestions": suggestions[:5],
            "suggested_actions": [
                "Vraag Finn om een ontbrekende indicator toe te voegen",
                "Vraag waarom een specifieke indicator laag scoort",
                "Vraag Finn om de scoring mode of weight te controleren",
            ],
        }

    def _indicator_insight_reasons(self, analysis: Dict[str, Any]) -> List[str]:
        reasons = []
        for category, summary in (analysis.get("categories") or {}).items():
            reasons.append(f"{category}: {summary.get('active_count')} actieve indicatoren, score {summary.get('score')}")
        reasons.extend((analysis.get("warnings") or [])[:3])
        return reasons or ["Geen indicator-data gevonden om uit te leggen."]

    def _indicator_insight_message(self, asset: str, analysis: Dict[str, Any]) -> str:
        if not analysis.get("has_daily_scores"):
            lines = [
                f"Ik kan de {asset} score nog niet volledig verklaren, omdat ik geen daily score van vandaag vind.",
                "Ik kan wel kijken welke indicator-data/configuratie al actief is.",
            ]
        else:
            lines = [f"Dit is wat Finn nu ziet voor {asset}, op basis van echte indicator-data en je huidige scoring-config."]

        for category, summary in (analysis.get("categories") or {}).items():
            score = summary.get("score")
            active_count = summary.get("active_count")
            available_count = summary.get("available_count")
            lines.append(f"\n{category.upper()}: score {score}, {active_count}/{available_count} indicatoren actief.")
            if summary.get("top_contributors"):
                preview = ", ".join(str(item) for item in summary["top_contributors"][:3])
                lines.append(f"- Belangrijkste contributors: {preview}")
            if summary.get("impact_leaders"):
                leaders = []
                for item in summary["impact_leaders"][:3]:
                    leaders.append(
                        f"{item.get('name')} score {item.get('score')} weight {item.get('weight')} mode {item.get('score_mode')}"
                    )
                lines.append(f"- Meeste impact: {'; '.join(leaders)}")
            if summary.get("weak_indicators"):
                names = ", ".join(f"{item.get('name')} ({item.get('score')})" for item in summary["weak_indicators"][:3])
                lines.append(f"- Trekt omlaag: {names}")
            if summary.get("heavy_weight_indicators"):
                names = ", ".join(f"{item.get('name')} (weight {item.get('weight')})" for item in summary["heavy_weight_indicators"][:3])
                lines.append(f"- Hoge weging: {names}")
            if summary.get("unused_options"):
                names = ", ".join(item.get("display_name") for item in summary["unused_options"][:3])
                lines.append(f"- Nog niet actief maar beschikbaar: {names}")
            if not summary.get("indicators"):
                lines.append("- Geen actieve indicator-data gevonden voor deze categorie.")

        if analysis.get("market_snapshot"):
            snap = analysis["market_snapshot"]
            lines.append(
                f"\nMARKET SNAPSHOT: {asset} prijs {snap.get('price')}, 24h change {snap.get('change_24h')}, volume {snap.get('volume')}."
            )

        suggestions = analysis.get("suggestions") or []
        if suggestions:
            lines.append("\nMogelijke bijsturing:")
            for suggestion in suggestions[:4]:
                lines.append(f"- {suggestion}")
        lines.append("\nIk pas niets automatisch aan. Als je iets wilt toevoegen of wijzigen, maak ik daar eerst een confirmable draft van.")
        return "\n".join(lines)

    def _build_daily_coach_analysis(
        self,
        *,
        asset: str,
        daily_scores: Optional[Dict[str, Any]],
        setup_analysis: Dict[str, Any],
        active_strategy: Dict[str, Any],
        bot_today: Dict[str, Any],
        indicator_analysis: Dict[str, Any],
        onboarding_status: Optional[Dict[str, bool]] = None,
    ) -> Dict[str, Any]:
        blockers = setup_analysis.get("blockers") or []
        decisions = bot_today.get("decisions") or []
        indicator_warnings = indicator_analysis.get("warnings") or []
        indicator_suggestions = indicator_analysis.get("suggestions") or []
        data_readiness = self._build_daily_data_readiness(
            daily_scores=daily_scores,
            indicator_analysis=indicator_analysis,
            onboarding_status=onboarding_status or {},
        )

        if not daily_scores:
            stance = "wait_for_scores"
        elif setup_analysis.get("is_active"):
            stance = "plan_is_active"
        else:
            stance = "wait_for_plan"

        reasons = []
        if not daily_scores:
            reasons.append(data_readiness.get("message") or "Geen daily scores beschikbaar; Finn mag geen actief/inactief oordeel verzinnen.")
        elif blockers:
            reasons.extend([
                f"{b.get('category')}: {b.get('score')} buiten range {b.get('range')}"
                for b in blockers[:3]
            ])
        else:
            reasons.append("Macro, technical en market vallen binnen de setup-ranges.")

        if active_strategy.get("active"):
            strategy = active_strategy.get("strategy") or {}
            reasons.append(f"Er is vandaag een actieve strategie: {strategy.get('name') or strategy.get('id')}.")
        else:
            reasons.append("Geen actieve DCA-strategie voor vandaag gevonden.")

        if decisions:
            reasons.append(f"Er staan {len(decisions)} bot-beslissing(en) voor vandaag.")
        else:
            reasons.append("Geen bot-beslissing voor vandaag gevonden.")

        suggested_actions = []
        if stance == "plan_is_active":
            suggested_actions.append("Volg je plan en check eventuele bot-proposal voordat je uitvoert.")
        elif stance == "wait_for_scores":
            suggested_actions.extend(data_readiness.get("suggested_actions") or [
                "Haal of genereer eerst daily scores voordat je een planbeslissing neemt."
            ])
        else:
            suggested_actions.append("Niet forceren: wacht tot de blocker-scores binnen je ranges vallen.")
        if indicator_suggestions:
            suggested_actions.extend(indicator_suggestions[:2])
        if not decisions:
            suggested_actions.append("Vraag Finn om een bot-decision te genereren als er een bot actief hoort te zijn.")

        return {
            "asset": asset,
            "date": datetime.utcnow().date().isoformat(),
            "has_scores": bool(daily_scores),
            "stance": stance,
            "setup": setup_analysis.get("setup"),
            "setup_active": bool(setup_analysis.get("is_active")),
            "setup_match_percentage": setup_analysis.get("match_percentage"),
            "blockers": blockers,
            "passed_checks": setup_analysis.get("passed_checks") or [],
            "active_strategy": active_strategy,
            "bot_today": {
                "decision_count": len(decisions),
                "decisions": decisions[:3],
                "error": bot_today.get("error"),
            },
            "indicator_summary": {
                "warnings": indicator_warnings,
                "suggestions": indicator_suggestions,
                "categories": indicator_analysis.get("categories") or {},
            },
            "data_readiness": data_readiness,
            "reasons": reasons,
            "suggested_actions": suggested_actions[:5],
        }

    def _build_daily_data_readiness(
        self,
        *,
        daily_scores: Optional[Dict[str, Any]],
        indicator_analysis: Dict[str, Any],
        onboarding_status: Dict[str, bool],
    ) -> Dict[str, Any]:
        categories = indicator_analysis.get("categories") or {}
        tracked = ["macro", "technical", "market"]
        config_gaps = [
            category for category in tracked
            if (categories.get(category) or {}).get("active_count", 0) == 0
        ]
        onboarding_gaps = [
            category for category in tracked
            if onboarding_status and onboarding_status.get(f"has_{category}") is False
        ]

        if daily_scores:
            status = "ready_with_gaps" if config_gaps else "ready"
            message = "Daily scores zijn beschikbaar."
        elif onboarding_gaps:
            status = "onboarding_incomplete"
            message = f"De daily score ontbreekt omdat je onboarding nog niet volledig is voor: {', '.join(onboarding_gaps)}."
        elif config_gaps:
            status = "indicator_config_missing"
            message = f"De daily score ontbreekt en deze datalagen zijn nog niet actief ingericht: {', '.join(config_gaps)}."
        else:
            status = "score_generation_missing"
            message = "De configuratie lijkt aanwezig, maar de daily score is nog niet gegenereerd."

        suggested_actions = []
        if onboarding_gaps:
            suggested_actions.append(f"Rond eerst deze onboarding-stappen af: {', '.join(onboarding_gaps)}.")
        if "macro" in config_gaps:
            suggested_actions.append("Laat Finn een macro-indicator toevoegen, bijvoorbeeld Bitcoin Dominance of Fear & Greed.")
        if "technical" in config_gaps:
            suggested_actions.append("Laat Finn een technical indicator toevoegen, bijvoorbeeld RSI of 200-day Moving Average.")
        if "market" in config_gaps:
            suggested_actions.append("Richt market data in of ververs de market score voor dit asset.")
        if not daily_scores and not onboarding_gaps and not config_gaps:
            suggested_actions.append("Genereer daily scores opnieuw voordat je een planbeslissing neemt.")

        return {
            "status": status,
            "message": message,
            "onboarding_gaps": onboarding_gaps,
            "config_gaps": config_gaps,
            "onboarding_status": onboarding_status,
            "suggested_actions": suggested_actions[:4],
        }

    def _build_portfolio_daily_coach_analysis(self, asset_analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
        ranked = sorted(asset_analyses, key=self._portfolio_priority_sort_key)
        actionable_assets = [a for a in ranked if a.get("stance") == "plan_is_active"]
        blocked_assets = [a for a in ranked if a.get("stance") == "wait_for_plan"]
        scoreless_assets = [a for a in ranked if a.get("stance") == "wait_for_scores"]
        warning_assets = [
            a for a in ranked
            if (a.get("indicator_summary") or {}).get("warnings")
        ]

        top_priorities = []
        for item in ranked[:5]:
            asset = item.get("asset")
            if item.get("stance") == "plan_is_active":
                label = "nu doen"
                reason = "plan actief volgens je score-ranges"
            elif item.get("stance") == "wait_for_plan":
                label = "niet forceren"
                blocker = (item.get("blockers") or [{}])[0]
                reason = f"{blocker.get('category')} blokkeert" if blocker.get("category") else "setup niet actief"
            else:
                label = "eerst data"
                reason = "daily scores ontbreken"
            top_priorities.append({
                "asset": asset,
                "priority": label,
                "reason": reason,
                "setup": item.get("setup"),
                "stance": item.get("stance"),
                "bot_decision_count": (item.get("bot_today") or {}).get("decision_count", 0),
                "warnings": ((item.get("indicator_summary") or {}).get("warnings") or [])[:2],
            })

        suggested_actions = []
        if actionable_assets:
            assets = ", ".join(a.get("asset") for a in actionable_assets[:3])
            suggested_actions.append(f"Review eerst de actieve plan-assets: {assets}.")
        if blocked_assets:
            first = blocked_assets[0]
            blocker = (first.get("blockers") or [{}])[0]
            suggested_actions.append(
                f"Forceer {first.get('asset')} niet: {blocker.get('category', 'score')} blokkeert nog."
            )
        if scoreless_assets:
            assets = ", ".join(a.get("asset") for a in scoreless_assets[:3])
            suggested_actions.append(f"Genereer of ververs daily scores voor: {assets}.")
        if warning_assets:
            first = warning_assets[0]
            warning = ((first.get("indicator_summary") or {}).get("warnings") or ["indicator coverage is dun"])[0]
            suggested_actions.append(f"Verbeter data-dekking voor {first.get('asset')}: {warning}")
        if not asset_analyses:
            suggested_actions.append("Maak eerst een setup aan; daarna kan Finn echte portfolio-prioriteiten bepalen.")

        reasons = []
        if not asset_analyses:
            reasons.append("Geen opgeslagen setups gevonden voor portfolio-briefing.")
        else:
            reasons.append(f"{len(asset_analyses)} setup-assets gecontroleerd.")
            reasons.append(f"{len(actionable_assets)} actief, {len(blocked_assets)} geblokkeerd, {len(scoreless_assets)} zonder daily scores.")

        return {
            "scope": "portfolio",
            "date": datetime.utcnow().date().isoformat(),
            "asset_count": len(asset_analyses),
            "has_any_scores": any(a.get("has_scores") for a in asset_analyses),
            "actionable_assets": actionable_assets,
            "blocked_assets": blocked_assets,
            "scoreless_assets": scoreless_assets,
            "warning_assets": warning_assets,
            "top_priorities": top_priorities,
            "assets": ranked,
            "reasons": reasons,
            "suggested_actions": suggested_actions[:5],
        }

    def _portfolio_priority_sort_key(self, analysis: Dict[str, Any]) -> tuple:
        stance_rank = {
            "plan_is_active": 0,
            "wait_for_plan": 1,
            "wait_for_scores": 2,
        }.get(analysis.get("stance"), 3)
        warning_count = len((analysis.get("indicator_summary") or {}).get("warnings") or [])
        blocker_count = len(analysis.get("blockers") or [])
        bot_count = (analysis.get("bot_today") or {}).get("decision_count", 0)
        return (stance_rank, -bot_count, -blocker_count, -warning_count, str(analysis.get("asset") or ""))

    def _daily_coach_message(self, analysis: Dict[str, Any]) -> str:
        asset = analysis.get("asset") or "BTC"
        stance = analysis.get("stance")
        if stance == "plan_is_active":
            headline = f"Voor {asset}: je plan mag vandaag actief zijn, zolang je je eigen execution-regels volgt."
        elif stance == "wait_for_scores":
            headline = f"Voor {asset}: ik zou nog geen planbeslissing nemen, omdat de daily scores ontbreken."
        else:
            headline = f"Voor {asset}: ik zou vandaag wachten; je setup is nog niet actief volgens je eigen ranges."

        lines = [headline]
        setup = analysis.get("setup") or {}
        if setup:
            lines.append(
                f"Setup: {setup.get('name')} (#{setup.get('id')}) - match {analysis.get('setup_match_percentage')}%."
            )

        blockers = analysis.get("blockers") or []
        if blockers:
            lines.append("Blokkeert nu:")
            for blocker in blockers[:3]:
                lines.append(
                    f"- {blocker.get('category')}: score {blocker.get('score')} moet binnen {blocker.get('range')} vallen"
                )
        elif analysis.get("has_scores"):
            lines.append("Geen score-blockers gevonden: macro, technical en market passen bij je setup.")

        active_strategy = analysis.get("active_strategy") or {}
        if active_strategy.get("active"):
            strategy = active_strategy.get("strategy") or {}
            lines.append(f"Strategie vandaag: actief ({strategy.get('name') or strategy.get('id')}).")
        else:
            lines.append("Strategie vandaag: geen actieve DCA-strategie gevonden.")

        bot_today = analysis.get("bot_today") or {}
        lines.append(f"Bot vandaag: {bot_today.get('decision_count', 0)} beslissing(en).")
        for decision in bot_today.get("decisions") or []:
            lines.append(
                f"- Bot #{decision.get('bot_id')}: {decision.get('action')} status {decision.get('status')}"
            )

        indicator_summary = analysis.get("indicator_summary") or {}
        warnings = indicator_summary.get("warnings") or []
        if warnings:
            lines.append("Data/indicator aandacht:")
            for warning in warnings[:3]:
                lines.append(f"- {warning}")

        readiness = analysis.get("data_readiness") or {}
        readiness_gaps = (readiness.get("onboarding_gaps") or []) + (readiness.get("config_gaps") or [])
        if readiness_gaps:
            lines.append("Datakwaliteit:")
            lines.append(f"- {readiness.get('message')}")

        actions = analysis.get("suggested_actions") or []
        if actions:
            lines.append("Veilige volgende stap:")
            for action in actions[:4]:
                lines.append(f"- {action}")

        lines.append("Ik voer niets automatisch uit vanuit deze check; dit is advies-only.")
        return "\n".join(lines)

    def _portfolio_daily_coach_message(self, analysis: Dict[str, Any]) -> str:
        asset_count = analysis.get("asset_count", 0)
        if not asset_count:
            return (
                "Ik kan je portfolio-dagbrief nog niet betrouwbaar maken, omdat ik nog geen opgeslagen setups vind.\n"
                "Topprioriteit: maak eerst een setup aan. Daarna kan ik per asset beoordelen wat actief, geblokkeerd of incompleet is.\n"
                "Ik voer niets automatisch uit vanuit deze briefing; dit is advies-only."
            )

        active_count = len(analysis.get("actionable_assets") or [])
        blocked_count = len(analysis.get("blocked_assets") or [])
        scoreless_count = len(analysis.get("scoreless_assets") or [])
        lines = [
            f"Portfolio daily brief: ik heb {asset_count} setup-assets gecontroleerd.",
            f"Status: {active_count} actief, {blocked_count} geblokkeerd, {scoreless_count} zonder daily scores.",
        ]

        priorities = analysis.get("top_priorities") or []
        if priorities:
            lines.append("Topprioriteiten vandaag:")
            for index, item in enumerate(priorities[:3], start=1):
                setup = item.get("setup") or {}
                setup_name = setup.get("name") or f"{item.get('asset')} setup"
                lines.append(
                    f"{index}. {item.get('asset')}: {item.get('priority')} - {item.get('reason')} ({setup_name})."
                )
                for warning in item.get("warnings") or []:
                    lines.append(f"   - Data-aandacht: {warning}")

        actions = analysis.get("suggested_actions") or []
        if actions:
            lines.append("Veilige volgende stappen:")
            for action in actions[:4]:
                lines.append(f"- {action}")

        lines.append("Ik voer niets automatisch uit vanuit deze portfolio-briefing; dit is advies-only.")
        return "\n".join(lines)

    def _score_value(self, daily_scores: Optional[Dict[str, Any]], key: str) -> Optional[float]:
        if not daily_scores:
            return None
        value = daily_scores.get(f"{key}_score")
        return float(value) if value is not None else None

    def _json_value(self, value: Any, fallback: Any) -> Any:
        if value is None:
            return fallback
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return fallback
        return fallback

    def _in_range(self, score: Optional[float], score_range: Optional[List[float]]) -> Optional[bool]:
        if score is None or not score_range:
            return None
        return score_range[0] <= score <= score_range[1]

    def _score_range_from_values(self, minimum: Any, maximum: Any) -> Optional[List[float]]:
        if minimum is None or maximum is None:
            return None
        try:
            return [float(minimum), float(maximum)]
        except (TypeError, ValueError):
            return None

    def _score_check(
        self,
        label: str,
        score: Optional[float],
        score_range: Optional[List[float]],
        daily_scores: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        interpretation = (daily_scores or {}).get(f"{label}_interpretation")
        contributors = self._json_value((daily_scores or {}).get(f"{label}_top_contributors"), [])
        passed = self._in_range(score, score_range)
        check = {
            "score": score,
            "range": score_range,
            "pass": passed,
            "interpretation": interpretation,
            "top_contributors": contributors,
        }
        if passed is False:
            check["blocker_reason"] = f"{label} score {score} valt buiten je range {score_range}"
        if passed is None:
            check["blocker_reason"] = f"{label} score of range ontbreekt"
        return check

    def _finalize_score_analysis(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        checks = analysis.get("checks") or {}
        known = [check.get("pass") for check in checks.values() if check.get("pass") is not None]
        failed = [
            {"category": label, **check}
            for label, check in checks.items()
            if check.get("pass") is False
        ]
        passed = [
            {"category": label, **check}
            for label, check in checks.items()
            if check.get("pass") is True
        ]
        missing = [
            {"category": label, **check}
            for label, check in checks.items()
            if check.get("pass") is None
        ]
        analysis["blockers"] = failed
        analysis["passed_checks"] = passed
        analysis["missing_checks"] = missing
        analysis["match_percentage"] = round((len(passed) / len(checks)) * 100, 1) if checks else 0.0
        analysis["is_active"] = bool(known) and len(known) == len(checks) and not failed
        analysis["confidence"] = "medium" if len(known) == len(checks) and analysis.get("has_scores") else "low"
        return analysis

    def _evaluate_draft_against_scores(
        self,
        draft: Dict[str, Any],
        daily_scores: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        setup = draft.get("setup") or {}
        checks = {
            "macro": self._score_check("macro", self._score_value(daily_scores, "macro"), setup.get("macro_score_range"), daily_scores),
            "technical": self._score_check("technical", self._score_value(daily_scores, "technical"), setup.get("technical_score_range"), daily_scores),
            "market": self._score_check("market", self._score_value(daily_scores, "market"), setup.get("market_score_range"), daily_scores),
        }
        return self._finalize_score_analysis({
            "checks": checks,
            "has_scores": bool(daily_scores),
            "source": "draft",
        })

    def _evaluate_setup_row(
        self,
        setup: Optional[Dict[str, Any]],
        daily_scores: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not setup:
            return {
                "is_active": False,
                "confidence": "low",
                "checks": {},
                "has_scores": bool(daily_scores),
                "reason": "Ik vond nog geen opgeslagen setup voor dit asset.",
            }
        checks = {
            "macro": self._score_check(
                "macro",
                self._score_value(daily_scores, "macro"),
                self._score_range_from_values(setup.get("min_macro_score"), setup.get("max_macro_score")),
                daily_scores,
            ),
            "technical": self._score_check(
                "technical",
                self._score_value(daily_scores, "technical"),
                self._score_range_from_values(setup.get("min_technical_score"), setup.get("max_technical_score")),
                daily_scores,
            ),
            "market": self._score_check(
                "market",
                self._score_value(daily_scores, "market"),
                self._score_range_from_values(setup.get("min_market_score"), setup.get("max_market_score")),
                daily_scores,
            ),
        }
        return self._finalize_score_analysis({
            "checks": checks,
            "has_scores": bool(daily_scores),
            "setup": {
                "id": setup.get("id"),
                "name": setup.get("name"),
                "type": setup.get("setup_type"),
                "timeframe": setup.get("timeframe"),
                "score": float(setup.get("score") or 0),
                "stored_is_active": bool(setup.get("is_active")),
            },
            "source": "saved_setup",
        })

    def _analysis_reasons(self, analysis: Dict[str, Any]) -> List[str]:
        if analysis.get("reason"):
            return [analysis["reason"]]
        blockers = analysis.get("blockers") or []
        if blockers:
            return [
                f"{blocker.get('category')}: {blocker.get('score')} buiten range {blocker.get('range')}"
                for blocker in blockers
            ]
        checks = analysis.get("checks") or {}
        if isinstance(checks, dict) and all(label in checks for label in ["macro", "technical", "market"]):
            reasons = []
            for label in ["macro", "technical", "market"]:
                check = checks.get(label) or {}
                status = "binnen range" if check.get("pass") else "buiten range"
                reasons.append(f"{label}: {check.get('score')} is {status}")
            return reasons
        setup = analysis.get("setup")
        if setup:
            return [f"Setup-score: {setup.get('score')}"]
        return ["Onvoldoende scoredata voor betrouwbare uitleg."]

    def _status_message(self, asset: str, analysis: Dict[str, Any], source: str) -> str:
        if not analysis.get("has_scores"):
            return (
                f"Ik kan nog niet betrouwbaar zeggen of {asset} actief is, omdat ik geen scores van vandaag vind. "
                "Zodra macro, technical en market scores beschikbaar zijn kan ik dit onderbouwen."
            )

        active_text = "actief" if analysis.get("is_active") else "niet actief"
        checks = analysis.get("checks") or {}
        blockers = analysis.get("blockers") or []
        passed_checks = analysis.get("passed_checks") or []
        match_percentage = analysis.get("match_percentage")

        if source == "draft":
            lines = [
                f"Je conceptplan voor {asset} is nu {active_text} op basis van de huidige scores.",
                f"Match met je plan: {match_percentage}%.",
            ]
            if blockers:
                lines.append("Blokkeert nu:")
                for blocker in blockers:
                    lines.append(
                        f"- {blocker.get('category')}: score {blocker.get('score')} moet binnen {blocker.get('range')} vallen"
                    )
            else:
                lines.append("Geen score-blockers: macro, technical en market vallen binnen je ingestelde ranges.")
            if passed_checks:
                lines.append("Binnen plan:")
                for check in passed_checks:
                    lines.append(f"- {check.get('category')}: {check.get('score')} binnen {check.get('range')}")
            for label in ["macro", "technical", "market"]:
                check = checks.get(label) or {}
                contributors = check.get("top_contributors") or []
                if contributors:
                    preview = ", ".join(str(item) for item in contributors[:2])
                    lines.append(f"- Belangrijkste {label}-signalen: {preview}")
            return "\n".join(lines)

        setup = analysis.get("setup")
        if not setup:
            return analysis.get("reason") or f"Ik vond geen actieve {asset} setup."
        lines = [
            f"Je opgeslagen setup '{setup.get('name')}' voor {asset} is nu {active_text} op basis van je eigen ranges.",
            f"Setup #{setup.get('id')} - {setup.get('type') or 'setup'} - timeframe {setup.get('timeframe') or 'n.v.t.'}.",
            f"Match met je plan: {match_percentage}%. Setup-score: {setup.get('score')}.",
        ]
        if blockers:
            lines.append("Blokkeert nu:")
            for blocker in blockers:
                lines.append(
                    f"- {blocker.get('category')}: score {blocker.get('score')} moet binnen {blocker.get('range')} vallen"
                )
        else:
            lines.append("Geen score-blockers: macro, technical en market vallen binnen je setup-ranges.")
        if passed_checks:
            lines.append("Binnen plan:")
            for check in passed_checks:
                lines.append(f"- {check.get('category')}: {check.get('score')} binnen {check.get('range')}")
        lines.append("Gebruik dit als plan-check, niet als losse emotionele trigger.")
        return "\n".join(lines)

    def _summary(self, draft: Dict[str, Any]) -> str:
        lines = [
            f"- Type: {draft.get('plan_type')}",
            f"- Asset: {draft.get('asset')}",
            f"- Naam: {draft['setup'].get('name')}",
            f"- Timeframe: {draft['setup'].get('timeframe')}",
            f"- Bedrag: €{draft['strategy'].get('base_amount_eur')}",
            f"- Macro: {draft['setup'].get('macro_score_range')}",
            f"- Technical: {draft['setup'].get('technical_score_range')}",
            f"- Market: {draft['setup'].get('market_score_range')}",
        ]
        if draft.get("plan_type") == "dca":
            lines.append(f"- DCA: {draft['dca'].get('frequency')} {draft['dca'].get('day') or draft['dca'].get('month_day') or ''}".strip())
        if draft.get("plan_type") == "trade":
            lines.extend([
                f"- Uitvoering: {draft['strategy'].get('entry_type')}",
                f"- Entry: {draft['strategy'].get('entry')}",
                f"- Stop-loss: {draft['strategy'].get('stop_loss')}",
                f"- Targets: {draft['strategy'].get('targets')}",
            ])
        lines.append(f"- Automatisering: {draft['bot'].get('automation') or ('bot_assisted' if draft['bot'].get('create_bot') else 'manual_only')}")
        if draft["bot"].get("create_bot"):
            env = "live" if draft["bot"].get("is_live") else "paper"
            lines.append(f"- Bot: {env}, {draft['bot'].get('mode')}, {draft['bot'].get('risk_profile')}")
        return "\n".join(lines)

    async def execute_action(self, user_id: int, action: Dict[str, Any]) -> Dict[str, Any]:
        if action and action.get("type") == "configure_indicator":
            return await self._execute_indicator_config_action(user_id, action)
        if action and action.get("type") == "create_bot":
            return await self._execute_bot_action(user_id, action)
        if action and action.get("type") == "create_strategy":
            return await self._execute_strategy_action(user_id, action)
        if not action or action.get("type") != "create_plan":
            raise HTTPException(400, "Onbekende Finn action")

        draft = _deep_merge(empty_plan_draft(), action.get("payload") or {})
        self._apply_defaults(draft)
        action_id = f"{action.get('id') or self._action_id(draft)}-u{user_id}"
        acquired = await self._try_create_pending_action(user_id, action_id, action)
        if not acquired:
            existing_result = await self._wait_for_action_result(user_id, action_id)
            if existing_result:
                return existing_result
            raise HTTPException(409, "Deze Finn actie wordt al verwerkt. Probeer zo opnieuw.")

        validation = self._validate(draft)
        if not validation["can_confirm"]:
            await self._upsert_action_audit(user_id, action_id, action, status="failed", result={
                "ok": False,
                "message": "Plan is nog niet geldig",
                "missing_fields": validation["missing_fields"],
                "invalid_fields": validation["invalid_fields"],
            })
            raise HTTPException(422, {
                "message": "Plan is nog niet geldig",
                "missing_fields": validation["missing_fields"],
                "invalid_fields": validation["invalid_fields"],
            })

        # Step 9: Autonomie Levels
        from backend.infrastructure.models import User
        from sqlalchemy import select
        
        result = await self.session.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        preferences = getattr(user, "ai_preferences", {}) or {}
        autonomy_level = preferences.get("autonomy_level", 2) # Default to level 2
        
        if autonomy_level < 2:
            raise HTTPException(403, f"Jouw autonomie-level ({autonomy_level}) staat het automatisch aanmaken van plannen niet toe.")
            
        if autonomy_level < 3 and draft["bot"].get("is_live"):
            raise HTTPException(403, f"Jouw autonomie-level ({autonomy_level}) staat het aanmaken van LIVE bots niet toe. Pas dit aan in je profiel.")

        # Step 10: Guardrails
        from backend.infrastructure.repositories.bot_repository import BotRepository
        bot_repo = BotRepository(self.session)
        portfolio_ctx = await bot_repo.get_portfolio_intelligence_context(user_id)
        
        # Guardrail 1: Max open trades (bots)
        active_bots = [b for b in portfolio_ctx["bots"] if b["is_active"]]
        if len(active_bots) >= 5:
            raise HTTPException(403, f"Guardrail geschonden: Je hebt al het maximale aantal actieve bots (5).")
            
        # Guardrail 2: Max exposure per asset (20%)
        allocations = portfolio_ctx["global"]["allocations_pct"]
        asset = draft.get("asset")
        current_alloc = allocations.get(asset, 0.0)
        if current_alloc > 20.0:
            raise HTTPException(403, f"Guardrail geschonden: Je hebt al {current_alloc}% exposure in {asset} (max 20%).")

        setup_service = SetupService(self.session)
        strategy_service = StrategyService(self.session)
        bot_service = BotService(self.session)
        setup_id = None
        strategy_id = None
        bot_id = None

        try:
            draft["setup"]["name"] = await self._unique_setup_name(setup_service, draft["setup"]["name"], user_id)
            setup_payload = self._setup_payload(draft)
            setup_result = await setup_service.save_setup(
                SetupCreateSchema(**setup_payload),
                setup_payload,
                user_id,
            )
            setup_id = setup_result["setup_id"]

            strategy_payload = self._strategy_payload(draft, setup_id)
            strategy_result = await strategy_service.save_strategy(
                StrategyCreateSchema(**strategy_payload),
                strategy_payload,
                user_id,
            )
            strategy_id = strategy_result["id"]

            if draft["bot"].get("create_bot"):
                bot_payload = self._bot_payload(draft, strategy_id)
                bot_result = await bot_service.create_bot_config(BotConfigCreateSchema(**bot_payload), user_id)
                bot_id = bot_result.get("id")

            verified = await self._verify_created_objects(user_id, setup_id, strategy_id, bot_id)
        except Exception:
            await self.session.rollback()
            await self._cleanup_created(user_id, setup_id=setup_id, strategy_id=strategy_id, bot_id=bot_id)
            await self._upsert_action_audit(
                user_id,
                action_id,
                action,
                status="failed",
                result={
                    "ok": False,
                    "setup_id": setup_id,
                    "strategy_id": strategy_id,
                    "bot_id": bot_id,
                },
            )
            raise

        result = {
            "ok": True,
            "message": "Plan aangemaakt",
            "setup_id": setup_id,
            "strategy_id": strategy_id,
            "bot_id": bot_id,
            "draft": draft,
            "action_id": action_id,
            "verified": verified,
        }
        await self._upsert_action_audit(user_id, action_id, action, status="executed", result=result)
        await self._log_intelligence_event(user_id, draft, result)
        await self.clear_state(user_id)
        return result

    async def _execute_bot_action(self, user_id: int, action: Dict[str, Any]) -> Dict[str, Any]:
        draft = _deep_merge(empty_bot_draft(), action.get("payload") or {})
        action_id = f"{action.get('id') or self._bot_action_id(draft)}-u{user_id}"
        acquired = await self._try_create_pending_action(user_id, action_id, action)
        if not acquired:
            existing_result = await self._wait_for_action_result(user_id, action_id)
            if existing_result:
                return existing_result
            raise HTTPException(409, "Deze Finn actie wordt al verwerkt. Probeer zo opnieuw.")

        await self._hydrate_existing_bot_draft_from_db(user_id, draft)
        await self._hydrate_bot_draft_from_db(user_id, draft)
        await self._apply_live_bot_preflight(user_id, draft)
        validation = self._validate_bot_draft(draft)
        if not validation["can_confirm"]:
            await self._upsert_action_audit(user_id, action_id, action, status="failed", result={
                "ok": False,
                "message": "Bot is nog niet geldig",
                "missing_fields": validation["missing_fields"],
                "invalid_fields": validation["invalid_fields"],
            })
            raise HTTPException(422, {
                "message": "Bot is nog niet geldig",
                "missing_fields": validation["missing_fields"],
                "invalid_fields": validation["invalid_fields"],
            })

        existing_bot = await self._existing_bot_for_strategy(user_id, draft.get("strategy_id"))
        if existing_bot and draft.get("operation") != "update":
            result = {
                "ok": True,
                "message": "Bot bestaat al",
                "bot_id": existing_bot.get("id"),
                "strategy_id": draft.get("strategy_id"),
                "draft": draft,
                "action_id": action_id,
                "verified": {"bot": True},
            }
            await self._upsert_action_audit(user_id, action_id, action, status="executed", result=result)
            await self.clear_state(user_id)
            return result

        bot_id = None
        try:
            bot_service = BotService(self.session)
            if draft.get("operation") == "update":
                bot_id = int(draft["bot_id"])
                bot_payload = self._bot_update_payload(draft)
                bot_result = await bot_service.update_bot_config(bot_id, BotConfigUpdateSchema(**bot_payload), user_id)
            else:
                bot_payload = self._bot_only_payload(draft)
                bot_result = await bot_service.create_bot_config(BotConfigCreateSchema(**bot_payload), user_id)
                bot_id = bot_result.get("id")
            verified = await self._verify_created_objects(user_id, None, None, bot_id)
        except Exception:
            await self.session.rollback()
            await self._upsert_action_audit(user_id, action_id, action, status="failed", result={"ok": False, "bot_id": bot_id})
            raise

        result = {
            "ok": True,
            "message": "Bot bijgewerkt" if draft.get("operation") == "update" else "Bot aangemaakt",
            "bot_id": bot_id,
            "strategy_id": draft.get("strategy_id"),
            "operation": draft.get("operation") or "create",
            "changes": draft.get("changes") or [],
            "draft": draft,
            "action_id": action_id,
            "verified": verified,
        }
        await self._upsert_action_audit(user_id, action_id, action, status="executed", result=result)
        await self.clear_state(user_id)
        return result

    async def _execute_indicator_config_action(self, user_id: int, action: Dict[str, Any]) -> Dict[str, Any]:
        draft = _deep_merge(empty_indicator_config_draft(), action.get("payload") or {})
        action_id = f"{action.get('id') or self._indicator_config_action_id(draft)}-u{user_id}"
        acquired = await self._try_create_pending_action(user_id, action_id, action)
        if not acquired:
            existing_result = await self._wait_for_action_result(user_id, action_id)
            if existing_result:
                return existing_result
            raise HTTPException(409, "Deze Finn actie wordt al verwerkt. Probeer zo opnieuw.")

        await self._hydrate_indicator_config_draft(user_id, draft)
        validation = self._validate_indicator_config_draft(draft)
        if not validation["can_confirm"]:
            await self._upsert_action_audit(user_id, action_id, action, status="failed", result={
                "ok": False,
                "message": "Indicator-configuratie is nog niet geldig",
                "missing_fields": validation["missing_fields"],
                "invalid_fields": validation["invalid_fields"],
            })
            raise HTTPException(422, {
                "message": "Indicator-configuratie is nog niet geldig",
                "missing_fields": validation["missing_fields"],
                "invalid_fields": validation["invalid_fields"],
            })

        indicator = draft["indicator"]
        category = draft["category"]
        try:
            config_service = IndicatorConfigService(IndicatorConfigRepository(self.session))
            if draft.get("operation") == "reset":
                await config_service.reset_indicator_rules(category, indicator, user_id)
            elif draft.get("score_mode") == "custom":
                await config_service.save_custom_rules(
                    category=category,
                    indicator=indicator,
                    user_id=user_id,
                    rules=draft.get("rules") or [],
                    weight=float(draft["weight"]),
                )
            else:
                await config_service.update_indicator_settings(
                    category=category,
                    indicator=indicator,
                    user_id=user_id,
                    score_mode=draft["score_mode"],
                    weight=float(draft["weight"]),
                )
            node_active = False
            if draft.get("activate_node") and category == "macro":
                macro_service = MacroDataService(self.session)
                if not await macro_service.repository.check_indicator_exists(user_id, indicator):
                    await macro_service.add_macro_indicator(user_id, indicator, None)
                node_active = True
            elif draft.get("activate_node") and category == "technical":
                technical_service = TechnicalDataService(self.session)
                symbol = draft.get("symbol") or "BTC"
                if await technical_service.repository.check_duplicate(indicator, user_id, symbol):
                    await technical_service.repository.ensure_user_config(user_id, indicator, "technical")
                else:
                    await technical_service.add_technical_indicator(indicator, user_id, symbol)
                node_active = True
            verified = await self._verify_indicator_config(
                user_id,
                category,
                indicator,
                node_active=node_active,
                require_override=draft.get("operation") != "reset",
            )
        except Exception:
            await self.session.rollback()
            await self._upsert_action_audit(user_id, action_id, action, status="failed", result={
                "ok": False,
                "indicator": indicator,
                "category": category,
            })
            raise

        result = {
            "ok": True,
            "message": "Indicator-configuratie gereset" if draft.get("operation") == "reset" else ("Indicator-configuratie bijgewerkt" if draft.get("operation") == "update" else "Indicator-configuratie toegevoegd"),
            "indicator": indicator,
            "category": category,
            "symbol": draft.get("symbol"),
            "operation": draft.get("operation") or "configure",
            "changes": draft.get("changes") or [],
            "draft": draft,
            "action_id": action_id,
            "verified": verified,
        }
        await self._upsert_action_audit(user_id, action_id, action, status="executed", result=result)
        await self.clear_state(user_id)
        return result

    async def _execute_strategy_action(self, user_id: int, action: Dict[str, Any]) -> Dict[str, Any]:
        draft = _deep_merge(empty_strategy_draft(), action.get("payload") or {})
        self._apply_strategy_defaults(draft)
        action_id = f"{action.get('id') or self._strategy_action_id(draft)}-u{user_id}"
        acquired = await self._try_create_pending_action(user_id, action_id, action)
        if not acquired:
            existing_result = await self._wait_for_action_result(user_id, action_id)
            if existing_result:
                return existing_result
            raise HTTPException(409, "Deze Finn actie wordt al verwerkt. Probeer zo opnieuw.")

        validation = self._validate_strategy_draft(draft)
        if not validation["can_confirm"]:
            await self._upsert_action_audit(user_id, action_id, action, status="failed", result={
                "ok": False,
                "message": "Strategie is nog niet geldig",
                "missing_fields": validation["missing_fields"],
                "invalid_fields": validation["invalid_fields"],
            })
            raise HTTPException(422, {
                "message": "Strategie is nog niet geldig",
                "missing_fields": validation["missing_fields"],
                "invalid_fields": validation["invalid_fields"],
            })

        strategy_service = StrategyService(self.session)
        strategy_id = None
        try:
            strategy_payload = self._strategy_only_payload(draft)
            if draft.get("operation") == "update":
                strategy_id = int(draft["strategy_id"])
                await strategy_service.update_strategy(strategy_id, strategy_payload, user_id)
            else:
                strategy_result = await strategy_service.save_strategy(
                    StrategyCreateSchema(**strategy_payload),
                    strategy_payload,
                    user_id,
                )
                strategy_id = strategy_result["id"]
            verified = await self._verify_created_objects(user_id, draft.get("setup_id"), strategy_id, None)
        except Exception:
            await self.session.rollback()
            await self._upsert_action_audit(
                user_id,
                action_id,
                action,
                status="failed",
                result={"ok": False, "strategy_id": strategy_id},
            )
            raise

        result = {
            "ok": True,
            "message": "Strategie bijgewerkt" if draft.get("operation") == "update" else "Strategie aangemaakt",
            "setup_id": draft.get("setup_id"),
            "strategy_id": strategy_id,
            "bot_id": None,
            "operation": draft.get("operation") or "create",
            "draft": draft,
            "action_id": action_id,
            "verified": verified,
        }
        await self._upsert_action_audit(user_id, action_id, action, status="executed", result=result)
        await self.clear_state(user_id)
        return result

    async def get_open_plan_state(self, user_id: int) -> Dict[str, Any]:
        context = await self.hydrate_context(user_id, {})
        draft = context.get("finn_draft")
        if isinstance(draft, dict) and draft.get("draft_kind") == "indicator_config":
            await self._hydrate_indicator_config_draft(user_id, draft)
            validation = self._validate_indicator_config_draft(draft)
            actions = []
            if validation["can_confirm"]:
                action_payload = deepcopy(draft)
                actions.append({
                    "id": self._indicator_config_action_id(action_payload),
                    "type": "configure_indicator",
                    "label": "Indicator configureren",
                    "payload": action_payload,
                    "risk_level": "low",
                    "requires_confirmation": True,
                    "autonomy_level": "confirm_required",
                })
            return {
                "ok": True,
                "has_draft": True,
                "response": self._build_indicator_config_message(draft, validation),
                "intent": "indicator_config",
                "flow": "indicator_config",
                "draft": draft,
                "state": self._indicator_config_flow_state(draft, validation),
                "reasoning": self._indicator_config_reasoning(draft, validation),
                "missing_fields": validation["missing_fields"],
                "invalid_fields": validation["invalid_fields"],
                "next_question": validation["next_question"],
                "can_confirm": validation["can_confirm"],
                "actions": actions,
            }
        if isinstance(draft, dict) and draft.get("draft_kind") == "bot":
            await self._hydrate_existing_bot_draft_from_db(user_id, draft)
            await self._hydrate_bot_draft_from_db(user_id, draft)
            await self._apply_live_bot_preflight(user_id, draft)
            validation = self._validate_bot_draft(draft)
            existing_bot = await self._existing_bot_for_strategy(user_id, draft.get("strategy_id"))
            if existing_bot and draft.get("operation") != "update":
                draft["existing_bot_id"] = existing_bot.get("id")
                validation = {
                    "missing_fields": [],
                    "invalid_fields": [{"field": "strategy_id", "reason": "voor deze strategie bestaat al een bot"}],
                    "next_question": "bot.update_existing",
                    "can_confirm": False,
                }
            actions = []
            if validation["can_confirm"]:
                action_payload = deepcopy(draft)
                actions.append({
                    "id": self._bot_action_id(action_payload),
                    "type": "create_bot",
                    "label": "Bot bijwerken" if draft.get("operation") == "update" else "Bot aanmaken",
                    "payload": action_payload,
                    "risk_level": "high" if draft["bot"].get("is_live") else "medium",
                    "requires_confirmation": True,
                    "autonomy_level": "confirm_required",
                })
            return {
                "ok": True,
                "has_draft": True,
                "response": self._build_bot_message(draft, validation),
                "intent": "bot_creation",
                "flow": "bot_creation",
                "draft": draft,
                "state": self._bot_flow_state(draft, validation),
                "reasoning": self._bot_reasoning(draft, validation),
                "missing_fields": validation["missing_fields"],
                "invalid_fields": validation["invalid_fields"],
                "next_question": validation["next_question"],
                "can_confirm": validation["can_confirm"],
                "actions": actions,
            }
        if isinstance(draft, dict) and draft.get("draft_kind") == "strategy":
            await self._hydrate_strategy_draft_from_db(user_id, draft)
            validation = self._validate_strategy_draft(draft)
            message = self._build_strategy_message(draft, validation)
            strategy_service = StrategyService(self.session)
            existing_strategy = None
            if draft.get("setup_id"):
                existing_strategy = await strategy_service.get_strategy_by_setup(int(draft["setup_id"]), user_id)
            if existing_strategy and draft.get("operation") != "update":
                draft["strategy_id"] = None
                draft["existing_strategy_id"] = existing_strategy.get("id")
                duplicate_validation = {
                    "missing_fields": [],
                    "invalid_fields": [{"field": "setup_id", "reason": "voor deze setup bestaat al een strategie"}],
                    "next_question": "strategy.update_existing",
                    "can_confirm": False,
                }
                return {
                    "ok": True,
                    "has_draft": True,
                    "response": (
                        f"Deze setup heeft al strategie #{existing_strategy.get('id')}. "
                        "Ik maak daarom geen tweede strategie aan. Zeg bijvoorbeeld 'pas de strategie aan met 150 euro' "
                        "als je deze bestaande strategie wilt bijwerken."
                    ),
                    "intent": "strategy_creation",
                    "flow": "strategy_creation",
                    "draft": draft,
                    "state": self._strategy_flow_state(draft, duplicate_validation),
                    "reasoning": self._strategy_reasoning(draft, duplicate_validation),
                    "missing_fields": duplicate_validation["missing_fields"],
                    "invalid_fields": duplicate_validation["invalid_fields"],
                    "next_question": duplicate_validation["next_question"],
                    "can_confirm": duplicate_validation["can_confirm"],
                    "actions": [],
                }
            if existing_strategy and draft.get("operation") == "update":
                existing_for_diff = await self._load_strategy_snapshot_for_diff(user_id, draft, strategy_service)
                self._merge_existing_strategy_into_draft(draft, existing_for_diff or existing_strategy)
                draft["changes"] = self._strategy_changes(existing_for_diff or existing_strategy, draft)
                validation = self._validate_strategy_draft(draft)
                message = self._build_strategy_message(draft, validation)
            actions = []
            if validation["can_confirm"]:
                action_payload = deepcopy(draft)
                actions.append({
                    "id": self._strategy_action_id(action_payload),
                    "type": "create_strategy",
                    "label": "Strategie bijwerken" if draft.get("operation") == "update" else "Strategie aanmaken",
                    "payload": action_payload,
                    "risk_level": "medium" if draft.get("setup_type") == "trade" else "low",
                    "requires_confirmation": True,
                    "autonomy_level": "confirm_required",
                })
            return {
                "ok": True,
                "has_draft": True,
                "response": message,
                "intent": "strategy_creation",
                "flow": "strategy_creation",
                "draft": draft,
                "state": self._strategy_flow_state(draft, validation),
                "reasoning": self._strategy_reasoning(draft, validation),
                "missing_fields": validation["missing_fields"],
                "invalid_fields": validation["invalid_fields"],
                "next_question": validation["next_question"],
                "can_confirm": validation["can_confirm"],
                "actions": actions,
            }

        has_recoverable_draft = (
            isinstance(draft, dict)
            and (
                draft.get("plan_type")
                or draft.get("asset")
                or isinstance(draft.get("_clarification"), dict)
            )
        )
        if not has_recoverable_draft:
            return {"ok": True, "has_draft": False}

        validation = self._validate(draft)
        message = self._build_message(draft, validation)
        actions = []
        if validation["can_confirm"]:
            action_payload = deepcopy(draft)
            action_id = self._action_id(action_payload)
            actions.append({
                "id": action_id,
                "type": "create_plan",
                "label": "Plan aanmaken",
                "payload": action_payload,
                "risk_level": self._action_risk(draft),
                "requires_confirmation": True,
                "autonomy_level": "confirm_required",
                "guardrails": self._guardrails(draft),
            })
        return {
            "ok": True,
            "has_draft": True,
            "response": message,
            "intent": "plan_creation",
            "flow": "plan_creation",
            "draft": draft,
            "state": self._flow_state(draft, validation),
            "reasoning": self._reasoning(draft, validation),
            "missing_fields": validation["missing_fields"],
            "invalid_fields": validation["invalid_fields"],
            "next_question": validation["next_question"],
            "can_confirm": validation["can_confirm"],
            "actions": actions,
        }

    async def _try_create_pending_action(self, user_id: int, action_id: str, action: Dict[str, Any]) -> bool:
        if not self.session:
            return True
        payload = {
            "action": action,
            "result": None,
            "updated_at": datetime.utcnow().isoformat(),
        }
        row = await self.session.execute(text("""
            INSERT INTO ai_pending_actions (id, user_id, type, payload, status, expires_at)
            VALUES (:id, :user_id, 'finn_create_plan', CAST(:payload AS JSONB), 'pending', :expires_at)
            ON CONFLICT (id) DO NOTHING
            RETURNING id
        """), {
            "id": action_id,
            "user_id": user_id,
            "payload": json.dumps(payload),
            "expires_at": datetime.utcnow() + timedelta(days=7),
        })
        acquired = row.fetchone() is not None
        await self.session.commit()
        return acquired

    async def _wait_for_action_result(self, user_id: int, action_id: str) -> Optional[Dict[str, Any]]:
        for _ in range(24):
            result = await self._get_executed_action_result(user_id, action_id)
            if result:
                return result
            await asyncio.sleep(0.25)
        return await self._get_executed_action_result(user_id, action_id)

    async def _get_executed_action_result(self, user_id: int, action_id: str) -> Optional[Dict[str, Any]]:
        if not self.session:
            return None
        row = await self.session.execute(text("""
            SELECT payload
            FROM ai_pending_actions
            WHERE id = :id AND user_id = :user_id AND status = 'executed'
            LIMIT 1
        """), {"id": action_id, "user_id": user_id})
        existing = row.mappings().first()
        if not existing:
            return None
        payload = existing["payload"] or {}
        if isinstance(payload, str):
            payload = json.loads(payload)
        result = payload.get("result")
        return result if isinstance(result, dict) else None

    async def _upsert_action_audit(
        self,
        user_id: int,
        action_id: str,
        action: Dict[str, Any],
        *,
        status: str,
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.session:
            return
        payload = {
            "action": action,
            "result": result,
            "updated_at": datetime.utcnow().isoformat(),
        }
        await self.session.execute(text("""
            INSERT INTO ai_pending_actions (id, user_id, type, payload, status, expires_at)
            VALUES (:id, :user_id, 'finn_create_plan', CAST(:payload AS JSONB), :status, :expires_at)
            ON CONFLICT (id) DO UPDATE SET
                payload = EXCLUDED.payload,
                status = EXCLUDED.status
            WHERE ai_pending_actions.user_id = EXCLUDED.user_id
        """), {
            "id": action_id,
            "user_id": user_id,
            "payload": json.dumps(payload),
            "status": status,
            "expires_at": datetime.utcnow() + timedelta(days=7),
        })
        await self.session.commit()

    async def _verify_created_objects(
        self,
        user_id: int,
        setup_id: Optional[int],
        strategy_id: Optional[int],
        bot_id: Optional[int],
    ) -> Dict[str, bool]:
        setup_found = True if setup_id is None else bool(await SetupService(self.session).repository.get_setup_by_id(setup_id, user_id))
        strategy_found = True if strategy_id is None else bool(await StrategyService(self.session).repository.get_raw_strategy_with_setup(strategy_id, user_id))
        bot_found = False
        if bot_id:
            bot_found = bool(await BotService(self.session).repository.get_bot_config(user_id, bot_id))

        verified = {
            "setup": setup_found,
            "strategy": strategy_found,
            "bot": bot_found,
        }
        required_verified = setup_found and strategy_found and (bot_found if bot_id else True)
        if not required_verified:
            raise HTTPException(500, f"Read-after-write verificatie faalde: {verified}")
        return verified

    async def _verify_indicator_config(
        self,
        user_id: int,
        category: str,
        indicator: str,
        *,
        node_active: bool = False,
        require_override: bool = True,
    ) -> Dict[str, bool]:
        config = await IndicatorConfigService(IndicatorConfigRepository(self.session)).get_indicator_config(category, indicator, user_id)
        rules_ok = bool(config and len(config.rules) == 5)
        table = {
            "macro": "macro_indicator_rules",
            "technical": "technical_indicator_rules",
        }.get(category)
        if not table:
            raise HTTPException(400, "Onbekende indicator category")
        override_rows = await self.session.execute(text("""
            SELECT COUNT(*) AS count
            FROM {table}
            WHERE user_id = :user_id AND indicator = :indicator
        """.format(table=table)), {"user_id": user_id, "indicator": indicator})
        override_count = int(override_rows.scalar() or 0)
        override_ok = override_count == 5 if require_override else override_count == 0
        node_ok = True
        if node_active and category == "macro":
            node_ok = await MacroDataService(self.session).repository.check_indicator_exists(user_id, indicator)
        elif node_active and category == "technical":
            config_rows = await self.session.execute(text("""
                SELECT COUNT(*) AS count
                FROM user_indicator_configs
                WHERE user_id = :user_id AND category = 'technical' AND indicator = :indicator
            """), {"user_id": user_id, "indicator": indicator})
            node_ok = int(config_rows.scalar() or 0) > 0
        node_key = "technical_node" if category == "technical" else "macro_node"
        verified = {
            "indicator_config": rules_ok and override_ok,
            node_key: node_ok,
        }
        if not verified["indicator_config"] or not verified[node_key]:
            raise HTTPException(500, f"Indicator read-after-write verificatie faalde: {verified}")
        return verified

    async def _log_intelligence_event(self, user_id: int, draft: Dict[str, Any], result: Dict[str, Any]) -> None:
        if not self.session:
            return
        await self.session.execute(text("""
            INSERT INTO ai_intelligence_events (user_id, type, symbol, title, description, severity, payload, status)
            VALUES (
                :user_id,
                'finn_plan_created',
                :symbol,
                :title,
                :description,
                'info',
                CAST(:payload AS JSONB),
                'active'
            )
        """), {
            "user_id": user_id,
            "symbol": draft.get("asset"),
            "title": f"Finn heeft {draft.get('asset')} {draft.get('plan_type')} plan aangemaakt",
            "description": "Setup, strategy en optioneel bot zijn via bevestigde Finn-actie aangemaakt.",
            "payload": json.dumps({"draft": draft, "result": result}, default=str),
        })
        await self.session.commit()

    async def _unique_setup_name(self, setup_service: SetupService, base_name: str, user_id: int) -> str:
        name = (base_name or "Finn Plan").strip()
        if not (await setup_service.check_name(name, user_id)).get("exists"):
            return name

        for suffix in range(2, 50):
            candidate = f"{name} #{suffix}"
            if not (await setup_service.check_name(candidate, user_id)).get("exists"):
                return candidate
        raise HTTPException(409, "Setupnaam bestaat al te vaak. Kies een andere naam.")

    async def _cleanup_created(
        self,
        user_id: int,
        *,
        setup_id: Optional[int],
        strategy_id: Optional[int],
        bot_id: Optional[int],
    ) -> None:
        cleanup_steps = []
        if bot_id:
            cleanup_steps.append((BotService(self.session).delete_bot_config, bot_id))
        if strategy_id:
            cleanup_steps.append((StrategyService(self.session).delete_strategy, strategy_id))
        if setup_id:
            cleanup_steps.append((SetupService(self.session).delete_setup, setup_id))

        for cleanup, object_id in cleanup_steps:
            try:
                await cleanup(object_id, user_id)
            except Exception:
                pass

    def _setup_payload(self, draft: Dict[str, Any]) -> Dict[str, Any]:
        setup = draft["setup"]
        dca = draft["dca"]
        plan_type = draft["plan_type"]
        return {
            "name": setup["name"],
            "symbol": draft["asset"],
            "setup_type": plan_type,
            "timeframe": setup["timeframe"],
            "dca_frequency": dca.get("frequency") if plan_type == "dca" else None,
            "dca_day": str(WEEKDAY_NUMBERS.get(str(dca.get("day") or "").lower(), dca.get("day"))) if plan_type == "dca" and dca.get("frequency") == "weekly" and dca.get("day") is not None else None,
            "dca_month_day": dca.get("month_day") if plan_type == "dca" and dca.get("frequency") == "monthly" else None,
            "min_macro_score": setup["macro_score_range"][0],
            "max_macro_score": setup["macro_score_range"][1],
            "min_technical_score": setup["technical_score_range"][0],
            "max_technical_score": setup["technical_score_range"][1],
            "min_market_score": setup["market_score_range"][0],
            "max_market_score": setup["market_score_range"][1],
            "description": "Aangemaakt via Finn",
            "category": "finn_plan",
        }

    def _strategy_payload(self, draft: Dict[str, Any], setup_id: int) -> Dict[str, Any]:
        strategy = draft["strategy"]
        payload = {
            "name": f"{draft['setup']['name']} Strategy",
            "setup_id": setup_id,
            "setup_type": draft["plan_type"],
            "execution_mode": strategy.get("execution_mode") or "fixed",
            "base_amount": float(strategy["base_amount_eur"]),
            "decision_curve": strategy.get("decision_curve"),
            "risk_profile": draft["bot"].get("risk_profile") or "balanced",
            "explanation": "Aangemaakt via Finn",
        }
        if draft["plan_type"] == "trade":
            payload.update({
                "direction": strategy.get("direction") or "long",
                "entry_type": strategy.get("entry_type") or "limit",
                "trade_execution_mode": strategy.get("entry_type") or "limit",
                "automation": draft["bot"].get("automation") or ("bot_assisted" if draft["bot"].get("create_bot") else "manual_only"),
                "entry": strategy.get("entry"),
                "stop_loss": strategy.get("stop_loss"),
                "targets": strategy.get("targets"),
            })
        elif draft["plan_type"] == "dca":
            payload.update({
                "dca_mode": draft["dca"].get("dca_mode") or "standard",
                "buy_score_threshold": draft["dca"].get("buy_score_threshold"),
            })
        return payload

    def _strategy_only_payload(self, draft: Dict[str, Any]) -> Dict[str, Any]:
        strategy = draft["strategy"]
        payload = {
            "name": f"Finn {str(draft.get('asset') or '').upper()} Strategy".strip(),
            "setup_id": int(draft["setup_id"]),
            "setup_type": draft["setup_type"],
            "execution_mode": strategy.get("execution_mode") or "fixed",
            "base_amount": float(strategy["base_amount_eur"]),
            "decision_curve": strategy.get("decision_curve"),
            "risk_profile": strategy.get("risk_profile") or "balanced",
            "automation": strategy.get("automation") or "manual_only",
            "explanation": "Aangemaakt via Finn",
        }
        if draft["setup_type"] == "trade":
            payload.update({
                "direction": strategy.get("direction") or "long",
                "entry_type": strategy.get("entry_type") or "limit",
                "trade_execution_mode": strategy.get("entry_type") or "limit",
                "market_execution_ack": bool(strategy.get("market_execution_ack")),
                "entry": strategy.get("entry"),
                "stop_loss": strategy.get("stop_loss"),
                "targets": strategy.get("targets"),
            })
        return payload

    def _bot_payload(self, draft: Dict[str, Any], strategy_id: int) -> Dict[str, Any]:
        bot = draft["bot"]
        return {
            "name": f"{draft['setup']['name']} Bot",
            "strategy_id": strategy_id,
            "mode": bot.get("mode") or "manual",
            "is_live": bool(bot.get("is_live")),
            "risk_profile": bot.get("risk_profile") or "balanced",
            "budget_total_eur": float(bot.get("total_budget_eur") or 0),
            "budget_daily_limit_eur": float(bot.get("daily_limit_eur") or 0),
            "budget_min_order_eur": float(bot.get("min_order_eur") or 0),
            "budget_max_order_eur": float(bot.get("max_order_eur") or 0),
            "max_asset_exposure_pct": float(bot.get("max_asset_exposure_pct") or 100),
            "cadence": "daily",
            "base_currency": "EUR",
            "symbol": draft["asset"],
        }

    def _bot_only_payload(self, draft: Dict[str, Any]) -> Dict[str, Any]:
        bot = draft["bot"]
        return {
            "name": bot["name"],
            "strategy_id": int(draft["strategy_id"]),
            "mode": bot.get("mode") or "manual",
            "is_live": bool(bot.get("is_live")),
            "risk_profile": bot.get("risk_profile") or "balanced",
            "cadence": bot.get("cadence") or "daily",
            "budget_total_eur": float(bot.get("budget_total_eur") or 0),
            "budget_daily_limit_eur": float(bot.get("budget_daily_limit_eur") or 0),
            "budget_min_order_eur": float(bot.get("budget_min_order_eur") or 0),
            "budget_max_order_eur": float(bot.get("budget_max_order_eur") or 0),
            "max_asset_exposure_pct": float(bot.get("max_asset_exposure_pct") or 100),
            "base_currency": bot.get("base_currency") or "EUR",
            "symbol": draft.get("asset"),
        }

    def _bot_update_payload(self, draft: Dict[str, Any]) -> Dict[str, Any]:
        bot = draft["bot"]
        return {
            "name": bot.get("name"),
            "mode": bot.get("mode") or "manual",
            "is_live": bool(bot.get("is_live")),
            "risk_profile": bot.get("risk_profile") or "balanced",
            "cadence": bot.get("cadence") or "daily",
            "budget_total_eur": float(bot.get("budget_total_eur") or 0),
            "budget_daily_limit_eur": float(bot.get("budget_daily_limit_eur") or 0),
            "budget_min_order_eur": float(bot.get("budget_min_order_eur") or 0),
            "budget_max_order_eur": float(bot.get("budget_max_order_eur") or 0),
            "max_asset_exposure_pct": float(bot.get("max_asset_exposure_pct") or 100),
            "base_currency": bot.get("base_currency") or "EUR",
        }
