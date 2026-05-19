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
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.schemas.bot_schema import BotConfigCreateSchema
from backend.schemas.trading_schema import SetupCreateSchema, StrategyCreateSchema
from backend.services.bot_service import BotService
from backend.services.setup_service import SetupService
from backend.services.strategy_service import StrategyService


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
        "strategy_id": None,
        "existing_bot_id": None,
        "asset": None,
        "setup_type": None,
        "timeframe": None,
        "bot": {
            "name": None,
            "mode": "manual",
            "is_live": False,
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
        if state and state.get("current_flow") in {"plan_creation", "strategy_creation", "bot_creation"} and isinstance(draft, dict):
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
        if response.get("intent") in {"plan_creation_cancelled", "strategy_creation_cancelled", "bot_creation_cancelled"}:
            await repo.clear_state(user_id)
            return
        if response.get("flow") not in {"plan_creation", "strategy_creation", "bot_creation"} or not isinstance(response.get("draft"), dict):
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
            elif draft.get("plan_type") or draft.get("asset") or isinstance(draft.get("_clarification"), dict):
                flow = "plan_creation"

        if not flow and self.session:
            state = await ConversationStateRepository(self.session).get_state(user_id)
            if state and state.get("current_flow") in {"plan_creation", "strategy_creation", "bot_creation"}:
                flow = state.get("current_flow")

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
        has_strategy_ref = bool(context.get("strategy_id")) or bool(re.search(r"\bstrateg(?:ie|y)\s*#?\s*\d+\b", q))
        has_create_intent = any(word in q for word in ["maak", "aanmaken", "creeer", "creeër", "bouw", "instellen", "wil"])
        return has_bot_word and (has_strategy_ref or has_create_intent)

    def looks_like_status_request(self, query: str) -> bool:
        q = (query or "").lower()
        has_status = any(word in q for word in [
            "actief", "active", "inactive", "inactief", "waarom koopt",
            "waarom niet", "moet ik kopen", "mag ik kopen", "plan actief",
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
        if self.is_cancel_request(q):
            return {
                "response": "Prima, ik heb deze bot-aanmaak gestopt. Er is niets aangemaakt.",
                "intent": "bot_creation_cancelled",
                "flow": None,
                "draft": empty_bot_draft(),
                "missing_fields": [],
                "invalid_fields": [],
                "next_question": None,
                "can_confirm": False,
                "actions": [],
            }

        strategy_id_match = re.search(r"\bstrateg(?:ie|y)\s*#?\s*(\d+)\b", q, re.IGNORECASE)
        if strategy_id_match:
            new_strategy_id = int(strategy_id_match.group(1))
            if draft.get("strategy_id") and int(draft["strategy_id"]) != new_strategy_id:
                self._reset_bot_strategy_binding(draft)
            draft["strategy_id"] = new_strategy_id

        bot = draft["bot"]
        name_match = re.search(r"(?:noem|naam|heet)\s+(?:hem|deze)?\s*[\"']?([^\"'.]+)[\"']?", q, re.IGNORECASE)
        if name_match:
            name = name_match.group(1).strip()
            if 2 <= len(name) <= 80:
                bot["name"] = name

        bot_patch = self._extract_from_query(q).get("bot") or {}
        for field, value in bot_patch.items():
            if value is not None:
                mapping = {
                    "total_budget_eur": "budget_total_eur",
                    "daily_limit_eur": "budget_daily_limit_eur",
                    "min_order_eur": "budget_min_order_eur",
                    "max_order_eur": "budget_max_order_eur",
                }
                bot[mapping.get(field, field)] = value

        if "hourly" in q_lower or "elk uur" in q_lower:
            bot["cadence"] = "hourly"
        elif "weekly" in q_lower or "wekelijks" in q_lower:
            bot["cadence"] = "weekly"
        elif "monthly" in q_lower or "maandelijks" in q_lower:
            bot["cadence"] = "monthly"
        elif "daily" in q_lower or "dagelijks" in q_lower:
            bot["cadence"] = "daily"

        for key, pattern in [
            ("budget_total_eur", r"(?:totaal\s*)?budget\s*(?:van|=|:)?\s*(?:€|eur|euro)?\s*([0-9][0-9.,]*)"),
            ("budget_daily_limit_eur", r"(?:daglimiet|daily limit)\s*(?:van|=|:)?\s*(?:€|eur|euro)?\s*([0-9][0-9.,]*)"),
            ("budget_min_order_eur", r"(?:min(?:imum)? order|min order)\s*(?:van|=|:)?\s*(?:€|eur|euro)?\s*([0-9][0-9.,]*)"),
            ("budget_max_order_eur", r"(?:max(?:imum)? order|max order)\s*(?:van|=|:)?\s*(?:€|eur|euro)?\s*([0-9][0-9.,]*)"),
        ]:
            match = re.search(pattern, q_lower)
            if match:
                bot[key] = _number(match.group(1))

        amount = re.search(r"(?:€|eur|euro)\s*([0-9][0-9.,]*)|([0-9][0-9.,]*)\s*(?:€|eur|euro)", q_lower)
        if amount and "budget" in q_lower and not bot.get("budget_total_eur"):
            bot["budget_total_eur"] = _number(amount.group(1) or amount.group(2))

        self._apply_bot_name_default(draft)

        validation = self._validate_bot_draft(draft)
        actions = []
        if validation["can_confirm"]:
            action_payload = deepcopy(draft)
            actions.append({
                "id": self._bot_action_id(action_payload),
                "type": "create_bot",
                "label": "Bot aanmaken",
                "payload": action_payload,
                "risk_level": "high" if bot.get("is_live") else "medium",
                "requires_confirmation": True,
                "autonomy_level": "confirm_required",
                "guardrails": {
                    "requires_confirmation": True,
                    "can_execute_without_user": False,
                    "execution_allowed": "bot_creation_only",
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
        await self._hydrate_bot_draft_from_db(user_id, draft)
        validation = self._validate_bot_draft(draft)

        existing_bot = await self._existing_bot_for_strategy(user_id, draft.get("strategy_id"))
        if existing_bot:
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
                "label": "Bot aanmaken",
                "payload": action_payload,
                "risk_level": "high" if draft["bot"].get("is_live") else "medium",
                "requires_confirmation": True,
                "autonomy_level": "confirm_required",
                "guardrails": {
                    "requires_confirmation": True,
                    "can_execute_without_user": False,
                    "execution_allowed": "bot_creation_only",
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
            daily_scores = await score_repo.fetch_daily_scores(user_id, asset)
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

    def _validate_bot_draft(self, draft: Dict[str, Any]) -> Dict[str, Any]:
        missing: List[str] = []
        invalid: List[Dict[str, str]] = []
        bot = draft.get("bot") or {}
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

        bot = draft.get("bot") or {}
        env = "live" if bot.get("is_live") else "paper"
        return (
            "Ik heb je bot klaarstaan. Controleer dit even en bevestig als het klopt:\n\n"
            f"- Bot: {bot.get('name')}\n"
            f"- Strategie: #{draft.get('strategy_id')}\n"
            f"- Omgeving: {env}\n"
            f"- Mode: {bot.get('mode')}\n"
            f"- Risk: {bot.get('risk_profile')}\n"
            f"- Cadence: {bot.get('cadence')}\n"
            f"- Budget: €{bot.get('budget_total_eur')} totaal, €{bot.get('budget_daily_limit_eur')} per dag"
        )

    def _bot_flow_state(self, draft: Dict[str, Any], validation: Dict[str, Any], strategy_options: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        return {
            "status": "ready_for_confirmation" if validation["can_confirm"] else "collecting",
            "current_flow": "bot_creation",
            "strategy_id": draft.get("strategy_id"),
            "existing_bot_id": draft.get("existing_bot_id"),
            "asset": draft.get("asset"),
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

    def _in_range(self, score: Optional[float], score_range: Optional[List[int]]) -> Optional[bool]:
        if score is None or not score_range:
            return None
        return score_range[0] <= score <= score_range[1]

    def _evaluate_draft_against_scores(
        self,
        draft: Dict[str, Any],
        daily_scores: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        setup = draft.get("setup") or {}
        checks = {
            "macro": {
                "score": self._score_value(daily_scores, "macro"),
                "range": setup.get("macro_score_range"),
                "interpretation": (daily_scores or {}).get("macro_interpretation"),
                "top_contributors": self._json_value((daily_scores or {}).get("macro_top_contributors"), []),
            },
            "technical": {
                "score": self._score_value(daily_scores, "technical"),
                "range": setup.get("technical_score_range"),
                "interpretation": (daily_scores or {}).get("technical_interpretation"),
                "top_contributors": self._json_value((daily_scores or {}).get("technical_top_contributors"), []),
            },
            "market": {
                "score": self._score_value(daily_scores, "market"),
                "range": setup.get("market_score_range"),
                "interpretation": (daily_scores or {}).get("market_interpretation"),
                "top_contributors": self._json_value((daily_scores or {}).get("market_top_contributors"), []),
            },
        }
        for check in checks.values():
            check["pass"] = self._in_range(check["score"], check["range"])
        known = [c["pass"] for c in checks.values() if c["pass"] is not None]
        is_active = bool(known) and all(known)
        return {
            "is_active": is_active,
            "confidence": "low" if len(known) < 3 else "medium",
            "checks": checks,
            "has_scores": bool(daily_scores),
        }

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
        breakdown = self._json_value(setup.get("breakdown"), {})
        return {
            "is_active": bool(setup.get("is_active")),
            "confidence": "medium" if daily_scores else "low",
            "checks": breakdown if isinstance(breakdown, dict) else {},
            "has_scores": bool(daily_scores),
            "setup": {
                "id": setup.get("id"),
                "name": setup.get("name"),
                "score": float(setup.get("score") or 0),
            },
        }

    def _analysis_reasons(self, analysis: Dict[str, Any]) -> List[str]:
        if analysis.get("reason"):
            return [analysis["reason"]]
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
        if source == "draft":
            lines = [f"Je conceptplan voor {asset} is nu {active_text} op basis van de huidige scores."]
            checks = analysis.get("checks") or {}
            for label in ["macro", "technical", "market"]:
                check = checks.get(label) or {}
                score = check.get("score")
                score_range = check.get("range")
                passed = check.get("pass")
                status = "binnen range" if passed else "buiten range"
                lines.append(f"- {label}: {score} versus {score_range} ({status})")
                contributors = check.get("top_contributors") or []
                if contributors:
                    preview = ", ".join(str(item) for item in contributors[:2])
                    lines.append(f"  Belangrijkste signalen: {preview}")
            return "\n".join(lines)

        setup = analysis.get("setup")
        if not setup:
            return analysis.get("reason") or f"Ik vond geen actieve {asset} setup."
        return (
            f"Je opgeslagen setup '{setup.get('name')}' voor {asset} is nu {active_text}. "
            f"De setup-score staat op {setup.get('score')}. Gebruik dit als plan-check, niet als losse emotionele trigger."
        )

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

        await self._hydrate_bot_draft_from_db(user_id, draft)
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
        if existing_bot:
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
            bot_payload = self._bot_only_payload(draft)
            bot_result = await BotService(self.session).create_bot_config(BotConfigCreateSchema(**bot_payload), user_id)
            bot_id = bot_result.get("id")
            verified = await self._verify_created_objects(user_id, None, None, bot_id)
        except Exception:
            await self.session.rollback()
            await self._upsert_action_audit(user_id, action_id, action, status="failed", result={"ok": False, "bot_id": bot_id})
            raise

        result = {
            "ok": True,
            "message": "Bot aangemaakt",
            "bot_id": bot_id,
            "strategy_id": draft.get("strategy_id"),
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
        if isinstance(draft, dict) and draft.get("draft_kind") == "bot":
            await self._hydrate_bot_draft_from_db(user_id, draft)
            validation = self._validate_bot_draft(draft)
            existing_bot = await self._existing_bot_for_strategy(user_id, draft.get("strategy_id"))
            if existing_bot:
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
                    "label": "Bot aanmaken",
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
