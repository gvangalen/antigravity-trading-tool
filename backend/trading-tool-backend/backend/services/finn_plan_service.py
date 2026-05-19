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
        "setup_id": None,
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
        if state and state.get("current_flow") in {"plan_creation", "strategy_creation"} and isinstance(draft, dict):
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
        if response.get("intent") in {"plan_creation_cancelled", "strategy_creation_cancelled"}:
            await repo.clear_state(user_id)
            return
        if response.get("flow") not in {"plan_creation", "strategy_creation"} or not isinstance(response.get("draft"), dict):
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

        setup_id_match = re.search(r"\bsetup\s*#?\s*(\d+)\b", q, re.IGNORECASE)
        if setup_id_match:
            draft["setup_id"] = int(setup_id_match.group(1))

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
                "label": "Strategie aanmaken",
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

    def _validate_strategy_draft(self, draft: Dict[str, Any]) -> Dict[str, Any]:
        missing: List[str] = []
        invalid: List[Dict[str, str]] = []

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

        if draft.get("setup_type") == "trade":
            if strategy.get("direction") != "long":
                invalid.append({"field": "strategy.direction", "reason": "alleen long trades worden nu ondersteund"})
            if strategy.get("entry_type") not in {"limit", "breakout", "market"}:
                missing.append("strategy.entry_type")
            entry = strategy.get("entry")
            stop_loss = strategy.get("stop_loss")
            targets = strategy.get("targets")
            if entry is None:
                missing.append("strategy.entry")
            if stop_loss is None:
                missing.append("strategy.stop_loss")
            if not targets:
                missing.append("strategy.targets")
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

    def _build_strategy_message(self, draft: Dict[str, Any], validation: Dict[str, Any]) -> str:
        next_question = validation["next_question"]
        if validation["invalid_fields"]:
            issue = validation["invalid_fields"][0]
            return f"Ik zie een probleem met {issue['field']}: {issue['reason']}. Wat wil je hiervoor instellen?"
        if next_question == "setup_id":
            return "Voor welke setup wil je deze strategie maken? Noem bijvoorbeeld setup 12 of open eerst de setup."
        if next_question == "setup_type":
            return "Is deze strategie voor een DCA-setup of een gewone trade-setup?"
        if next_question == "strategy.base_amount_eur":
            return "Met welk basisbedrag in euro wil je deze strategie uitvoeren?"
        if next_question == "strategy.entry_type":
            return "Wil je een limit entry, breakout trigger of market execution gebruiken?"
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
            "- Type: strategie",
            f"- Setup: #{draft.get('setup_id')}",
            f"- Setup type: {draft.get('setup_type')}",
            f"- Asset: {draft.get('asset')}",
            f"- Timeframe: {draft.get('timeframe')}",
            f"- Bedrag: €{strategy.get('base_amount_eur')}",
        ]
        if draft.get("setup_type") == "trade":
            lines.extend([
                f"- Uitvoering: {strategy.get('entry_type')}",
                f"- Entry: {strategy.get('entry')}",
                f"- Stop-loss: {strategy.get('stop_loss')}",
                f"- Targets: {strategy.get('targets')}",
                f"- Automatisering: {strategy.get('automation')}",
            ])
        return "\n".join(lines)

    def _strategy_flow_state(self, draft: Dict[str, Any], validation: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "ready_for_confirmation" if validation["can_confirm"] else "collecting",
            "current_flow": "strategy_creation",
            "asset": draft.get("asset"),
            "setup_id": draft.get("setup_id"),
            "setup_type": draft.get("setup_type"),
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
            "message": "Strategie aangemaakt",
            "setup_id": draft.get("setup_id"),
            "strategy_id": strategy_id,
            "bot_id": None,
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
        if isinstance(draft, dict) and draft.get("draft_kind") == "strategy":
            validation = self._validate_strategy_draft(draft)
            message = self._build_strategy_message(draft, validation)
            actions = []
            if validation["can_confirm"]:
                action_payload = deepcopy(draft)
                actions.append({
                    "id": self._strategy_action_id(action_payload),
                    "type": "create_strategy",
                    "label": "Strategie aanmaken",
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
        bot_found = True
        if bot_id:
            bot_found = bool(await BotService(self.session).repository.get_bot_config(user_id, bot_id))

        verified = {
            "setup": setup_found,
            "strategy": strategy_found,
            "bot": bot_found,
        }
        if not all(verified.values()):
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
