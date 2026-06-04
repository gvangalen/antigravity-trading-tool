import hashlib
import json
import re
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.conversation_state_repository import ConversationStateRepository
from backend.infrastructure.repositories.exchange_repository import ExchangeRepository
from backend.infrastructure.repositories.indicator_config_repository import IndicatorConfigRepository
from backend.infrastructure.repositories.macro_data_repository import MacroDataRepository
from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
from backend.infrastructure.repositories.report_repository import ReportRepository
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.infrastructure.repositories.strategy_repository import StrategyRepository
from backend.infrastructure.repositories.technical_data_repository import TechnicalDataRepository
from backend.schemas.bot_schema import BotConfigCreateSchema, BotConfigUpdateSchema
from backend.schemas.trading_schema import SetupCreateSchema, StrategyCreateSchema
from backend.services.bot_service import BotService
from backend.services.finn_action_policy_service import FinnActionPolicyService
from backend.services.finn_execution_governance_service import FinnExecutionGovernanceService
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
TRANSACTIONAL_FLOWS = {"plan_creation", "strategy_creation", "bot_creation", "indicator_config"}
READ_ONLY_FLOWS = {
    "general_help",
    "education",
    "product_help",
    "decision_review",
    "plan_adherence_review",
    "outcome_tracking",
    "outcome_memory",
    "personal_performance",
    "trade_journal_intelligence",
    "personal_coach",
    "portfolio_intelligence",
    "priority_engine",
    "portfolio_operating_system",
    "governed_action_review",
    "context_explain",
    "mission_control_explain",
    "behavioral_intelligence",
    "weekly_reflection",
    "behavioral_memory",
    "finn_report",
    "daily_coach",
    "indicator_insight",
    "status",
}
TRANSACTIONAL_STATE_TTL_MINUTES = 45
BOT_DECISION_STATE_TTL_MINUTES = 20
READ_ONLY_STATE_TTL_MINUTES = 20
INTENT_HISTORY_LIMIT = 8
RECENT_CONTEXT_ENTITY_LIMIT = 6
ROUTE_FAMILY_BY_FLOW = {
    "general_help": "help",
    "product_help": "help",
    "education": "education",
    "decision_review": "review",
    "plan_adherence_review": "coaching",
    "outcome_tracking": "coaching",
    "outcome_memory": "coaching",
    "personal_performance": "coaching",
    "trade_journal_intelligence": "coaching",
    "personal_coach": "coaching",
    "portfolio_intelligence": "review",
    "priority_engine": "explain",
    "portfolio_operating_system": "explain",
    "governed_action_review": "review",
    "context_explain": "explain",
    "mission_control_explain": "explain",
    "behavioral_intelligence": "coaching",
    "weekly_reflection": "coaching",
    "behavioral_memory": "coaching",
    "finn_report": "explain",
    "daily_coach": "coaching",
    "indicator_insight": "explain",
    "status": "explain",
    "maintenance_action": "refresh",
    "plan_creation": "transactional",
    "strategy_creation": "transactional",
    "bot_creation": "transactional",
    "indicator_config": "transactional",
    "bot_decision": "transactional",
    "bot_decision_review": "transactional",
    "bot_execution_decision": "transactional",
}

PRODUCT_REFRESH_HELP_PHRASES = (
    "waarom zijn mijn scores oud",
    "waarom is mijn score oud",
    "waarom zie ik oude data",
    "waarom zie ik nog oude data",
    "waarom zijn mijn daily scores oud",
    "waarom is mijn daily score oud",
    "waarom zie ik nog oude scores",
)

GENERAL_CAPABILITY_FOLLOW_UP_PHRASES = (
    "leg dat in een simpele zin uit",
    "leg dat in één simpele zin uit",
    "in een simpele zin",
    "kort samengevat",
    "kort uitgelegd",
)

OVERTRADING_DIRECT_COACH_TERMS = (
    "overtrade",
    "overtrading",
    "overtraden",
    "te vaak handelen",
    "te veel trades",
    "te veel gehandeld",
    "al te veel trades",
    "te veel entries",
    "nog een trade",
    "weer een trade",
    "ik wil weer handelen",
    "ik wil opnieuw handelen",
    "ik wil alweer handelen",
    "ik wil alweer instappen",
    "ik moet weer iets doen",
    "ik moet alweer iets doen",
    "nog even traden",
)

PLAN_ADHERENCE_HARD_OVERRIDE_TERMS = (
    "mijn plan zegt wachten maar ik wil kopen",
    "mijn plan zegt wachten maar ik wil toch kopen",
    "mijn plan zegt wachten maar ik wil instappen",
    "mijn plan zegt wachten maar ik wil toch instappen",
    "ik wil mijn stop-loss verwijderen",
    "ik wil mijn stop loss verwijderen",
    "ik wil stop-loss verwijderen",
    "ik wil stop loss verwijderen",
    "ik wil een grotere positie openen",
    "ik wil groter gaan",
    "ik wil meer risico nemen",
    "ik wil mijn positie vergroten",
    "ik wil buiten mijn plan handelen",
    "ik wil buiten mijn strategie handelen",
    "ik wil mijn regels loslaten",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_db_timestamp() -> datetime:
    """Return UTC normalized for existing naive timestamp columns."""
    return _utc_now().replace(tzinfo=None)


def _normalized_route_source(route_source: Optional[str]) -> str:
    source = str(route_source or "finn").lower()
    if source.startswith("legacy"):
        return "legacy"
    if "rescue" in source:
        return "finn_rescue"
    return "finn"


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
    def __init__(self, db_session: AsyncSession, trace_id: Optional[str] = None):
        self.session = db_session
        self.trace_id = trace_id
        self.action_policy_service = FinnActionPolicyService()
        self.execution_governance_service = FinnExecutionGovernanceService()

    def _normalized_query(self, query: str) -> str:
        return (query or "").strip().lower()

    def _infer_governed_action_from_query(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        q = self._normalized_query(query)
        context = context or {}
        asset_mentions = _asset_mentions(query)
        has_asset = bool(context.get("symbol") or context.get("asset") or asset_mentions)

        if any(term in q for term in [
            "live order",
            "live trade",
            "live uitvoeren",
            "live uitgevoerd",
            "direct live",
            "manual order",
            "plaats nu direct",
            "plaats direct",
            "zet live",
            "plaats deze trade live",
        ]) or (
            "order" in q and has_asset and any(term in q for term in ["plaats", "open", "uitvoer", "doe"])
        ):
            return {"action_type": "live_manual_order", "subject_type": "trade", "subject_id": context.get("bot_id") or context.get("decision_id")}
        if any(term in q for term in [
            "verwijder mijn stop-loss",
            "haal mijn stop-loss weg",
            "zonder stop-loss",
            "negeer mijn risk limit",
            "ik bevestig later wel",
        ]):
            return {"action_type": "live_manual_order", "subject_type": "trade", "subject_id": context.get("decision_id") or context.get("bot_id")}
        if any(term in q for term in ["rebalance", "allocatie wijzigen", "portfolio mutatie", "herverdelen"]):
            return {"action_type": "portfolio_rebalance", "subject_type": "portfolio", "subject_id": None}
        if any(term in q for term in ["trade plan opslaan", "sla dit trade plan op", "save trade plan"]):
            return {"action_type": "save_trade_plan", "subject_type": "decision", "subject_id": context.get("decision_id") or context.get("bot_id")}
        if any(term in q for term in ["risicoprofiel aanpassen", "risk profile", "risk profiel"]):
            return {"action_type": "update_risk_profile", "subject_type": "profile", "subject_id": None}
        if any(term in q for term in ["watchlist toevoegen", "zet op watchlist", "voeg toe aan watchlist"]):
            return {"action_type": "watchlist_add", "subject_type": "asset", "subject_id": context.get("symbol") or context.get("asset")}
        if any(term in q for term in ["watchlist verwijderen", "haal van watchlist", "verwijder uit watchlist"]):
            return {"action_type": "watchlist_remove", "subject_type": "asset", "subject_id": context.get("symbol") or context.get("asset")}
        if any(term in q for term in ["bot activeren", "deze bot activeren", "mag finn deze bot activeren", "mag deze bot live draaien"]):
            return {"action_type": "activate_bot", "subject_type": "bot", "subject_id": context.get("bot_id")}
        if any(term in q for term in ["strategie activeren", "deze strategie activeren", "mag finn deze strategie activeren"]):
            return {"action_type": "create_strategy", "subject_type": "strategy", "subject_id": context.get("strategy_id")}
        if any(term in q for term in ["setup activeren", "deze setup activeren"]):
            return {"action_type": "activate_setup", "subject_type": "setup", "subject_id": context.get("setup_id")}
        if any(term in q for term in ["bot aanmaken", "bot klaarzetten", "bot opzetten", "maak deze bot"]):
            return {"action_type": "create_bot", "subject_type": "bot", "subject_id": context.get("bot_id")}
        if any(term in q for term in ["strategie aanmaken", "strategie klaarzetten", "maak deze strategie", "maak een nieuwe strategie", "nieuwe strategie aanmaken"]):
            return {"action_type": "create_strategy", "subject_type": "strategy", "subject_id": context.get("strategy_id")}
        if any(term in q for term in ["maak een setup review klaar", "setup review klaar"]):
            return {"action_type": "setup_review", "subject_type": "setup", "subject_id": context.get("setup_id")}
        if any(term in q for term in ["setup aanmaken", "setup klaarzetten", "maak deze setup"]):
            return {"action_type": "create_setup", "subject_type": "setup", "subject_id": context.get("setup_id")}
        if any(term in q for term in ["bereid deze trade voor, maar voer hem nog niet uit", "voer hem nog niet uit"]):
            return {"action_type": "decision_review", "subject_type": "trade", "subject_id": context.get("decision_id") or context.get("bot_id")}
        if any(term in q for term in [
            "welke agents",
            "welke agenten",
            "wie moet hiernaar kijken",
            "wie moet dit reviewen",
            "voordat ik dit doe",
        ]):
            if "bot" in q:
                return {"action_type": "activate_bot", "subject_type": "bot", "subject_id": context.get("bot_id")}
            if "strategie" in q or "strategy" in q:
                return {"action_type": "create_strategy", "subject_type": "strategy", "subject_id": context.get("strategy_id")}
            if "portfolio" in q or "portefeuille" in q:
                return {"action_type": "portfolio_review", "subject_type": "portfolio", "subject_id": None}
            return {"action_type": "decision_review", "subject_type": "trade", "subject_id": context.get("decision_id") or context.get("bot_id")}
        if has_asset and any(term in q for term in [
            "trade openen",
            "long toevoegen",
            "short toevoegen",
            "extra risico toevoegen",
            "deze trade openen",
            "deze btc trade openen",
        ]):
            return {"action_type": "decision_review", "subject_type": "trade", "subject_id": context.get("decision_id") or context.get("bot_id")}
        if "portfolio" in q or "portefeuille" in q:
            return {"action_type": "portfolio_review", "subject_type": "portfolio", "subject_id": None}
        if "bot" in q:
            return {"action_type": "bot_review", "subject_type": "bot", "subject_id": context.get("bot_id")}
        if "strategie" in q or "strategy" in q:
            return {"action_type": "strategy_review", "subject_type": "strategy", "subject_id": context.get("strategy_id")}
        if "setup" in q:
            return {"action_type": "setup_review", "subject_type": "setup", "subject_id": context.get("setup_id")}
        return {"action_type": "decision_review", "subject_type": "trade", "subject_id": context.get("decision_id") or context.get("bot_id")}

    def _governed_action_context_sufficiency(
        self,
        *,
        action_type: str,
        context: Optional[Dict[str, Any]],
        decision_status: Optional[str],
    ) -> str:
        context = context or {}
        has_asset = bool(context.get("symbol") or context.get("asset") or next(iter(_asset_mentions(str(context.get("query") or ""))), None))
        has_subject = bool(context.get("setup_id") or context.get("strategy_id") or context.get("bot_id") or context.get("decision_id"))

        if action_type == "portfolio_review":
            return "sufficient"
        if action_type in {"activate_bot", "create_bot"} and (context.get("bot_id") or context.get("strategy_id") or context.get("setup_id")):
            return "sufficient"
        if action_type in {"activate_setup", "create_setup"} and (context.get("setup_id") or has_asset):
            return "sufficient"
        if action_type in {"create_strategy"} and (context.get("strategy_id") or context.get("setup_id") or has_asset):
            return "sufficient"
        if action_type in {"live_manual_order", "save_trade_plan"} and (has_asset or has_subject):
            return "sufficient" if decision_status != "insufficient_context" else "partial"
        if has_asset or has_subject:
            return "sufficient"
        return "insufficient"

    def _parse_iso_datetime(self, value: Any) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                return None
        return None

    def _state_is_fresh(self, updated_at: Any, ttl_minutes: int) -> bool:
        parsed = self._parse_iso_datetime(updated_at)
        if not parsed:
            return False
        return (_utc_now() - parsed) <= timedelta(minutes=ttl_minutes)

    def _extract_numeric_reference(self, query: str, labels: List[str]) -> Optional[int]:
        q = self._normalized_query(query)
        for label in labels:
            match = re.search(rf"\b{label}\s*#?\s*(\d+)\b", q)
            if match:
                return int(match.group(1))
        return None

    def _draft_conflicts_with_query_or_context(
        self,
        query: str,
        draft: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        context = context or {}
        draft_asset = str(draft.get("asset") or "").upper() or None
        context_asset = str(context.get("symbol") or context.get("asset") or "").upper() or None
        query_assets = _asset_mentions(query)

        if draft_asset and context_asset and draft_asset != context_asset:
            return True
        if draft_asset and len(query_assets) == 1 and query_assets[0] != draft_asset:
            return True

        draft_setup_id = draft.get("setup_id")
        if draft_setup_id and context.get("setup_id") and draft_setup_id != context.get("setup_id"):
            return True
        query_setup_id = self._extract_numeric_reference(query, ["setup", "plan"])
        if draft_setup_id and query_setup_id and draft_setup_id != query_setup_id:
            return True

        draft_strategy_id = draft.get("strategy_id") or draft.get("existing_strategy_id")
        if draft_strategy_id and context.get("strategy_id") and draft_strategy_id != context.get("strategy_id"):
            return True
        query_strategy_id = self._extract_numeric_reference(query, ["strategie", "strategy"])
        if draft_strategy_id and query_strategy_id and draft_strategy_id != query_strategy_id:
            return True

        draft_bot_id = draft.get("bot_id") or draft.get("existing_bot_id")
        if draft_bot_id and context.get("bot_id") and draft_bot_id != context.get("bot_id"):
            return True
        query_bot_id = self._extract_numeric_reference(query, ["bot"])
        if draft_bot_id and query_bot_id and draft_bot_id != query_bot_id:
            return True

        return False

    def _has_explain_intent(self, query: str) -> bool:
        q = self._normalized_query(query)
        return (
            any(phrase in q for phrase in [
            "leg uit", "uitleg", "verklaar", "waarom", "wat is", "wat doet",
            "welke", "welk", "met welke", "bekijk ik", "zie ik nu", "heb ik open", "simpele taal", "samenvat",
            "vat", "leg dit scherm uit", "wat bekijk ik nu", "wat betekent",
            ])
            or ("leg" in q and "uit" in q)
        )

    def _response_mode_for_flow(self, flow: Optional[str], draft: Optional[Dict[str, Any]] = None) -> str:
        flow = str(flow or "").lower()
        if flow in TRANSACTIONAL_FLOWS or isinstance(draft, dict):
            return "transactional"
        return "read_only"

    def _route_family_for_flow(self, flow: Optional[str], mode: str) -> str:
        flow = str(flow or "").lower()
        return ROUTE_FAMILY_BY_FLOW.get(flow, "transactional" if mode == "transactional" else "help")

    def _state_bucket_for_flow(self, flow: Optional[str]) -> str:
        flow = str(flow or "").lower()
        if flow in TRANSACTIONAL_FLOWS:
            return "transactional_state"
        if flow == "behavioral_intelligence":
            return "coaching_state"
        if flow in {"context_explain", "mission_control_explain"}:
            return "explain_state"
        return "read_only_state"

    def _append_intent_history(
        self,
        previous_state: Optional[Dict[str, Any]],
        *,
        flow: Optional[str],
        intent: Optional[str],
        mode: str,
    ) -> List[Dict[str, Any]]:
        previous_slots = (previous_state or {}).get("slots") or {}
        history = list(previous_slots.get("intent_history") or [])
        history.append(
            {
                "flow": flow,
                "intent": intent,
                "mode": mode,
                "at": _utc_now().isoformat(),
            }
        )
        return history[-INTENT_HISTORY_LIMIT:]

    def _append_recent_context_entities(
        self,
        previous_state: Optional[Dict[str, Any]],
        response: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        previous_slots = (previous_state or {}).get("slots") or {}
        recent = list(previous_slots.get("recent_context_entities") or [])
        analysis = response.get("analysis") if isinstance(response.get("analysis"), dict) else {}
        context_explain = analysis.get("context_explain") if isinstance(analysis.get("context_explain"), dict) else {}
        entity = analysis.get("entity") if isinstance(analysis.get("entity"), dict) else {}
        entity_type = context_explain.get("entity_type") or analysis.get("entity_type")
        if response.get("flow") not in {"context_explain", "mission_control_explain"} or not entity_type:
            return recent[-RECENT_CONTEXT_ENTITY_LIMIT:]

        confidence = analysis.get("context_confidence") if isinstance(analysis.get("context_confidence"), dict) else {}
        resolution = analysis.get("context_entity_resolution") if isinstance(analysis.get("context_entity_resolution"), dict) else {}
        recent.append(
            {
                "entity_type": entity_type,
                "entity_id": context_explain.get("entity_id") or entity.get("id") or confidence.get("entity_id"),
                "asset": context_explain.get("asset") or entity.get("asset") or entity.get("symbol"),
                "report_type": context_explain.get("report_type") or entity.get("table_name"),
                "page_family": entity.get("page_family"),
                "resolved_from": resolution.get("resolved_from"),
                "confidence_level": confidence.get("level"),
                "at": _utc_now().isoformat(),
            }
        )
        return recent[-RECENT_CONTEXT_ENTITY_LIMIT:]

    def _merge_last_context_entity(
        self,
        previous_state: Optional[Dict[str, Any]],
        response: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        previous_slots = (previous_state or {}).get("slots") or {}
        previous = previous_slots.get("last_context_entity")
        if not isinstance(previous, dict):
            previous = None

        analysis = response.get("analysis") if isinstance(response.get("analysis"), dict) else {}
        context_explain = analysis.get("context_explain") if isinstance(analysis.get("context_explain"), dict) else {}
        entity = analysis.get("entity") if isinstance(analysis.get("entity"), dict) else {}
        confidence = analysis.get("context_confidence") if isinstance(analysis.get("context_confidence"), dict) else {}
        resolution = analysis.get("context_entity_resolution") if isinstance(analysis.get("context_entity_resolution"), dict) else {}
        entity_type = context_explain.get("entity_type") or analysis.get("entity_type")

        # Preserve the last concrete entity-specific context across broad read-only turns.
        if response.get("flow") != "context_explain" or entity_type not in {"strategy", "setup", "bot", "report", "asset", "score"}:
            return previous

        entity_id = context_explain.get("entity_id") or entity.get("id") or confidence.get("entity_id")
        asset = context_explain.get("asset") or entity.get("asset") or entity.get("symbol")
        report_type = context_explain.get("report_type") or entity.get("table_name")

        if entity_type in {"strategy", "setup", "bot"} and not entity_id:
            return previous
        if entity_type == "report" and not report_type:
            return previous
        if entity_type in {"asset", "score"} and not asset:
            return previous

        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "asset": asset,
            "report_type": report_type,
            "page_family": entity.get("page_family"),
            "resolved_from": resolution.get("resolved_from"),
            "confidence_level": confidence.get("level"),
            "at": _utc_now().isoformat(),
        }

    def _build_response_analysis_metadata(
        self,
        response: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        *,
        route_source: str = "finn",
    ) -> Dict[str, Any]:
        context = context or {}
        analysis = response.get("analysis") if isinstance(response.get("analysis"), dict) else {}
        flow = response.get("flow") or (response.get("state") or {}).get("current_flow")
        mode = self._response_mode_for_flow(flow, response.get("draft") if isinstance(response.get("draft"), dict) else None)
        if mode == "read_only" and "context_confidence" not in analysis:
            analysis["context_confidence"] = self._context_confidence(context)
        analysis["mode"] = mode
        analysis["route_source"] = _normalized_route_source(route_source)
        analysis["route_family"] = self._route_family_for_flow(flow, mode)
        response["analysis"] = analysis
        state = response.get("state") if isinstance(response.get("state"), dict) else {}
        state_analysis = state.get("analysis") if isinstance(state.get("analysis"), dict) else {}
        state_analysis.update(analysis)
        state["analysis"] = state_analysis
        response["state"] = state
        return response

    def looks_like_general_capability_request(self, query: str) -> bool:
        q = self._normalized_query(query)
        capability_phrases = [
            "wat kun je", "waar kun je mee helpen", "hoe kun je helpen",
            "wat doe je", "hoe ondersteun", "hoe help", "waar help je mee",
        ]
        return any(phrase in q for phrase in capability_phrases) or any(
            phrase in q for phrase in GENERAL_CAPABILITY_FOLLOW_UP_PHRASES
        )

    def looks_like_product_refresh_help_request(self, query: str) -> bool:
        q = self._normalized_query(query)
        if self.looks_like_daily_score_refresh_request(query):
            return False
        return any(phrase in q for phrase in PRODUCT_REFRESH_HELP_PHRASES)

    def looks_like_product_help_request(self, query: str, context: Optional[Dict[str, Any]] = None) -> bool:
        q = self._normalized_query(query)
        context = context or {}
        if any(word in q for word in ["maak ", "aanmaken", "creeer", "creeër", "bouw", "update", "wijzig", "pas "]):
            return False
        if self.looks_like_entity_explain_request(query, context) or self.looks_like_mission_control_explain_request(query, context):
            return False
        help_phrases = [
            "wat bekijk ik nu",
            "wat is dit scherm",
            "leg dit scherm uit",
            "wat kan ik hier doen",
            "wat doet tradamind hier",
            "hoe werkt dit rapport",
            "wat kan ik met deze setup",
            "wat kan ik met deze strategie",
            "wat kan ik met deze bot",
            "wat betekent deze score",
            "wat betekent deze setup",
            "wat betekent deze strategie",
            "wat betekent deze bot",
        ]
        if any(phrase in q for phrase in help_phrases):
            return True
        page_type = str(context.get("page_type") or "").lower()
        return bool(page_type and any(phrase in q for phrase in ["hier doen", "dit scherm", "deze pagina", "bekijk ik nu"]))

    def _read_only_state_entity(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        context = context or {}
        finn_state = context.get("finn_state") if isinstance(context.get("finn_state"), dict) else {}
        analysis = finn_state.get("analysis") if isinstance(finn_state.get("analysis"), dict) else {}
        entity = analysis.get("entity") if isinstance(analysis.get("entity"), dict) else {}
        context_explain = analysis.get("context_explain") if isinstance(analysis.get("context_explain"), dict) else {}
        return {
            "entity_type": context_explain.get("entity_type") or analysis.get("entity_type"),
            "entity_id": context_explain.get("entity_id") or entity.get("id"),
            "asset": context_explain.get("asset") or entity.get("asset") or entity.get("symbol"),
            "report_type": context_explain.get("report_type") or entity.get("table_name"),
        }

    def _last_context_entity(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        context = context or {}
        finn_state = context.get("finn_state") if isinstance(context.get("finn_state"), dict) else {}
        last = finn_state.get("last_context_entity")
        if isinstance(last, dict):
            return last
        return {}

    def _recent_read_only_entities(self, context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        context = context or {}
        finn_state = context.get("finn_state") if isinstance(context.get("finn_state"), dict) else {}
        recent = finn_state.get("recent_context_entities")
        if isinstance(recent, list):
            return [item for item in recent if isinstance(item, dict)]
        return []

    def _current_page_type(self, context: Optional[Dict[str, Any]] = None) -> str:
        return str((context or {}).get("page_type") or (context or {}).get("page") or "").lower()

    def _page_family(self, context: Optional[Dict[str, Any]] = None) -> str:
        page_type = self._current_page_type(context)
        if "strategy" in page_type:
            return "strategy"
        if "setup" in page_type:
            return "setup"
        if "bot" in page_type:
            return "bot"
        if "report" in page_type:
            return "report"
        if "dashboard" in page_type:
            return "dashboard"
        return page_type or "unknown"

    def _page_supports_entity(self, context: Optional[Dict[str, Any]], entity_type: str) -> bool:
        page_type = self._current_page_type(context)
        mapping = {
            "strategy": ("strategy", "assistant"),
            "setup": ("setup", "setups", "assistant"),
            "bot": ("bot", "assistant"),
            "report": ("report", "assistant"),
            "score": ("dashboard", "score", "market", "setup", "strategy", "bot"),
            "asset": ("dashboard", "market", "setup", "strategy", "bot", "report"),
            "page": ("dashboard", "setup", "strategy", "bot", "report", "market"),
        }
        return any(token in page_type for token in mapping.get(entity_type, (entity_type,)))

    def _follow_up_context_entity_type(self, query: str, context: Optional[Dict[str, Any]] = None) -> Optional[str]:
        q = self._normalized_query(query)
        if not any(
            phrase in q for phrase in [
                "leg dit uit",
                "leg die uit",
                "leg dat uit",
                "welke is dit",
                "welke is dat",
                "wat bedoel je precies",
                "waar slaat dit op",
                "wat is dit precies",
            ]
        ):
            return None
        candidates = [
            self._read_only_state_entity(context),
            self._last_context_entity(context),
        ]
        candidates.extend(reversed(self._recent_read_only_entities(context)))
        for item in candidates:
            entity_type = str(item.get("entity_type") or "")
            if entity_type in {"strategy", "setup", "bot", "report"}:
                return entity_type
        return None

    def _resolve_context_target(
        self,
        query: str,
        context: Optional[Dict[str, Any]],
        entity_type: str,
        *,
        asset: Optional[str] = None,
    ) -> Dict[str, Any]:
        context = context or {}
        q = self._normalized_query(query)
        state_entity = self._read_only_state_entity(context)
        last_context_entity = self._last_context_entity(context)
        recent_entities = self._recent_read_only_entities(context)
        prompt_asset = next(iter(_asset_mentions(query)), None)
        context_asset = asset or prompt_asset or context.get("symbol") or context.get("asset")
        current_page_family = self._page_family(context)
        dashboard_follow_up = current_page_family in {"dashboard", "market"} and entity_type in {"strategy", "setup"}
        explicit_current_entity_follow_up = (
            entity_type in {"strategy", "setup"}
            and any(
                phrase in q for phrase in [
                    "welke strategie bekijk ik nu",
                    "welke setup heb ik nu open",
                    "welke strategie heb ik nu open",
                    "welke setup bekijk ik nu",
                    "welke strategie is dit",
                    "welke setup is dit",
                    "leg deze strategie uit",
                    "leg deze setup uit",
                    "leg die strategie uit",
                    "leg die setup uit",
                ]
            )
        )
        explicit_strategy_id = self._extract_numeric_reference(query, ["strategie", "strategy"])
        explicit_setup_id = self._extract_numeric_reference(query, ["setup", "plan"])
        explicit_bot_id = self._extract_numeric_reference(query, ["bot"])
        page_entity_id = {
            "strategy": context.get("strategy_id"),
            "setup": context.get("setup_id"),
            "bot": context.get("bot_id"),
            "report": self._report_table_from_query_or_context(query, context),
            "score": asset or prompt_asset or context.get("symbol") or context.get("asset"),
            "asset": asset or prompt_asset or context.get("symbol") or context.get("asset"),
            "page": context.get("page") or context.get("page_type"),
        }.get(entity_type)
        explicit_entity_id = {
            "strategy": explicit_strategy_id,
            "setup": explicit_setup_id,
            "bot": explicit_bot_id,
            "report": self._report_table_from_query_or_context(query, context) if any(term in q for term in ["rapport", "report"]) else None,
            "score": asset or prompt_asset,
            "asset": asset or prompt_asset,
            "page": (context.get("page") or context.get("page_type")) if any(term in q for term in ["scherm", "pagina"]) else None,
        }.get(entity_type)
        state_entity_id = {
            "strategy": state_entity.get("entity_id") if state_entity.get("entity_type") == "strategy" else None,
            "setup": state_entity.get("entity_id") if state_entity.get("entity_type") == "setup" else None,
            "bot": state_entity.get("entity_id") if state_entity.get("entity_type") == "bot" else None,
            "report": state_entity.get("report_type") if state_entity.get("entity_type") == "report" else None,
            "score": state_entity.get("asset"),
            "asset": state_entity.get("asset"),
            "page": context.get("page") or context.get("page_type"),
        }.get(entity_type)
        last_context_entity_id = {
            "strategy": last_context_entity.get("entity_id") if last_context_entity.get("entity_type") == "strategy" else None,
            "setup": last_context_entity.get("entity_id") if last_context_entity.get("entity_type") == "setup" else None,
            "bot": last_context_entity.get("entity_id") if last_context_entity.get("entity_type") == "bot" else None,
            "report": last_context_entity.get("report_type") if last_context_entity.get("entity_type") == "report" else None,
            "score": last_context_entity.get("asset"),
            "asset": last_context_entity.get("asset"),
            "page": context.get("page") or context.get("page_type"),
        }.get(entity_type)
        recent_entity = None
        for item in reversed(recent_entities):
            if item.get("entity_type") != entity_type:
                continue
            item_asset = item.get("asset")
            if (
                context_asset
                and item_asset
                and str(context_asset).upper() != str(item_asset).upper()
                and not dashboard_follow_up
                and not explicit_current_entity_follow_up
            ):
                continue
            if (
                item.get("page_family")
                and current_page_family not in {"dashboard", "market", "report", "assistant", item.get("page_family")}
                and item.get("page_family") != current_page_family
                and not explicit_current_entity_follow_up
            ):
                continue
            if not item.get("entity_id"):
                continue
            recent_entity = item
            break

        if explicit_entity_id:
            return {
                "level": "high",
                "entity_type": entity_type,
                "entity_id": explicit_entity_id,
                "reason": "explicit_context_match",
                "why": f"explicit prompt reference for {entity_type}",
            }
        if page_entity_id and self._page_supports_entity(context, entity_type):
            return {
                "level": "high",
                "entity_type": entity_type,
                "entity_id": page_entity_id,
                "reason": "page_entity_match",
                "why": f"page context matched active {entity_type}",
            }
        if page_entity_id:
            return {
                "level": "medium",
                "entity_type": entity_type,
                "entity_id": page_entity_id,
                "reason": "explicit_context_match",
                "why": f"context payload included {entity_type} without strong page confirmation",
            }
        recent_entity_reusable = self._page_supports_entity(context, entity_type) or (
            entity_type in {"strategy", "setup", "bot", "report"}
            and current_page_family in {"dashboard", "market", "report", "score", "assistant"}
            and bool(recent_entity and recent_entity.get("entity_id"))
        ) or (
            explicit_current_entity_follow_up
            and bool(recent_entity and recent_entity.get("entity_id"))
        )
        if recent_entity and recent_entity_reusable:
            recent_asset = recent_entity.get("asset")
            return {
                "level": "medium",
                "entity_type": entity_type,
                "entity_id": recent_entity.get("entity_id"),
                "reason": "state_reuse_match",
                "why": f"reused recent compatible {entity_type} context"
                + (f" for {recent_asset}" if recent_asset else ""),
            }
        last_context_entity_reusable = (
            last_context_entity.get("entity_type") == entity_type
            and bool(last_context_entity_id)
            and (
                not last_context_entity.get("asset")
                or not context_asset
                or str(last_context_entity.get("asset")).upper() == str(context_asset).upper()
                or dashboard_follow_up
                or explicit_current_entity_follow_up
            )
            and (
                not last_context_entity.get("page_family")
                or current_page_family in {"dashboard", "market", "report", last_context_entity.get("page_family")}
                or last_context_entity.get("page_family") == current_page_family
                or explicit_current_entity_follow_up
            )
        )
        if last_context_entity_reusable:
            last_asset = last_context_entity.get("asset")
            return {
                "level": "medium",
                "entity_type": entity_type,
                "entity_id": last_context_entity_id,
                "reason": "state_reuse_match",
                "why": f"reused last concrete {entity_type} context"
                + (f" for {last_asset}" if last_asset else ""),
            }
        if state_entity_id and (
            not recent_entity
            or recent_entity.get("entity_id") in (None, state_entity_id)
            or explicit_current_entity_follow_up
        ):
            return {
                "level": "medium",
                "entity_type": entity_type,
                "entity_id": state_entity_id,
                "reason": "state_reuse_match",
                "why": f"reused recent read-only {entity_type} context",
            }
        if entity_type in {"asset", "score"} and context_asset and self._page_supports_entity(context, entity_type):
            return {
                "level": "medium" if entity_type == "asset" and "dashboard" in self._current_page_type(context) else "high",
                "entity_type": entity_type,
                "entity_id": context_asset,
                "reason": "page_entity_match",
                "why": f"dashboard/context symbol matched active {entity_type}",
            }
        return {
            "level": "low",
            "entity_type": entity_type if entity_type != "asset" else "asset",
            "entity_id": None,
            "reason": "generic_fallback",
            "why": f"no confident {entity_type} context was available",
        }

    def _context_resolution_payload(
        self,
        confidence: Dict[str, Any],
        entity_type: str,
        entity: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        entity = entity or {}
        resolved_from = {
            "explicit_context_match": "explicit_prompt_or_context",
            "page_entity_match": "page_context",
            "state_reuse_match": "recent_read_only_state",
            "generic_fallback": "fallback",
        }.get(confidence.get("reason"), "fallback")
        return {
            "target": entity_type,
            "resolved_from": resolved_from,
            "resolved_asset": entity.get("asset") or entity.get("symbol"),
            "resolved_ids": {
                key: value
                for key, value in {
                    "entity_id": entity.get("id") or confidence.get("entity_id"),
                    "setup_id": entity.get("setup_id"),
                    "strategy_id": entity.get("strategy_id"),
                    "bot_id": entity.get("bot_id"),
                    "report_type": entity.get("table_name"),
                    "page": entity.get("page"),
                }.items()
                if value not in (None, "", [], {})
            },
            "fallback_used": confidence.get("level") == "low" or confidence.get("reason") == "generic_fallback",
        }

    def looks_like_education_request(self, query: str) -> bool:
        q = self._normalized_query(query)
        topics = [
            "rsi", "ma200", "ma 200", "wyckoff", "dca", "stop loss", "stoploss",
            "position sizing", "risk management", "trading plan", "niets doen",
            "even niets doen", "beter even niets doen",
        ]
        explain_terms = [
            "wat is", "leg uit", "uitleg", "verklaar", "simpele taal",
            "eenvoudig", "betekent", "hoe werkt",
        ]
        do_nothing_terms = [
            "wanneer", "beter", "niets doen", "even niets", "niet traden",
            "geen trade", "wachten",
        ]
        if any(word in q for word in ["maak ", "aanmaken", "creeer", "creeër", "bouw", "update", "pas ", "wijzig"]):
            return False
        if any(topic in q for topic in topics) and any(term in q for term in explain_terms):
            return True
        return ("niets doen" in q or "even niets" in q) and any(term in q for term in do_nothing_terms)

    def looks_like_entity_explain_request(self, query: str, context: Optional[Dict[str, Any]] = None) -> bool:
        q = self._normalized_query(query)
        context = context or {}
        page_type = str(context.get("page_type") or context.get("page") or "").lower()
        has_explain = self._has_explain_intent(query)
        if "report" in page_type and any(phrase in q for phrase in [
            "welk rapport zie ik nu",
            "welk report zie ik nu",
            "welk rapport bekijk ik nu",
            "welk report bekijk ik nu",
            "mijn rapport",
            "dit rapport",
            "dat rapport",
        ]):
            return True
        if not has_explain:
            return False
        if any(phrase in q for phrase in ["mission control", "dit scherm", "deze pagina", "wat kan ik hier doen"]):
            return False
        if context.get("setup_id") and any(term in q for term in ["setup", "plan", "open"]):
            return True
        if context.get("strategy_id") and any(term in q for term in ["strategie", "strategy", "open"]):
            return True
        if context.get("bot_id") and "bot" in q:
            return True
        if any(phrase in q for phrase in [
            "wat bekijk ik nu", "heb ik nu open", "wat zie ik nu",
            "welk rapport zie ik nu", "welk report zie ik nu",
            "met welke asset werk ik nu", "welke asset werk ik nu",
            "met welke asset en bot werk ik nu",
        ]):
            return True
        return any(term in q for term in ["setup", "strategie", "strategy", "bot", "rapport", "report", "score", "scherm", "pagina", "asset"])

    def looks_like_mission_control_explain_request(self, query: str, context: Optional[Dict[str, Any]] = None) -> bool:
        q = self._normalized_query(query)
        context = context or {}
        page_type = str(context.get("page_type") or "").lower()
        has_mc = "mission control" in q or context.get("scope") == "mission_control"
        if not has_mc and "dashboard" not in page_type:
            return False
        explain_terms = [
            "samenvat", "vat", "uitleg", "leg uit", "wat zegt", "drie bullets",
            "prioriteiten", "wat moet ik vandaag doen", "wat gebeurt hier",
        ]
        return has_mc and any(term in q for term in explain_terms)

    def _looks_like_transactional_follow_up(self, query: str, draft: Dict[str, Any]) -> bool:
        q = self._normalized_query(query)
        if self.is_cancel_request(q):
            return True
        if self.looks_like_general_capability_request(query):
            return False
        if self.looks_like_product_help_request(query, {}):
            return False
        if self.looks_like_education_request(query):
            return False
        if self.looks_like_entity_explain_request(query, {}):
            return False
        if self.looks_like_mission_control_explain_request(query, {}):
            return False
        if self.looks_like_behavioral_intelligence_request(query):
            return False
        if self.looks_like_weekly_reflection_request(query):
            return False
        if self.looks_like_outcome_memory_request(query):
            return False
        if self.looks_like_personal_performance_request(query):
            return False
        if self.looks_like_trade_journal_intelligence_request(query):
            return False
        if self.looks_like_personal_coach_request(query):
            return False
        if self.looks_like_behavioral_memory_request(query):
            return False
        if self.looks_like_finn_report_request(query):
            return False
        if self.looks_like_daily_coach_request(query):
            return False
        if self.looks_like_indicator_insight_request(query):
            return False
        if self.looks_like_status_request(query):
            return False

        if re.fullmatch(r"\s*(ja|nee|ok|prima|doe maar|bevestig|confirm|annuleer|cancel|stop|\d+)\s*", q):
            return True

        continuation_terms = {
            "bot": ["bot", "strategie", "strategy", "paper", "live", "manual", "auto", "budget", "daglimiet", "min order", "max order", "cadence", "risk", "risico"],
            "strategy": ["strategie", "strategy", "setup", "entry", "stop", "target", "basisbedrag", "base amount", "market akkoord"],
            "indicator_config": ["indicator", "macro", "technical", "node", "weging", "weight", "rule", "regel", "contrarian"],
            "plan": ["setup", "dca", "trade", "entry", "stop", "target", "wekelijks", "maandelijks", "dagelijks", "btc", "eth", "sol"],
        }
        draft_kind = draft.get("draft_kind")
        if draft_kind == "bot":
            return any(term in q for term in continuation_terms["bot"])
        if draft_kind == "strategy":
            return any(term in q for term in continuation_terms["strategy"])
        if draft_kind == "indicator_config":
            return any(term in q for term in continuation_terms["indicator_config"])
        return any(term in q for term in continuation_terms["plan"])

    def sanitize_context_for_query(self, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = dict(context or {})
        draft = payload.get("finn_draft") if isinstance(payload.get("finn_draft"), dict) else None
        if not draft:
            return payload
        finn_state = payload.get("finn_state") if isinstance(payload.get("finn_state"), dict) else {}
        current_flow = payload.get("current_flow") or finn_state.get("current_flow")
        if current_flow in TRANSACTIONAL_FLOWS and not self._state_is_fresh(
            finn_state.get("updated_at"),
            TRANSACTIONAL_STATE_TTL_MINUTES,
        ):
            payload["_finn_sanitization"] = {"draft_rejected_reason": "transactional_state_expired"}
            payload.pop("finn_draft", None)
            payload.pop("finn_state", None)
            payload.pop("current_flow", None)
            return payload
        if self._draft_conflicts_with_query_or_context(query, draft, payload):
            payload["_finn_sanitization"] = {"draft_rejected_reason": "entity_conflict_or_query_conflict"}
            payload.pop("finn_draft", None)
            payload.pop("finn_state", None)
            payload.pop("current_flow", None)
            return payload
        if self._looks_like_transactional_follow_up(query, draft):
            return payload
        payload["_finn_sanitization"] = {"draft_rejected_reason": "non_transactional_turn"}
        payload.pop("finn_draft", None)
        payload.pop("finn_state", None)
        if payload.get("current_flow") in TRANSACTIONAL_FLOWS:
            payload.pop("current_flow", None)
        return payload

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

        repo = ConversationStateRepository(self.session)
        state = await repo.get_state(user_id)
        slots = (state or {}).get("slots") or {}
        draft = slots.get("draft")
        state_updated_at = slots.get("updated_at") or (state or {}).get("updated_at")
        if state and state.get("current_flow") in TRANSACTIONAL_FLOWS and isinstance(draft, dict):
            if not self._state_is_fresh(state_updated_at, TRANSACTIONAL_STATE_TTL_MINUTES):
                await repo.clear_state(user_id)
                return hydrated
            if self._draft_conflicts_with_query_or_context("", draft, hydrated):
                await repo.clear_state(user_id)
                return hydrated
            hydrated["finn_draft"] = draft
            hydrated["finn_state"] = {
                "version": slots.get("version"),
                "updated_at": state_updated_at,
                "current_flow": state.get("current_flow"),
            }
        elif state and state.get("current_flow") == "bot_decision":
            if not self._state_is_fresh(state_updated_at, BOT_DECISION_STATE_TTL_MINUTES):
                await repo.clear_state(user_id)
                return hydrated
            bot_decision_state = slots.get("state") if isinstance(slots.get("state"), dict) else {}
            if bot_decision_state.get("pending_behavioral_memory_friction"):
                hydrated.update({
                    "current_flow": "bot_decision",
                    "asset": state.get("asset") or bot_decision_state.get("asset"),
                    "bot_id": bot_decision_state.get("bot_id"),
                    "memory_friction": bot_decision_state.get("memory_friction"),
                    "pending_behavioral_memory_friction": bot_decision_state.get("pending_behavioral_memory_friction"),
                })
        elif state and state.get("current_flow") in READ_ONLY_FLOWS:
            if not self._state_is_fresh(state_updated_at, READ_ONLY_STATE_TTL_MINUTES):
                await repo.clear_state(user_id)
                return hydrated
            hydrated["current_flow"] = state.get("current_flow")
            hydrated["finn_state"] = {
                "version": slots.get("version"),
                "updated_at": state_updated_at,
                "current_flow": state.get("current_flow"),
                "state_bucket": slots.get("state_bucket"),
                "intent_history": slots.get("intent_history") or [],
                "recent_context_entities": slots.get("recent_context_entities") or [],
                "last_context_entity": slots.get("last_context_entity") if isinstance(slots.get("last_context_entity"), dict) else {},
                "analysis": slots.get("analysis") if isinstance(slots.get("analysis"), dict) else {},
            }
        return hydrated

    async def persist_response_state(self, user_id: int, response: Dict[str, Any]) -> None:
        if not self.session:
            return
        repo = ConversationStateRepository(self.session)
        flow = response.get("flow")
        mode = self._response_mode_for_flow(flow, response.get("draft") if isinstance(response.get("draft"), dict) else None)
        stored = await repo.get_state(user_id)
        intent_history = self._append_intent_history(
            stored,
            flow=flow,
            intent=response.get("intent"),
            mode=mode,
        )
        if response.get("intent") in {"plan_creation_cancelled", "strategy_creation_cancelled", "bot_creation_cancelled", "indicator_config_cancelled"}:
            await repo.clear_state(user_id)
            return
        if response.get("flow") == "bot_decision":
            state = response.get("state") if isinstance(response.get("state"), dict) else {}
            if state.get("pending_behavioral_memory_friction") and response.get("next_question") == "behavioral_memory_ack":
                await repo.save_state(
                    user_id,
                    current_flow="bot_decision",
                    asset=state.get("asset"),
                    slots={
                        "version": FINN_STATE_VERSION,
                        "state": state,
                        "missing_fields": response.get("missing_fields", []),
                        "invalid_fields": response.get("invalid_fields", []),
                        "can_confirm": response.get("can_confirm", False),
                        "state_bucket": "transactional_state",
                        "intent_history": intent_history,
                        "updated_at": _utc_now().isoformat(),
                    },
                )
                return
            if stored and stored.get("current_flow") == "bot_decision":
                await repo.clear_state(user_id)
            return
        if response.get("flow") not in TRANSACTIONAL_FLOWS or not isinstance(response.get("draft"), dict):
            recent_context_entities = self._append_recent_context_entities(stored, response)
            last_context_entity = self._merge_last_context_entity(stored, response)
            lightweight_state = {
                "version": FINN_STATE_VERSION,
                "state_bucket": self._state_bucket_for_flow(flow),
                "intent_history": intent_history,
                "recent_context_entities": recent_context_entities,
                "last_context_entity": last_context_entity or {},
                "analysis": response.get("analysis") if isinstance(response.get("analysis"), dict) else {},
                "updated_at": _utc_now().isoformat(),
            }
            if flow in READ_ONLY_FLOWS:
                await repo.save_state(
                    user_id,
                    current_flow=flow,
                    asset=(response.get("state") or {}).get("asset") or (response.get("analysis") or {}).get("entity", {}).get("asset"),
                    slots=lightweight_state,
                )
                return
            if stored and stored.get("current_flow") in (TRANSACTIONAL_FLOWS | {"bot_decision"} | READ_ONLY_FLOWS):
                await repo.clear_state(user_id)
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
                "state_bucket": "transactional_state",
                "intent_history": intent_history,
                "updated_at": _utc_now().isoformat(),
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
        if draft and draft.get("plan_type") and self._looks_like_transactional_follow_up(query, draft):
            return True
        if draft and draft.get("draft_kind") == "strategy":
            return False
        if self.looks_like_general_capability_request(query) or self.looks_like_product_help_request(query) or self.looks_like_education_request(query) or self.looks_like_entity_explain_request(query) or self.looks_like_mission_control_explain_request(query):
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
        if draft.get("draft_kind") == "strategy" and self._looks_like_transactional_follow_up(query, draft):
            return True
        if self.looks_like_general_capability_request(query) or self.looks_like_product_help_request(query, context) or self.looks_like_education_request(query) or self.looks_like_entity_explain_request(query, context) or self.looks_like_mission_control_explain_request(query, context):
            return False
        if self.looks_like_status_request(query):
            return False
        has_strategy_word = any(word in q for word in ["strategie", "strategy"])
        has_setup_ref = bool(context.get("setup_id")) or bool(re.search(r"\bsetup\s*#?\s*\d+\b", q))
        has_strategy_ref = bool(context.get("strategy_id")) or bool(re.search(r"\bstrateg(?:ie|y)\s*#?\s*\d+\b", q))
        has_create_intent = any(word in q for word in ["maak", "aanmaken", "creeer", "creeër", "bouw", "instellen", "wil"])
        has_update_intent = any(word in q for word in ["pas", "wijzig", "update", "bijwerk", "bijwerken", "verander", "aanpassen"])
        return has_strategy_word and (has_setup_ref or has_strategy_ref or has_create_intent or has_update_intent)

    def looks_like_bot_request(self, query: str, context: Optional[Dict[str, Any]] = None) -> bool:
        q = (query or "").lower()
        context = context or {}
        draft = context.get("finn_draft") if isinstance(context.get("finn_draft"), dict) else {}
        if draft.get("draft_kind") == "bot" and self._looks_like_transactional_follow_up(query, draft):
            return True
        if self.looks_like_general_capability_request(query) or self.looks_like_product_help_request(query, context) or self.looks_like_education_request(query) or self.looks_like_entity_explain_request(query, context) or self.looks_like_mission_control_explain_request(query, context):
            return False
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
        if draft.get("draft_kind") == "indicator_config" and self._looks_like_transactional_follow_up(query, draft):
            return True
        if self.looks_like_general_capability_request(query) or self.looks_like_product_help_request(query, context) or self.looks_like_education_request(query) or self.looks_like_entity_explain_request(query, context) or self.looks_like_mission_control_explain_request(query, context):
            return False
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
        portfolio_risk_terms = [
            "grootste portfolio risico", "grootste risico", "portfolio risico",
            "portefeuille risico", "portfolio exposure", "te veel exposure",
            "risico per asset", "welke asset vraagt", "welke assets vragen",
            "welke assets moet ik vandaag negeren", "welke asset moet ik vandaag negeren",
            "welke assets laat ik vandaag liggen", "welke asset laat ik vandaag liggen",
            "welke assets negeren", "assets negeren", "assets laten liggen",
            "welke live bots botsen", "live bots botsen", "live bots conflict",
            "live bot conflict", "welke live bots vragen review",
            "welke bots stapelen", "welke plannen stapelen", "stapelen risico",
            "welke setups conflicteren", "conflicterende setups", "bots met overlappende budgetten",
            "overlappende budgetten", "dca en trade",
        ]
        if any(term in q for term in portfolio_risk_terms):
            return True
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
            "portfolio", "portefeuille", "asset", "assets", "exposure", "risico",
        ])
        return has_today and (has_decision_intent or has_trading_context or "kopen" in q)

    def looks_like_behavioral_intelligence_request(self, query: str) -> bool:
        q = (query or "").lower()
        explicit_behavioral_questions = [
            "overtrade ik",
            "ben ik aan het overtraden",
            "handel ik te impulsief",
            "ben ik te impulsief",
            "neem ik te vroeg winst",
            "pak ik te vroeg winst",
            "stap ik te laat uit",
            "laat ik winnaars te vroeg los",
            "laat ik verliezers te lang lopen",
        ]
        if any(term in q for term in explicit_behavioral_questions):
            return True
        behavioral_terms = [
            "discipline", "gedrag", "behavior", "behaviour", "fomo", "revenge",
            "impulsief", "impulsieve", "emotie", "emotioneel", "overtrade",
            "overtrading", "afwijk", "wijk af", "wijk ik af", "buiten mijn plan",
            "buiten mijn strategie", "toch instappen", "plan gevolgd", "trading gedrag",
            "heb ik mijn plan", "weekreflectie", "reflectie", "patroon", "patronen",
            "all-in", "all in", "bang", "twijfel", "twijfelachtig", "panic", "paniek",
            "jagen", "forceren", "te groot", "te veel risico", "emotionele beslissing",
            "geen goed gevoel", "dit voelt niet goed", "geen helder plananker",
            "toch doen", "alsnog instappen", "override", "regels loslaten",
            "afwijken", "afwijking", "ik durf niet", "emotionele druk",
            "gefrustreerd", "gemiste move", "ik baal", "ik wil het terugpakken",
            "ik moet nu iets doen", "ik wil nu handelen omdat",
            *OVERTRADING_DIRECT_COACH_TERMS,
        ]
        coaching_terms = [
            "hoe", "zie", "check", "controleer", "analyseer", "waar", "wat zegt",
            "spiegel", "coach", "ben ik", "heb ik", "wijk", "wat moet ik doen",
            "nu doen", "wat nu", "help me", "moet ik", "zal ik", "denk eraan",
        ]
        hard_override_terms = [
            "wat moet ik doen", "wat nu", "moet ik", "zal ik", "help me",
            "ik wil toch", "ik wil mijn regels", "ik wil buiten mijn plan",
            "ik wil afwijken", "ik heb er geen goed gevoel bij", "dit voelt niet goed",
            "ik wil nu handelen omdat", "ik wil het terugpakken", "ik moet nu iets doen",
            "ik wil weer handelen", "ik wil opnieuw handelen", "nog een trade", "weer een trade",
        ]
        return any(term in q for term in behavioral_terms) and (
            any(term in q for term in coaching_terms) or any(term in q for term in hard_override_terms)
        )

    def _behavioral_variant_for_query(self, query: str) -> str:
        q = self._normalized_query(query)
        plan_adherence_terms = [
            "ik wijk af van mijn strategie",
            "ik wijk af van mijn plan",
            "ik wil buiten mijn plan handelen",
            "ik wil buiten mijn strategie handelen",
            "ik wil afwijken",
            "ik wil toch afwijken",
            "ik wil toch instappen",
            "ik wil toch kopen",
            "ik wil toch traden",
            "ik wil nu toch instappen",
            "ik wil toch doen",
            "ik wil alsnog instappen",
            "ik wil mijn plan negeren",
            "ik wil mijn regels loslaten",
            "ik wijk af",
            "buiten mijn plan",
            "buiten mijn strategie",
        ]
        direct_coach_terms = [
            "fomo", "all-in", "all in", "paniek", "panic", "revenge",
            "impuls", "nu toch instappen", "moet ik nu", "denk eraan",
            "ik wil nu", "ik wil kopen", "ik wil verkopen", "ik wil sellen",
            "ik wil instappen", "emotionele beslissing", "emotioneel",
            "geen goed gevoel", "ik twijfel", "ik durf niet", "ik ben bang",
            "toch doen", "alsnog instappen", "dit voelt niet goed",
            "geen helder plananker", "twijfel om dit te doen",
            "gefrustreerd", "gemiste move", "ik baal", "ik wil het terugpakken",
            "ik moet nu iets doen", "ik wil nu handelen omdat",
            *OVERTRADING_DIRECT_COACH_TERMS,
        ]
        if any(term in q for term in plan_adherence_terms):
            return "plan_adherence_coach"
        if any(term in q for term in direct_coach_terms):
            return "direct_coach"
        return "behavioral_reflection"

    def looks_like_weekly_reflection_request(self, query: str) -> bool:
        q = (query or "").lower()
        weekly_terms = [
            "weekreflectie", "week reflectie", "weekly reflection", "weekrapport",
            "week rapport", "week review", "weekoverzicht", "afgelopen week",
            "laatste 7 dagen", "7 dagen", "deze week",
        ]
        reflection_terms = [
            "geef", "maak", "toon", "hoe", "reflectie", "review", "rapport",
            "samenvatting", "gedrag", "discipline", "patroon", "patronen",
        ]
        return any(term in q for term in weekly_terms) and any(term in q for term in reflection_terms)

    def looks_like_finn_report_request(self, query: str) -> bool:
        q = (query or "").lower()
        finn_terms = [
            "finn rapport", "finn-report", "finn report", "rapport van finn",
            "finn verslag", "operator rapport", "operator report", "discipline rapport",
            "risk officer rapport", "guardrail rapport", "wat heeft finn geblokkeerd",
            "wat heeft finn vandaag gedaan", "wat heb ik vandaag met finn gedaan",
            "dagafsluiting", "dag afsluiting", "einde dag", "sluit mijn dag af",
            "waar week ik af", "waar wijk ik af", "waar week ik af vandaag",
            "waar wijk ik af vandaag", "waar week ik af met finn", "waar wijk ik af met finn",
        ]
        report_terms = [
            "rapport", "verslag", "samenvatting", "overzicht", "afsluiting",
            "geblokkeerd", "afgeremd", "overrides", "afwijkingen", "skips",
            "snoozes", "guardrails", "finn acties", "week ik af", "wijk ik af",
            "wat heb ik gedaan", "wat deed finn", "geborgd", "afremde",
        ]
        return any(term in q for term in finn_terms) or ("finn" in q and any(term in q for term in report_terms))

    def looks_like_behavioral_memory_request(self, query: str) -> bool:
        q = (query or "").lower()
        memory_terms = [
            "lange termijn", "lange-termijn", "long term", "long-term", "memory",
            "geheugen", "onthoud", "onthouden", "gedragsrapport", "behavioral report",
            "maandreflectie", "maand reflectie", "30 dagen", "laatste 30 dagen",
            "persoonlijk profiel", "gedragsprofiel", "trading profiel",
        ]
        behavior_terms = [
            "gedrag", "discipline", "fomo", "overtrading", "override", "afwijk",
            "patroon", "patronen", "bot-decision", "decision", "plan",
        ]
        report_terms = ["geef", "maak", "toon", "wat", "hoe", "analyseer", "rapport", "reflectie", "profiel"]
        return any(term in q for term in memory_terms) and (
            any(term in q for term in behavior_terms) or any(term in q for term in report_terms)
        )

    def looks_like_outcome_memory_request(self, query: str) -> bool:
        q = self._normalized_query(query)
        explicit_terms = [
            "wat onthoudt finn van mijn uitkomsten",
            "welk gedrag kost me de laatste maand het meeste",
            "welke uitkomstpatronen ziet finn",
            "welk patroon blijft terugkomen in mijn uitkomsten",
            "wat blijft zich herhalen in mijn resultaten",
            "wat zegt mijn historie over mijn gedrag",
            "welke fouten blijven terugkomen",
            "welke patronen blijven me geld kosten",
            "wat onthoudt finn van mijn laatste fouten",
            "wat leert mijn historie over mijn gedrag",
            "wat zie je terugkeren in mijn verliestrades",
            "wat keert terug in mijn verliestrades",
            "welke fout keert terug in mijn verliestrades",
        ]
        if any(term in q for term in explicit_terms):
            return True
        has_memory = any(term in q for term in [
            "onthoudt finn",
            "outcome memory",
            "uitkomst geheugen",
            "historie",
            "blijft terugkomen",
            "herhalen",
        ])
        has_outcome = any(term in q for term in [
            "uitkomst",
            "uitkomsten",
            "resultaat",
            "resultaten",
            "fouten",
            "gedrag",
            "verlies",
            "winst",
        ])
        has_recurrence = any(term in q for term in [
            "terugkeren",
            "terugkomt",
            "blijft terugkomen",
            "herhalen",
            "herhaalt",
            "patroon",
            "fouten",
        ])
        has_loss_focus = any(term in q for term in [
            "verliestrades",
            "verlies trades",
            "verliezen",
            "drawdown",
            "geld kosten",
        ])
        if has_recurrence and has_loss_focus:
            return True
        return has_memory and has_outcome

    def looks_like_personal_performance_request(self, query: str) -> bool:
        q = self._normalized_query(query)
        if any(term in q for term in [
            "word ik beter of slechter",
            "ben ik beter of slechter",
            "mijn grootste performance lek",
            "mijn grootste persoonlijke performance lek",
            "volgende beste coachregel",
        ]):
            return False
        explicit_terms = [
            "hoe goed trade ik eigenlijk",
            "hoe handel ik eigenlijk",
            "geef mijn persoonlijke performance",
            "geef mijn performance score",
            "wat is mijn performance score",
            "hoe ziet mijn performance eruit",
            "hoe goed is mijn discipline en follow through",
            "hoe goed is mijn discipline en follow-through",
            "hoe goed trade ik de laatste 30 dagen",
            "wat zegt finn over mijn trading kwaliteit",
            "hoe sterk is mijn persoonlijke trading performance",
        ]
        if any(term in q for term in explicit_terms):
            return True
        performance_terms = [
            "performance", "kwaliteit", "score", "quality", "groei", "groeidoel",
            "follow through", "follow-through", "selectiviteit", "patience", "geduld",
            "herstel", "recovery", "discipline", "trading kwaliteit",
        ]
        self_terms = ["mijn", "ik", "persoonlijke", "persoonlijk", "hoe goed", "hoe sterk"]
        return (
            any(term in q for term in performance_terms)
            and any(term in q for term in self_terms)
            and not self.looks_like_weekly_reflection_request(query)
        )

    def _is_lightweight_personal_performance_prompt(self, query: str) -> bool:
        q = self._normalized_query(query)
        return any(term in q for term in [
            "geef mijn performance score",
            "wat is mijn performance score",
            "hoe goed trade ik de laatste 30 dagen",
            "wat zegt finn over mijn trading kwaliteit",
            "waar verlies ik het meeste discipline",
            "waar verlies ik het meest discipline",
            "hoe sterk is mijn persoonlijke trading performance",
        ])

    def looks_like_trade_journal_intelligence_request(self, query: str) -> bool:
        q = self._normalized_query(query)
        explicit_terms = [
            "wat leert mijn trade journal",
            "wat ziet finn in mijn trade journal",
            "wat staat er tussen mijn trade notes",
            "wat zegt mijn journal over mijn trades",
            "haal intelligence uit mijn trade journal",
            "welke patronen zitten in mijn notities",
            "wat leren mijn post trade notities",
            "wat leert mijn dagboek over mijn trades",
            "welke les moet ik uit mijn laatste trades trekken",
            "welke les haal ik uit mijn laatste trades",
            "wat leren mijn laatste trades me",
            "wat leren mijn verliestrades me",
            "welke terugkerende fout zit in mijn laatste trades",
        ]
        if any(term in q for term in explicit_terms):
            return True
        journal_terms = [
            "journal", "dagboek", "notities", "note", "notes",
            "trade note", "trade notes", "trade journal", "post trade",
            "post-trade", "reviewnotities", "reflectienotities",
        ]
        trade_review_terms = [
            "mijn laatste trades",
            "mijn trades",
            "verliestrades",
            "laatste trades",
            "trade review",
            "trades review",
        ]
        intelligence_terms = [
            "patroon", "patronen", "intelligence", "inzichten", "lesson",
            "les", "wat zegt", "wat leert", "analyseer", "samenvat",
            "welke fout", "welke emotie", "thesis",
        ]
        return (
            (any(term in q for term in journal_terms) and any(term in q for term in intelligence_terms))
            or (any(term in q for term in trade_review_terms) and any(term in q for term in intelligence_terms))
        )

    def looks_like_personal_coach_request(self, query: str) -> bool:
        q = self._normalized_query(query)
        if any(term in q for term in [
            "waar verlies ik het meeste discipline",
            "waar verlies ik het meest discipline",
        ]):
            return False
        explicit_terms = [
            "coach me op basis van mijn laatste fouten",
            "coach me persoonlijk",
            "wees mijn persoonlijke trading coach",
            "wat is mijn grootste persoonlijke performance lek",
            "wat moet ik nu in mezelf onderbreken",
            "welk patroon moet ik nu doorbreken",
            "hoe coach jij mij nu het beste",
            "wat is mijn volgende beste coachregel",
            "wat is mijn grootste performance lek",
            "word ik beter of slechter als trader",
            "word ik beter of slechter",
            "ben ik beter of slechter aan het worden",
        ]
        if any(term in q for term in explicit_terms):
            return True
        coach_terms = ["coach", "coaching", "patroon", "discipline", "fouten", "lek", "doorbreken", "onderbreken", "persoonlijk"]
        guidance_terms = ["wat moet ik", "help me", "hoe", "welk", "waar", "op basis van", "nu", "beste"]
        return any(term in q for term in coach_terms) and any(term in q for term in guidance_terms)

    def _is_lightweight_personal_coach_prompt(self, query: str) -> bool:
        q = self._normalized_query(query)
        return any(term in q for term in [
            "word ik beter of slechter",
            "ben ik beter of slechter",
            "aan het worden",
            "mijn grootste performance lek",
            "mijn grootste persoonlijke performance lek",
            "mijn volgende beste coachregel",
            "wat is mijn volgende beste coachregel",
            "coach me op basis van mijn laatste fouten",
        ])

    def looks_like_daily_score_refresh_request(self, query: str) -> bool:
        q = (query or "").lower()
        if any(phrase in q for phrase in [
            "ververs daily score", "ververs daily scores", "refresh daily score",
            "refresh daily scores", "genereer daily score", "genereer daily scores",
            "daily score opnieuw", "daily scores opnieuw", "scores opnieuw genereren",
            "scores verversen",
        ]):
            return True
        has_refresh_verb = any(term in q for term in ["ververs", "refresh", "genereer opnieuw", "opnieuw genereer"])
        has_score_target = (
            "daily score" in q
            or "daily scores" in q
            or ("scores" in q and "daily" in q)
        )
        return has_refresh_verb and has_score_target

    def looks_like_bot_decision_request(self, query: str) -> bool:
        q = (query or "").lower()
        has_bot = "bot" in q
        has_decision = any(word in q for word in ["decision", "beslissing", "proposal", "voorstel"])
        has_generate = any(word in q for word in ["maak", "genereer", "bereid", "draai", "run", "laat"])
        return has_bot and has_decision and has_generate

    def looks_like_bot_decision_review_request(self, query: str) -> bool:
        q = (query or "").lower()
        has_decision = any(word in q for word in ["bot-decision", "bot decision", "decision", "beslissing", "proposal", "voorstel"])
        has_review = any(word in q for word in ["leg", "uitleg", "waarom", "review", "beoordeel", "controleer"])
        return has_decision and has_review

    def looks_like_bot_execution_decision_request(self, query: str) -> bool:
        q = (query or "").lower()
        has_decision = any(word in q for word in ["bot-decision", "bot decision", "decision", "beslissing", "proposal", "voorstel"])
        has_execution_choice = any(phrase in q for phrase in [
            "sla over", "sla bot-decision", "sla decision", "overslaan", "skip", "monitor", "alleen monitoren",
            "paper uitvoeren", "paper execute", "voer paper", "paper uit", "uitvoeren",
            "markeer uitgevoerd", "live preflight", "live check", "live uitvoeren",
        ])
        return has_decision and has_execution_choice

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

    def looks_like_plan_adherence_review_request(self, query: str) -> bool:
        q = self._normalized_query(query)
        rule_terms = [
            "wijk ik af van mijn plan",
            "wijk ik af van mijn strategie",
            "handel ik buiten mijn plan",
            "handel ik buiten mijn strategie",
            "breek ik mijn regels",
            "breek ik hier mijn plan",
            "past dit nog bij mijn plan",
            "past dit nog bij mijn strategie",
            "volg ik mijn plan",
            "ga ik nu buiten mijn plan",
            "ga ik nu buiten mijn strategie",
            "override ik mijn plan",
            *PLAN_ADHERENCE_HARD_OVERRIDE_TERMS,
        ]
        if any(term in q for term in rule_terms):
            return True
        has_breach_action = any(term in q for term in [
            "stop-loss verwijderen",
            "stop loss verwijderen",
            "grotere positie",
            "positie vergroten",
            "meer risico",
            "wachten maar ik wil kopen",
            "wachten maar ik wil instappen",
            "toch kopen",
            "toch instappen",
        ])
        has_plan_boundary = any(term in q for term in [
            "plan",
            "strategie",
            "regels",
            "stop-loss",
            "stop loss",
            "positie",
            "risico",
        ])
        return has_breach_action and has_plan_boundary

    def looks_like_outcome_tracking_request(self, query: str) -> bool:
        q = self._normalized_query(query)
        outcome_terms = [
            "hoe pakte dat uit",
            "hoe pakten die beslissingen uit",
            "wat leert finn van mijn uitkomsten",
            "wat leverden mijn planafwijkingen op",
            "welke patronen kosten me geld",
            "wat kost dit gedrag me",
            "historisch resultaat",
            "uitkomst van mijn gedrag",
            "uitkomst van mijn beslissingen",
            "hoe eindigen mijn overrides",
            "hoe eindigen mijn planafwijkingen",
            "laatste keren dat ik afweek",
        ]
        if any(term in q for term in outcome_terms):
            return True
        has_historical_counts = bool(re.search(r"\b\d+\s+(?:fomo\s+)?trades?\b", q)) and (
            bool(re.search(r"\b\d+\s+winst(?:trades?)?\b", q))
            or bool(re.search(r"\b\d+\s+verlies(?:trades?)?\b", q))
            or "gemiddeld resultaat" in q
        )
        has_behavior_pattern = any(term in q for term in [
            "fomo",
            "override",
            "planafwijk",
            "afweek",
            "afwijk",
            "gedrag",
            "uitkomst",
            "historisch",
        ])
        return has_historical_counts and has_behavior_pattern

    def looks_like_portfolio_intelligence_request(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        q = self._normalized_query(query)
        context = context or {}
        direct_trade_review_cues = [
            "beoordeel deze trade",
            "review deze trade",
            "controleer deze trade",
            "moet ik deze trade openen",
            "kan ik deze trade openen",
            "mag ik deze trade openen",
            "zou jij dit doen",
            "zou je dit doen",
            "zou jij dit openen",
            "zou je dit openen",
            "wat vind je van deze trade",
            "wat vind je van dit trade idee",
            "waarom blokkeer je deze trade",
        ]
        if any(phrase in q for phrase in direct_trade_review_cues):
            return False
        phrases = [
            "heb ik te veel exposure",
            "wat is mijn portfolio risico",
            "wat is mijn portefeuille risico",
            "hoe geconcentreerd is mijn portfolio",
            "hoe geconcentreerd is mijn portefeuille",
            "mag ik extra btc risico toevoegen",
            "mag ik extra exposure toevoegen",
            "welke asset stapelt risico",
            "welke assets stapelen risico",
            "welke trade is lokaal goed maar globaal slecht",
            "wat blokkeert mij op portefeuilleniveau",
            "wat is mijn grootste portfolio risico",
            "waar zit mijn concentratierisico",
            "voeg ik nu te veel geconcentreerd risico toe",
            "kan ik nog een btc long openen",
            "kan ik nog meer btc risico nemen",
            "mag ik nog meer btc risico nemen",
            "waar zit mijn grootste exposure",
            "waar stapelt mijn risico",
        ]
        if any(phrase in q for phrase in phrases):
            return True
        explicit_mix = re.findall(
            r"(?:"
            r"(\d+(?:[.,]\d+)?)\s*%\s*(btc|eth|sol|doge|xrp|ada|bnb|avax|link|matic|pepe|cash)"
            r"|"
            r"(btc|eth|sol|doge|xrp|ada|bnb|avax|link|matic|pepe|cash)\s*(\d+(?:[.,]\d+)?)\s*%"
            r")",
            q,
        )
        if explicit_mix and any(term in q for term in [
            "kan ik",
            "mag ik",
            "nog een",
            "extra",
            "toevoegen",
            "openen",
            "long",
            "risico",
        ]):
            return True
        has_portfolio = any(term in q for term in [
            "portfolio", "portefeuille", "allocatie", "allocation", "exposure", "concentratie", "overgewicht",
        ])
        has_judgment = any(term in q for term in [
            "risico", "blokkeert", "veilig", "toevoegen", "concentratie", "stapelt", "te veel", "extra btc",
            "extra exposure", "long openen", "grootste",
        ])
        return has_portfolio and has_judgment and bool(context.get("symbol") or context.get("asset") or context.get("page"))

    def looks_like_priority_engine_request(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        q = self._normalized_query(query)
        phrases = [
            "wat is vandaag mijn hoogste prioriteit",
            "wat moet ik vandaag eerst doen",
            "wat moet ik nu eerst doen",
            "waar moet ik nu op focussen",
            "waar moet ik vandaag op focussen",
            "wat is nu het belangrijkste",
            "geef mijn prioriteiten",
            "geef mijn top prioriteiten",
            "wat moet ik eerst reviewen",
            "wat is mijn review queue",
            "welke acties moet ik vandaag doen",
            "wat kan ik vandaag negeren",
            "wat moet ik vandaag laten liggen",
            "waar begin ik vandaag",
            "wat verdient nu mijn aandacht",
            "wat is vandaag het belangrijkst",
            "wat zijn vandaag mijn 3 belangrijkste acties",
            "waar moet ik mee beginnen",
            "wat moet ik juist niet doen",
            "wat zijn vandaag mijn topprioriteiten",
            "help me even kiezen wat ik nu moet doen",
        ]
        if any(phrase in q for phrase in phrases):
            return True
        context = context or {}
        has_priority = any(term in q for term in [
            "prioriteit",
            "prioriteiten",
            "focus",
            "focuspunten",
            "review queue",
            "reviewqueue",
            "do now",
            "ignore today",
            "wat moet ik eerst",
            "wat verdient eerst aandacht",
            "wat kan wachten",
            "kan vandaag wachten",
            "waar begin ik",
            "waar focus ik op",
            "wat eerst doen",
            "wat laat ik liggen",
            "wat laat ik vandaag liggen",
            "hoogste prioriteit",
            "belangrijkste acties",
            "mee beginnen",
            "juist niet doen",
            "niet doen",
            "topprioriteiten",
            "kiezen wat ik nu moet doen",
        ])
        has_mc = "mission control" in q or context.get("scope") == "mission_control" or context.get("page") == "mission_control"
        return has_priority and (
            has_mc
            or "vandaag" in q
            or "nu" in q
            or "eerst" in q
            or "wachten" in q
            or "liggen" in q
            or "aandacht" in q
        )

    def looks_like_portfolio_operating_system_request(self, query: str) -> bool:
        q = self._normalized_query(query)
        phrases = [
            "geef mijn portfolio operating system",
            "geef mijn trading operating system",
            "hoe staat mijn portfolio operating system ervoor",
            "hoe ziet mijn trading operating system eruit",
            "geef mijn finn governance laag",
            "hoe staat mijn portfolio control plane ervoor",
            "geef mijn portfolio os status",
            "geef mijn operating layer",
            "geef mijn operating system status",
        ]
        return any(phrase in q for phrase in phrases)

    def looks_like_governed_action_review_request(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        q = self._normalized_query(query)
        context = context or {}
        asset_mentions = _asset_mentions(query)
        phrases = [
            "mag finn deze strategie activeren",
            "mag finn deze bot activeren",
            "kan finn deze bot voor me klaarzetten",
            "kun je deze bot voor me klaarzetten",
            "mag dit live uitgevoerd worden",
            "welke bevestiging is hiervoor nodig",
            "waarom blokkeer je deze actie",
            "welke context mist nog voor uitvoering",
            "mag deze actie uitgevoerd worden",
            "is deze actie toegestaan",
            "mag dit uitgevoerd worden",
            "welke governance geldt hier",
            "ik wil deze btc trade openen, mag dat",
            "maak een nieuwe strategie aan",
            "welke agents moeten hiernaar kijken voordat ik dit doe",
            "plaats nu direct een live btc order",
            "maak een setup review klaar",
            "bereid deze trade voor, maar voer hem nog niet uit",
            "plaats deze trade live",
            "verwijder mijn stop-loss",
            "actieveer deze bot zonder bevestiging",
            "activeer deze bot zonder bevestiging",
            "negeer mijn risk limit en open toch",
            "voer deze trade uit, ik bevestig later wel",
            "wat wordt hiervan gelogd",
            "kan ik later zien waarom finn dit advies gaf",
            "welke confirmation is nodig",
            "is deze trade veilig voor mijn portfolio",
            "bot a en bot b zitten allebei btc long, is dat een probleem",
            "welke portfolio-conflicten zie je",
            "laat risk en strategy deze trade beoordelen",
            "wat zegt performance history over deze actie",
            "welke laag blokkeert deze actie",
        ]
        if any(phrase in q for phrase in phrases):
            return True
        has_action = any(term in q for term in [
            "activeren",
            "uitvoeren",
            "klaarzetten",
            "aanmaken",
            "opslaan",
            "bevestiging",
            "confirm",
            "uitvoering",
            "actie",
            "openen",
            "plaatsen",
            "toevoegen",
            "live zetten",
            "zonder bevestiging",
        ])
        has_governance = any(term in q for term in [
            "mag",
            "toegestaan",
            "governance",
            "geblokkeerd",
            "blokkeer",
            "waarom niet",
            "wat mist nog",
            "welke context",
            "zonder bevestiging",
            "bevestigen",
            "direct",
            "live",
            "welke agents",
            "welke agenten",
            "voordat ik dit doe",
            "gelogd",
            "audit",
            "trace",
            "waarom finn",
            "confirmation",
            "veilig voor mijn portfolio",
            "probleem",
            "blokkeert",
        ])
        has_subject = any(term in q for term in [
            "setup",
            "strategie",
            "strategy",
            "bot",
            "trade plan",
            "live order",
            "live trade",
            "portfolio",
            "portefeuille",
            "order",
            "positie",
            "long",
            "short",
            "btc",
            "eth",
        ]) or bool(context.get("setup_id") or context.get("strategy_id") or context.get("bot_id") or asset_mentions)
        has_portfolio_conflict = any(term in q for term in [
            "extra btc risico",
            "btc long toevoegen",
            "te veel exposure",
            "concentratie",
            "correlated risk",
            "correlated exposure",
            "bot stacking",
            "setup clustering",
            "cashbuffer",
        ])
        has_execution_intent = any(term in q for term in [
            "mag ik",
            "mag dat",
            "plaats",
            "uitvoeren",
            "zet live",
            "zonder bevestiging",
            "nu direct",
            "maak",
            "activeer",
        ])
        if has_portfolio_conflict and (has_execution_intent or bool(asset_mentions)):
            return True
        if any(term in q for term in ["welke agents", "welke agenten", "wie moet hiernaar kijken", "wie moet dit reviewen"]):
            return True
        if any(term in q for term in ["wat wordt hiervan gelogd", "kan ik later zien waarom finn dit advies gaf", "welke confirmation is nodig", "welke bevestiging is hiervoor nodig"]):
            return True
        if any(term in q for term in ["live order", "live trade", "plaats nu direct", "zet live"]) and (has_subject or bool(asset_mentions)):
            return True
        return has_action and has_governance and has_subject

    def _is_lightweight_governance_prompt(self, query: str) -> bool:
        q = self._normalized_query(query)
        return any(term in q for term in [
            "wat wordt hiervan gelogd",
            "kan ik later zien waarom finn dit advies gaf",
            "welke confirmation is nodig",
            "welke bevestiging is hiervoor nodig",
            "welke agents",
            "welke agenten",
            "wie moet hiernaar kijken",
            "wat zegt performance history over deze actie",
            "welke laag blokkeert deze actie",
            "maak een setup review klaar",
            "maak een nieuwe strategie aan",
            "bereid deze trade voor, maar voer hem nog niet uit",
            "plaats deze trade live",
            "plaats nu direct een live btc order",
            "plaats nu direct een live order",
            "live btc order",
            "verwijder mijn stop-loss",
            "extra risico toevoegen",
            "extra btc risico toevoegen",
            "nog een btc long toevoegen",
            "kan ik nog een btc long openen",
        ])

    def _lightweight_governance_snapshot(
        self,
        *,
        query: str,
        context: Optional[Dict[str, Any]],
        action: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        q = self._normalized_query(query)
        context = context or {}
        asset = self._asset_from_query_or_context(query, context)
        decision_analysis: Dict[str, Any] = {}
        adherence_analysis: Dict[str, Any] = {}
        portfolio_analysis: Dict[str, Any] = {}

        if action.get("action_type") == "live_manual_order":
            decision_analysis = {
                "decision_status": "modify",
                "risk_summary": "Live execution blijft read-only tot confirmatie en guardrails rond zijn.",
                "operator_next_step": "Gebruik eerst confirm + audit in plaats van directe uitvoering.",
            }

        if any(term in q for term in ["verwijder mijn stop-loss", "haal mijn stop-loss weg", "zonder stop-loss"]):
            adherence_analysis = {
                "adherence_status": "forced_override",
                "threatened_rule": "Je haalt je vooraf afgesproken exit-grens weg.",
                "suggested_recovery_step": "Laat de stop-loss staan of verlaag eerst je exposure voordat je iets wijzigt.",
            }

        if any(term in q for term in ["extra risico toevoegen", "extra btc risico toevoegen", "nog een btc long toevoegen", "kan ik nog een btc long openen"]):
            focus_asset = str(asset or "dezelfde asset").upper() if asset else "dezelfde asset"
            portfolio_analysis = {
                "concentration_warning": (
                    f"Extra {focus_asset}-risico toevoegen stapelt concentratie in dezelfde asset."
                ),
                "stacked_risk_warning": (
                    f"{focus_asset} krijgt nu een extra exposure-laag voordat de bestaande risk stack is afgebouwd."
                ),
                "portfolio_blockers": [
                    f"Voeg nu geen extra {focus_asset}-risico toe zonder eerst bestaande exposure of open risk stack af te bouwen."
                ],
                "portfolio_safe_alternative": (
                    "Verlaag eerst bestaande exposure of kies een niet-gestapelde trade voordat je nieuw risico toevoegt."
                ),
            }

        return {
            "decision_analysis": decision_analysis,
            "adherence_analysis": adherence_analysis,
            "portfolio_analysis": portfolio_analysis,
        }

    def _governed_action_required_agents(
        self,
        *,
        action_type: str,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        context = context or {}
        q = self._normalized_query(query)
        agents: List[Dict[str, str]] = []

        def add(name: str, role: str) -> None:
            if not any(existing.get("name") == name for existing in agents):
                agents.append({"name": name, "role": role})

        if action_type in {"decision_review", "live_manual_order", "portfolio_rebalance", "portfolio_review"}:
            add("Risk Agent", "Controleert risico, sizing en execution-frictie.")
            add("Portfolio Agent", "Controleert exposure, concentratie en correlatierisico.")
        if action_type in {"decision_review", "activate_bot", "activate_setup", "save_trade_plan", "portfolio_rebalance"}:
            add("Discipline Agent", "Controleert planfit, overrides en gedragsfrictie.")
        if action_type in {"create_strategy", "strategy_review", "create_setup", "setup_review", "create_bot", "bot_review"}:
            add("Strategy Agent", "Controleert of de actie logisch past bij setup, strategie en structuur.")
        if action_type in {"live_manual_order", "activate_bot", "portfolio_rebalance"}:
            add("Execution Agent", "Controleert of uitvoering alleen onder bevestiging en guardrails kan.")
        if context.get("bot_id") or action_type in {"activate_bot", "bot_review", "create_bot"}:
            add("Bot Agent", "Controleert bot-specific context, status en live readiness.")
        if any(term in q for term in ["performance history", "performance", "historie", "eerdere uitkomsten"]):
            add("Performance Agent", "Controleert of eerdere uitkomsten extra frictie of waarschuwingen geven.")
        return agents[:4]

    def looks_like_decision_review_request(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        q = self._normalized_query(query)
        context = context or {}
        if self.looks_like_plan_adherence_review_request(query):
            return False
        if self.looks_like_bot_decision_review_request(query):
            return False
        review_terms = [
            "beoordeel deze trade",
            "review deze trade",
            "controleer deze trade",
            "wat vind je van deze trade",
            "wat vind je van dit trade idee",
            "ik wil deze trade openen",
            "ik wil deze trade nemen",
            "kan ik deze trade openen",
            "mag ik deze trade openen",
            "moet ik deze trade openen",
            "kan ik deze trade nemen",
            "mag ik deze trade nemen",
            "is dit een goede trade",
            "past dit bij mijn strategie",
            "past deze trade bij mijn strategie",
            "past deze setup bij mijn strategie",
            "beoordeel deze setup",
            "beoordeel deze strategie",
            "review deze setup",
            "review deze strategie",
            "waarom blokkeer je deze trade",
            "trade review",
            "decision review",
            "zou jij dit doen",
            "zou je dit doen",
            "zou jij dit openen",
            "zou je dit openen",
        ]
        if any(term in q for term in review_terms):
            return True
        has_review_verb = any(term in q for term in ["beoordeel", "review", "controleer", "check", "valideer"])
        has_target = any(term in q for term in ["trade", "setup", "strategie", "strategy", "bot", "instap", "entry"])
        if has_review_verb and has_target:
            return True
        natural_trade_review = any(term in q for term in [
            "zou jij dit doen",
            "zou je dit doen",
            "zou jij dit openen",
            "zou je dit openen",
            "zou jij dit nemen",
            "zou je dit nemen",
            "is dit slim",
            "zou dit slim zijn",
        ])
        trade_context = bool(
            context.get("setup_id")
            or context.get("strategy_id")
            or context.get("bot_id")
            or context.get("symbol")
            or self._page_family(context) in {"setup", "strategy", "bot", "dashboard", "market"}
        )
        if natural_trade_review and trade_context:
            return True
        return bool(
            has_target
            and any(term in q for term in ["mag ik", "kan ik", "moet ik", "past dit", "goede trade"])
            and (
                context.get("setup_id")
                or context.get("strategy_id")
                or context.get("bot_id")
                or context.get("symbol")
            )
        )

    async def build_general_capability_response(self, user_id: int, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        context = context or {}
        page = context.get("page_type") or context.get("page") or "Tradamind"
        asset = context.get("symbol") or context.get("asset")
        asset_text = f" rond {str(asset).upper()}" if asset else ""
        response = (
            f"Ik help je hier vooral met uitleg, coaching en review in {page}{asset_text}. "
            "Denk aan: je actieve setup of strategie uitleggen, score- en blocker-uitleg geven, "
            "dagcoaching doen, Mission Control samenvatten en bot-decisions reviewen voordat je iets uitvoert."
        )
        return {
            "response": response,
            "intent": "general_help",
            "flow": "general_help",
            "state": {
                "current_flow": "general_help",
                "page": context.get("page"),
                "asset": asset,
            },
            "analysis": {
                "mode": "read_only",
                "route_source": "finn",
                "examples": [
                    "Leg mijn setup uit",
                    "Waarom blokkeert technical mijn BTC setup?",
                    "Wat moet ik vandaag doen?",
                ],
            },
            "actions": [],
        }

    def _product_capability_inventory(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        context = context or {}
        page_type = str(context.get("page_type") or context.get("page") or "Tradamind")
        current_entity = {
            "symbol": context.get("symbol") or context.get("asset"),
            "setup_id": context.get("setup_id"),
            "strategy_id": context.get("strategy_id"),
            "bot_id": context.get("bot_id"),
        }
        return {
            "page": page_type,
            "current_entity": {k: v for k, v in current_entity.items() if v not in (None, "", [], {})},
            "supported_read_only": [
                "setup_uitleg",
                "strategie_uitleg",
                "bot_uitleg",
                "score_uitleg",
                "rapport_uitleg",
                "coaching",
                "mission_control_samenvatting",
            ],
            "supported_mutations": [
                "setup_aanmaken",
                "strategie_genereren",
                "bot_aanmaken",
                "bot_decision_review",
            ],
            "not_supported_yet": [
                "watchlist_wijzigen_via_finn",
                "brede_portfolio_mutaties",
            ],
        }

    async def build_product_help_response(self, user_id: int, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        context = context or {}
        page = context.get("page_type") or context.get("page") or "Tradamind"
        inventory = self._product_capability_inventory(context)
        supported_now = ", ".join([
            "uitleg van je huidige scherm",
            "score/setup/strategie/bot uitleg",
            "coaching",
            "Mission Control samenvatten",
        ])
        mutations = ", ".join([
            "setup aanmaken",
            "strategie genereren",
            "bot aanmaken",
            "bot-decisions reviewen",
        ])
        response = (
            f"Je zit nu op {page}. Hier help ik je vooral met begrijpen en veilig beslissen. "
            f"Wat ik nu direct voor je kan doen: {supported_now}. "
            f"Als je echt iets wilt bouwen of wijzigen, kan ik ook helpen met: {mutations}. "
            "Wat ik nog niet breed zelf doet: watchlists aanpassen en vrije portfolio-mutaties."
        )
        return {
            "response": response,
            "intent": "product_help",
            "flow": "product_help",
            "state": {
                "current_flow": "product_help",
                "page": context.get("page"),
                "analysis": {
                    "mode": "read_only",
                    "route_source": "finn",
                },
            },
            "analysis": {
                "mode": "read_only",
                "route_source": "finn",
                "product_help": inventory,
            },
            "actions": [],
        }

    async def build_product_refresh_help_response(self, user_id: int, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        context = context or {}
        asset = self._asset_from_query_or_context(query, context)
        response = (
            f"Je ziet waarschijnlijk oudere of ontbrekende daily scoredata voor {asset}. "
            "Dat betekent niet automatisch dat je setup fout is; meestal loopt de datalaag of scoregeneratie gewoon achter. "
            f"Als je echt wilt verversen, vraag dan: 'Ververs mijn daily scores voor {asset}'."
        )
        analysis = {
            "mode": "read_only",
            "tool_intent_reason": "safe_read_only_explain",
            "product_help": {
                "variant": "refresh_help",
                "asset": asset,
                "suggested_next_step": f"Ververs daily scores voor {asset}",
            },
        }
        return {
            "response": response,
            "intent": "product_help",
            "flow": "product_help",
            "state": {
                "current_flow": "product_help",
                "asset": asset,
                "analysis": analysis,
            },
            "analysis": analysis,
            "actions": [],
        }

    def _education_topic_catalog(self) -> Dict[str, Dict[str, Any]]:
        return {
            "rsi": {
                "aliases": ["rsi"],
                "title": "RSI",
                "simple": "RSI laat zien of prijs op korte termijn al hard is opgelopen of gedaald. Het helpt je zien of momentum heet of juist afgekoeld is.",
                "what_it_is": "RSI is een momentum-indicator die vaak tussen 0 en 100 beweegt.",
                "why_it_matters": "Het helpt je voorkomen dat je alleen naar gevoel kijkt als prijs snel beweegt.",
                "not_enough_on_its_own": "RSI alleen is geen koop- of verkoopknop; je leest hem samen met trend en context.",
            },
            "ma200": {
                "aliases": ["ma200", "ma 200"],
                "title": "MA200",
                "simple": "De MA200 is een lang gemiddelde dat helpt zien of de grotere trend eerder sterk of zwak is.",
                "what_it_is": "De MA200 is het gemiddelde van ongeveer 200 candles of perioden.",
                "why_it_matters": "Veel traders gebruiken hem als simpele scheidslijn tussen bovenliggende kracht en zwakte.",
                "not_enough_on_its_own": "Hij zegt weinig over je precieze entry; hij geeft vooral trendcontext.",
            },
            "wyckoff": {
                "aliases": ["wyckoff"],
                "title": "Wyckoff",
                "simple": "Wyckoff probeert te lezen of grote spelers rustig aan het opbouwen zijn of juist aan het uitstappen zijn.",
                "what_it_is": "Het is een marktbenadering rond accumulatie, distributie en vraag-aanbod gedrag.",
                "why_it_matters": "Het helpt prijsactie zien als een proces, niet alleen als losse candles.",
                "not_enough_on_its_own": "Het vraagt context en oefening; het is geen snelle one-indicator check.",
            },
            "dca": {
                "aliases": ["dca"],
                "title": "DCA",
                "simple": "DCA betekent dat je in vaste stapjes koopt in plaats van alles in één keer.",
                "what_it_is": "Je spreidt entries over tijd, bijvoorbeeld wekelijks of maandelijks.",
                "why_it_matters": "Dat vermindert timingdruk en maakt impulsbeslissingen minder dominant.",
                "not_enough_on_its_own": "DCA beschermt niet tegen elk slecht plan; je blijft risk management nodig hebben.",
            },
            "stop_loss": {
                "aliases": ["stop loss", "stoploss"],
                "title": "Stop loss",
                "simple": "Een stop loss is je vooraf gekozen punt waar je uitstapt als je trade ongeldig wordt.",
                "what_it_is": "Het is een verdedigingsregel voor verliesbeperking.",
                "why_it_matters": "Je beslist vooraf wat je maximaal wilt laten misgaan in plaats van dat emotie dat later doet.",
                "not_enough_on_its_own": "Een stop loss werkt pas goed samen met positieomvang en marktstructuur.",
            },
            "position_sizing": {
                "aliases": ["position sizing"],
                "title": "Position sizing",
                "simple": "Position sizing gaat over hoeveel je koopt, niet alleen wat je koopt.",
                "what_it_is": "Je koppelt positiegrootte aan je totale kapitaal en aan het risico van één idee.",
                "why_it_matters": "Zelfs een goed idee wordt gevaarlijk als je positie te groot is.",
                "not_enough_on_its_own": "Goede sizing vervangt geen goed plan; het maakt een plan alleen veiliger uitvoerbaar.",
            },
            "risk_management": {
                "aliases": ["risk management"],
                "title": "Risk management",
                "simple": "Risk management is de laag die bepaalt hoeveel je mag verliezen en wanneer je juist niets doet.",
                "what_it_is": "Het combineert regels voor verlies, exposure, positiegrootte en discipline.",
                "why_it_matters": "Zonder risk management kan één slechte beslissing te veel schade doen.",
                "not_enough_on_its_own": "Het maakt slechte ideeën niet goed, maar het voorkomt dat slechte ideeën je opblazen.",
            },
            "trading_plan": {
                "aliases": ["trading plan"],
                "title": "Trading plan",
                "simple": "Een trading plan is je vooraf afgesproken speelboek voor entry, exit, risico en wachten.",
                "what_it_is": "Je legt vast wat je doet voordat de markt druk of emotie toevoegt.",
                "why_it_matters": "Daardoor besluit je minder op adrenaline en meer op regels.",
                "not_enough_on_its_own": "Een plan werkt pas als je het ook echt volgt en bijstuurt op basis van bewijs.",
            },
            "do_nothing": {
                "aliases": ["niets doen", "even niets doen", "beter even niets doen"],
                "title": "Niets doen",
                "simple": "Niets doen is vaak verstandig als je plan niet actief is, je context onzeker is of je emotie hoger is dan je duidelijkheid.",
                "what_it_is": "Het is geen passiviteit, maar een bewuste keuze om geen slechte trade te forceren.",
                "why_it_matters": "Veel schade komt niet van te weinig trades, maar van geforceerde trades.",
                "not_enough_on_its_own": "Wachten helpt alleen als je ook weet waar je later wél op wacht.",
            },
        }

    def _match_education_topic(self, query: str) -> Optional[str]:
        q = self._normalized_query(query)
        if ("niets" in q and "doe" in q) or "even niets" in q:
            return "do_nothing"
        for key, meta in self._education_topic_catalog().items():
            if any(alias in q for alias in meta.get("aliases", [])):
                return key
        return None

    def _build_education_message(self, topic_key: Optional[str], query: str) -> Dict[str, Any]:
        topic = self._education_topic_catalog().get(topic_key or "", {})
        if not topic:
            return {
                "response": "Ik kan basis trading-concepten simpel uitleggen, zoals RSI, MA200, Wyckoff, DCA, stop loss, position sizing, risk management en wanneer juist niets doen verstandig is.",
                "analysis": {
                    "topic": None,
                    "difficulty": "simple",
                    "confidence": "medium",
                    "what_it_is": None,
                    "why_it_matters": None,
                    "how_to_use_it_safely": None,
                    "common_mistake": None,
                },
            }
        safe_use = (
            "Gebruik dit samen met trend, context en je plan; laat het niet alleen beslissen of je iets doet."
        )
        common_mistake = topic["not_enough_on_its_own"]
        response = (
            f"{topic['simple']}\n"
            f"Wat het is: {topic['what_it_is']}\n"
            f"Waarom het telt: {topic['why_it_matters']}\n"
            f"Veilig gebruiken: {safe_use}\n"
            f"Veelgemaakte fout: {common_mistake}"
        )
        return {
            "response": response,
            "analysis": {
                "topic": topic_key,
                "topic_label": topic["title"],
                "difficulty": "simple" if "simpele taal" in self._normalized_query(query) or "eenvoudig" in self._normalized_query(query) else "standard",
                "confidence": "high",
                "what_it_is": topic["what_it_is"],
                "why_it_matters": topic["why_it_matters"],
                "how_to_use_it_safely": safe_use,
                "common_mistake": common_mistake,
            },
        }

    def _context_confidence(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        context = context or {}
        for target in ("strategy", "setup", "bot"):
            confidence = self._resolve_context_target("", context, target)
            if confidence["level"] in {"high", "medium"}:
                return confidence
        return {"level": "low", "entity_type": "unknown", "entity_id": None, "reason": "generic_fallback", "why": "no strong entity context"}

    def _context_confidence_for_target(
        self,
        context: Optional[Dict[str, Any]],
        entity_type: str,
        *,
        query: str = "",
        asset: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._resolve_context_target(query, context, entity_type, asset=asset)

    def _context_explain_target(self, query: str, context: Optional[Dict[str, Any]] = None) -> str:
        q = self._normalized_query(query)
        context = context or {}
        if any(phrase in q for phrase in ["wat bekijk ik nu", "leg dit scherm uit", "wat zie ik nu", "welke pagina", "dit scherm", "deze pagina"]):
            return "page"
        if "mission control" in q:
            return "mission_control"
        if "asset" in q:
            return "asset"
        if any(phrase in q for phrase in ["welk rapport zie ik nu", "welk report zie ik nu", "welk rapport bekijk ik nu", "welk report bekijk ik nu"]):
            return "report"
        if any(term in q for term in ["rapport", "report"]):
            return "report"
        if "score" in q:
            return "score"
        if "bot" in q:
            return "bot"
        if any(term in q for term in ["strategie", "strategy"]):
            return "strategy"
        if any(term in q for term in ["setup", "plan"]):
            return "setup"
        follow_up_target = self._follow_up_context_entity_type(query, context)
        if follow_up_target:
            return follow_up_target
        if context.get("strategy_id"):
            return "strategy"
        if context.get("setup_id"):
            return "setup"
        if context.get("bot_id"):
            return "bot"
        if context.get("symbol") or context.get("asset"):
            return "score"
        if context.get("page_type") or context.get("page"):
            return "page"
        return "unknown"

    def _report_table_from_query_or_context(self, query: str, context: Optional[Dict[str, Any]] = None) -> str:
        q = self._normalized_query(query)
        page_type = str((context or {}).get("page_type") or "").lower()
        if any(term in q for term in ["quarter", "kwartaal", "kwartaalrapport"]):
            return "quarterly_reports"
        if any(term in q for term in ["maand", "monthly", "30 dagen"]):
            return "monthly_reports"
        if any(term in q for term in ["week", "weekly", "weekreflectie"]):
            return "weekly_reports"
        if "report" in page_type and "week" in page_type:
            return "weekly_reports"
        if "report" in page_type and "maand" in page_type:
            return "monthly_reports"
        return "daily_reports"

    def _context_explain_payload(
        self,
        *,
        response: str,
        confidence: Dict[str, Any],
        entity_type: str,
        entity: Optional[Dict[str, Any]] = None,
        state_overrides: Optional[Dict[str, Any]] = None,
        actions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        entity = entity or {}
        context_resolution = self._context_resolution_payload(confidence, entity_type, entity)
        analysis = {
            "entity_type": entity_type,
            "entity": entity,
            "context_confidence": confidence,
            "context_entity_resolution": context_resolution,
            "context_explain": {
                "entity_type": entity_type,
                "entity_id": entity.get("id") or confidence.get("entity_id"),
                "asset": entity.get("asset") or entity.get("symbol"),
                "report_type": entity.get("table_name"),
            },
        }
        state = {"current_flow": "context_explain", "analysis": analysis}
        if state_overrides:
            state.update(state_overrides)
        return {
            "response": response,
            "intent": "context_explain",
            "flow": "context_explain",
            "state": state,
            "analysis": analysis,
            "actions": actions or [],
        }

    def _page_summary_message(self, context: Optional[Dict[str, Any]] = None) -> str:
        context = context or {}
        page_type = str(context.get("page_type") or context.get("page") or "Tradamind")
        page = str(context.get("page") or "").lower()
        symbol = context.get("symbol") or context.get("asset")
        setup_id = context.get("setup_id")
        strategy_id = context.get("strategy_id")
        bot_id = context.get("bot_id")

        if "dashboard" in page_type.lower() or "dashboard" in page:
            return "Je zit op het dashboard. Hier zie je vooral je actuele asset-context, dagelijkse scores, Mission Control en snelle coaching over wat vandaag aandacht vraagt."
        if "setup" in page_type.lower() or setup_id:
            return f"Je zit op een setup-scherm{f' voor setup #{setup_id}' if setup_id else ''}. Hier kijk je of een setup logisch is, welke score-ranges gelden en of deze context klaar is voor een strategie."
        if "strategy" in page_type.lower() or strategy_id:
            return f"Je zit op een strategie-scherm{f' voor strategie #{strategy_id}' if strategy_id else ''}. Hier beoordeel je hoe een setup vertaald wordt naar entry-, stop-, target- en risicoregels."
        if "bot" in page_type.lower() or bot_id:
            return f"Je zit op een bot-scherm{f' voor bot #{bot_id}' if bot_id else ''}. Hier kijk je vooral naar automation, review-openingen en of de bot veilig live of paper draait."
        if "report" in page_type.lower() or "report" in page:
            return "Je zit op de report-surface. Hier vat FINN je reflectie, gedrag en rapportcontext samen zodat je sneller ziet wat je hebt gedaan en wat aandacht vraagt."
        if symbol:
            return f"Je zit in een {page_type}-context rond {symbol}. Ik kan hier vooral scores, blockers en je actieve productcontext uitleggen."
        return f"Je zit op {page_type}. Ik kan hier het scherm uitleggen, de actieve entiteit duiden en helpen bepalen wat nu lezen is en wat echt een actie vraagt."

    def _mission_summary_dedupe_key(self, item: Dict[str, Any]) -> str:
        return str(item.get("title") or item.get("label") or item.get("asset") or item.get("id") or "").strip().lower()

    def _mission_summary_priority_items(self, mission: Dict[str, Any]) -> List[Dict[str, Any]]:
        workqueue = mission.get("workqueue") or []
        type_weight = {
            "portfolio_live_hotspot": 120,
            "portfolio_risk_stack": 115,
            "blocked_plan": 110,
            "blocker_explanation": 100,
            "bot_decision": 92,
            "bot_decision_request": 88,
            "execution_review": 84,
            "indicator_gap": 72,
            "data_gap": 58,
            "score_refresh": 52,
        }

        def _score(item: Dict[str, Any]) -> int:
            item_type = str(item.get("type") or "")
            priority = str(item.get("priority") or "").lower()
            title = str(item.get("title") or item.get("label") or "").lower()
            reason = str(item.get("reason") or "").lower()
            score = int(type_weight.get(item_type, 40))
            if priority == "high":
                score += 20
            elif priority == "medium":
                score += 8
            if any(term in f"{title} {reason}" for term in ["blokke", "risico", "review", "conflict", "live", "wachten"]):
                score += 10
            if any(term in f"{title} {reason}" for term in ["refresh", "ververs", "daily score", "oude data"]):
                score -= 8
            return score

        ranked = sorted(workqueue, key=lambda item: (_score(item), -(int(item.get("priority_rank") or 999))), reverse=True)
        picked: List[Dict[str, Any]] = []
        seen = set()
        refresh_used = False
        blocker_used = False
        actionable_used = False
        for item in ranked:
            title = item.get("title") or item.get("label")
            if not title:
                continue
            dedupe = self._mission_summary_dedupe_key(item)
            if dedupe in seen:
                continue
            item_type = str(item.get("type") or "")
            if item_type in {"score_refresh", "data_gap"}:
                if refresh_used:
                    continue
                refresh_used = True
            if item_type in {"blocked_plan", "blocker_explanation", "portfolio_risk_stack", "portfolio_live_hotspot"}:
                if blocker_used and item_type != "portfolio_live_hotspot":
                    continue
                blocker_used = True
            if item_type in {"bot_decision", "bot_decision_request", "execution_review"}:
                if actionable_used:
                    continue
                actionable_used = True
            picked.append(item)
            seen.add(dedupe)
            if len(picked) >= 3:
                break
        return picked

    def _mission_summary_suppressions(self, mission: Dict[str, Any], analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        coaching_loop = mission.get("coaching_loop") or {}
        suppressed = coaching_loop.get("suppressed_items") or []
        cleaned: List[Dict[str, Any]] = []
        seen = set()
        for item in suppressed:
            title = item.get("title")
            reason = item.get("reason")
            if not title or title == "None":
                continue
            dedupe = f"{title}|{reason}"
            if dedupe in seen:
                continue
            seen.add(dedupe)
            cleaned.append(item)
            if len(cleaned) >= 2:
                break
        if cleaned:
            return cleaned
        ignore_today = ((analysis.get("portfolio_risk") or {}).get("ignore_today_assets")) or []
        for item in ignore_today:
            asset = item.get("asset")
            reason = item.get("reason")
            if not asset or not reason:
                continue
            cleaned.append({
                "title": f"{asset} vandaag laten liggen",
                "reason": reason,
            })
            if len(cleaned) >= 2:
                break
        return cleaned

    def _mission_summary_payload(self, mission: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
        top_items = self._mission_summary_priority_items(mission)
        suppressions = self._mission_summary_suppressions(mission, analysis)
        counts = mission.get("summary") or {}
        top_priority = top_items[0] if top_items else {}
        top_title = top_priority.get("title")
        top_reason = top_priority.get("reason")
        headline = (
            f"Belangrijkste focus nu: {top_title}. {top_reason}"
            if top_items and top_reason else
            f"Belangrijkste focus nu: {top_title}."
            if top_items else
            "Mission Control ziet nu geen harde act-now escalatie."
        )
        return {
            "headline": headline,
            "top_3": [
                {
                    "title": item.get("title") or item.get("label"),
                    "type": item.get("type"),
                    "priority": item.get("priority"),
                    "reason": item.get("reason"),
                    "asset": item.get("asset"),
                }
                for item in top_items
            ],
            "avoid_today": [
                {
                    "title": item.get("title"),
                    "reason": item.get("reason"),
                    "asset": item.get("asset"),
                }
                for item in suppressions
            ],
            "open_counts": {
                "workqueue_count": counts.get("workqueue_count", 0),
                "open_action_count": counts.get("open_action_count", 0),
                "high_priority_count": len([
                    item for item in (mission.get("workqueue") or [])
                    if str(item.get("priority") or "").lower() == "high"
                ]),
            },
        }

    def _priority_engine_governance_signals(
        self,
        events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        asset_signals: Dict[str, Dict[str, Any]] = {}
        global_signals: List[Dict[str, Any]] = []
        for event in events or []:
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            event_type = str(event.get("type") or "")
            asset = str(payload.get("asset") or event.get("symbol") or "").upper()
            weight = 0
            reason = None
            if event_type == "finn_plan_adherence_review":
                adherence = str(payload.get("adherence_status") or "")
                if adherence in {"forced_override", "outside_plan"}:
                    weight = 34
                    reason = payload.get("threatened_rule") or event.get("description")
                elif adherence == "insufficiently_justified":
                    weight = 22
                    reason = event.get("description")
            elif event_type == "finn_decision_review":
                status = str(payload.get("decision_status") or "")
                if status == "block":
                    weight = 30
                    reason = (payload.get("top_blockers") or [None])[0] or event.get("description")
                elif status in {"modify", "insufficient_context"}:
                    weight = 18
                    reason = (payload.get("recommended_changes") or [None])[0] or event.get("description")
            elif event_type == "finn_portfolio_intelligence":
                portfolio_status = str(payload.get("portfolio_status") or "")
                if portfolio_status in {"high_attention", "concentrated"}:
                    weight = 28
                    reason = payload.get("concentration_warning") or payload.get("stacked_risk_warning") or event.get("description")
                elif portfolio_status in {"watch", "needs_data"}:
                    weight = 14
                    reason = event.get("description")
            elif event_type == "finn_outcome_tracking_summary":
                sample_size = int(payload.get("sample_size") or 0)
                if sample_size >= 3:
                    weight = 12
                    reason = payload.get("net_effect") or event.get("description")
            if weight <= 0:
                continue
            signal = {
                "type": event_type,
                "weight": weight,
                "reason": reason,
                "asset": asset or None,
            }
            if asset:
                current = asset_signals.get(asset)
                if not current or weight > int(current.get("weight") or 0):
                    asset_signals[asset] = signal
            else:
                global_signals.append(signal)
        return {"asset_signals": asset_signals, "global_signals": global_signals[:3]}

    def _priority_item_rationale(
        self,
        *,
        item_type: str,
        item_reason: Optional[str],
        signal_reason: Optional[str],
    ) -> str:
        item_reason = str(item_reason or "").strip()
        signal_reason = str(signal_reason or "").strip()
        if not signal_reason:
            return item_reason
        if not item_reason:
            return signal_reason
        if signal_reason.lower() == item_reason.lower():
            return item_reason
        if item_type in {"portfolio_risk_stack", "blocked_plan"}:
            return f"{item_reason} Extra governance-frictie: {signal_reason}"
        return item_reason

    def _priority_engine_payload(
        self,
        mission: Dict[str, Any],
        analysis: Dict[str, Any],
        governance_signals: Dict[str, Any],
        *,
        question_focus: str = "headline",
    ) -> Dict[str, Any]:
        workqueue = mission.get("workqueue") or []
        counts = mission.get("summary") or {}
        asset_signals = governance_signals.get("asset_signals") if isinstance(governance_signals, dict) else {}
        global_signals = governance_signals.get("global_signals") if isinstance(governance_signals, dict) else []
        suppressions = self._mission_summary_suppressions(mission, analysis)
        ranked_items: List[Dict[str, Any]] = []
        seen = set()
        for item in workqueue:
            title = item.get("title") or item.get("label")
            if not title:
                continue
            dedupe = self._mission_summary_dedupe_key(item)
            if dedupe in seen:
                continue
            seen.add(dedupe)
            asset = str(item.get("asset") or "").upper()
            item_type = str(item.get("type") or "")
            priority = str(item.get("priority") or "").lower()
            base = max(0, 120 - int(item.get("priority_rank") or 99))
            if priority == "high":
                base += 18
            elif priority == "medium":
                base += 8
            if item_type in {"portfolio_live_hotspot", "portfolio_risk_stack", "blocked_plan"}:
                base += 18
            elif item_type in {"bot_decision", "bot_decision_request", "execution_review"}:
                base += 12
            elif item_type in {"score_refresh", "data_gap"}:
                base -= 10
            signal = asset_signals.get(asset) if asset else None
            signal_reason = None
            if signal:
                base += int(signal.get("weight") or 0)
                signal_reason = signal.get("reason")
            elif global_signals and item_type in {"portfolio_live_hotspot", "portfolio_risk_stack", "blocked_plan"}:
                base += int(global_signals[0].get("weight") or 0) // 2
                signal_reason = global_signals[0].get("reason")
            rationale = self._priority_item_rationale(
                item_type=item_type,
                item_reason=item.get("reason"),
                signal_reason=signal_reason,
            )
            ranked_items.append({
                "id": item.get("id"),
                "title": title,
                "asset": item.get("asset"),
                "priority": item.get("priority"),
                "type": item_type,
                "lane": self._mission_coaching_lane(item),
                "score": base,
                "why_now": rationale,
                "source_reason": item.get("reason"),
                "governance_reason": signal_reason or None,
                "next_action": item.get("next_best_action") or item.get("resolve_action"),
            })

        ranked_items = sorted(
            ranked_items,
            key=lambda item: (-int(item.get("score") or 0), str(item.get("title") or "")),
        )
        top_priorities = ranked_items[:3]
        review_queue = [
            item for item in ranked_items
            if item.get("lane") in {"act_now", "review_then_act"} or item.get("type") in {"bot_decision", "portfolio_live_hotspot", "portfolio_risk_stack", "blocked_plan"}
        ][:5]
        ignore_today = [
            {
                "title": item.get("title"),
                "reason": item.get("reason"),
                "asset": item.get("asset"),
            }
            for item in suppressions[:3]
        ]
        if not ignore_today:
            for item in reversed(ranked_items):
                if len(ignore_today) >= 3:
                    break
                if item.get("priority") not in {"low", "medium"} and item.get("type") not in {"score_refresh", "data_gap"}:
                    continue
                ignore_today.append({
                    "title": item.get("title"),
                    "reason": item.get("source_reason") or item.get("why_now"),
                    "asset": item.get("asset"),
                })
        suppression_reasons = [item.get("reason") for item in ignore_today if item.get("reason")]
        top = top_priorities[0] if top_priorities else {}
        if question_focus == "start_now":
            headline = (
                f"Begin nu met: {top.get('title')}."
                if top.get("title") else
                "Ik zie nu geen harde startactie boven je huidige flow."
            )
        elif question_focus == "ignore_today":
            first_ignore = (ignore_today or [{}])[0]
            headline = (
                f"Laat vandaag liggen: {first_ignore.get('title')}."
                if first_ignore.get("title") else
                "Vandaag hoeft er niets bewust genegeerd te worden boven je huidige flow."
            )
        elif question_focus == "wait":
            first_ignore = (ignore_today or [{}])[0]
            headline = (
                f"Dit kan wachten: {first_ignore.get('title')}."
                if first_ignore.get("title") else
                "Ik zie nu geen duidelijk uitstelfocuspunt boven je huidige flow."
            )
        elif question_focus == "focus":
            headline = (
                f"Focus vandaag eerst op: {top.get('title')}."
                if top.get("title") else
                "Vandaag zie ik geen enkele focusverschuiving boven je huidige flow."
            )
        else:
            headline = (
                f"Vandaag eerst: {top.get('title')}."
                if top.get("title") else
                "Vandaag zie ik geen harde act-now prioriteit boven je huidige flow."
            )
        why_now = (
            top.get("why_now")
            or (global_signals[0].get("reason") if global_signals else None)
            or "Dit geeft nu de meeste combinatie van risico, urgentie en besliswaarde."
        )
        focus_guidance = {
            "start_now": "Kies nu eerst de bovenste act-now taak en laat de rest heel even stilvallen.",
            "focus": "Hou vandaag een smalle focus aan; een te brede reviewstack maakt je besluitvorming slapper.",
            "wait": "Wachten is hier discipline, niet passiviteit. Laat alleen liggen wat nu geen besliswaarde heeft.",
            "ignore_today": "Niet doen is hier een guardrail, geen gemiste kans. Bescherm eerst je kapitaal en aandacht.",
            "top3": "Hou het vandaag bij drie kernacties; meer voegt vooral ruis toe aan je operatorflow.",
            "headline": "Gebruik dit als je dagvolgorde: eerst risico en reviewdruk, daarna pas nieuwe ideeën.",
        }.get(question_focus, "Gebruik dit als je dagvolgorde: eerst risico en reviewdruk, daarna pas nieuwe ideeën.")
        return {
            "headline": headline,
            "top_priorities": top_priorities,
            "review_queue": review_queue,
            "ignore_today": ignore_today,
            "why_now": why_now,
            "focus_guidance": focus_guidance,
            "suppression_reasons": suppression_reasons,
            "question_focus": question_focus,
            "open_counts": {
                "workqueue_count": counts.get("workqueue_count", 0),
                "open_action_count": counts.get("open_action_count", 0),
                "high_priority_count": len([
                    item for item in workqueue
                    if str(item.get("priority") or "").lower() == "high"
                ]),
            },
            "governance_signals": governance_signals,
        }

    def _priority_engine_message(self, analysis: Dict[str, Any]) -> str:
        question_focus = str(analysis.get("question_focus") or "headline")
        lines = [
            analysis.get("headline") or "Hier is je prioriteitenmotor voor vandaag.",
            analysis.get("why_now") or "",
        ]
        if analysis.get("focus_guidance"):
            lines.append(str(analysis.get("focus_guidance")))
        top_priorities = analysis.get("top_priorities") or []
        if top_priorities and question_focus != "ignore_today":
            top_label = "Doe of review nu het volgende:"
            if question_focus == "start_now":
                top_label = "Begin hier nu mee:"
            elif question_focus == "focus":
                top_label = "Hier moet vandaag je focus liggen:"
            elif question_focus == "top3":
                top_label = "Dit zijn vandaag je 3 belangrijkste acties:"
            lines.append("Doe of review nu het volgende:")
            lines[-1] = top_label
            for item in top_priorities[:3]:
                lines.append(f"- {item.get('title')}: {item.get('why_now') or item.get('source_reason')}")
        ignore_today = analysis.get("ignore_today") or []
        if ignore_today:
            ignore_label = "Vandaag bewust laten liggen:"
            if question_focus == "wait":
                ignore_label = "Dit kan vandaag wachten:"
            elif question_focus == "ignore_today":
                ignore_label = "Dit moet je vandaag juist niet doen:"
            lines.append(ignore_label)
            for item in ignore_today[:3]:
                lines.append(f"- {item.get('title')}: {item.get('reason')}")
        review_queue = analysis.get("review_queue") or []
        if review_queue and question_focus not in {"ignore_today", "wait"}:
            queue_label = "Hierna reviewen:"
            if question_focus == "top3":
                queue_label = "Daarna in deze volgorde reviewen:"
            lines.append(queue_label)
            for item in review_queue[:2]:
                lines.append(f"- {item.get('title')}: {item.get('why_now') or item.get('source_reason')}")
        return "\n".join([line for line in lines if line])

    async def build_priority_engine_response(
        self,
        user_id: int,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        question_focus = self._priority_question_focus(query)
        daily = await self.build_portfolio_daily_coach_response(
            user_id,
            "Geef mijn daily brief",
            {
                **(context or {"page": "mission_control"}),
                "scope": "mission_control",
                "mission_control_fast": True,
                "mission_control_preview_only": True,
            },
        )
        analysis = (daily.get("state") or {}).get("analysis") or {}
        mission = self._build_mission_control_from_daily_analysis(analysis)
        governance_events = await self._fetch_recent_governance_events(
            user_id,
            event_types=[
                "finn_decision_review",
                "finn_plan_adherence_review",
                "finn_outcome_tracking_summary",
                "finn_portfolio_intelligence",
            ],
            limit=30,
        )
        priority_engine = self._priority_engine_payload(
            mission,
            analysis,
            self._priority_engine_governance_signals(governance_events),
            question_focus=question_focus,
        )
        await self._record_governance_event(
            user_id,
            event_type="finn_priority_engine_summary",
            symbol=context.get("symbol") if isinstance(context, dict) else None,
            title="Finn rankte vandaag de operator-prioriteiten",
            description=priority_engine.get("why_now") or priority_engine.get("headline"),
            severity="info",
            payload={
                "phase": "priority_ranking_engine",
                "query": query,
                "question_focus": question_focus,
                "headline": priority_engine.get("headline"),
                "top_priorities": priority_engine.get("top_priorities"),
                "review_queue": priority_engine.get("review_queue"),
                "ignore_today": priority_engine.get("ignore_today"),
                "suppression_reasons": priority_engine.get("suppression_reasons"),
            },
            cooldown_hours=2,
        )
        return {
            "response": self._priority_engine_message(priority_engine),
            "intent": "priority_engine",
            "flow": "priority_engine",
            "draft": None,
            "missing_fields": [],
            "invalid_fields": [],
            "next_question": None,
            "can_confirm": False,
            "actions": [],
            "state": {
                "status": "answered",
                "current_flow": "priority_engine",
                "analysis": priority_engine,
                "autonomy_level": "advice_only",
            },
            "analysis": priority_engine,
            "reasoning": {
                "confidence_score": 0.84 if priority_engine.get("top_priorities") else 0.66,
                "risk_detected": bool(priority_engine.get("suppression_reasons")),
                "reasons": [priority_engine.get("why_now") or priority_engine.get("headline")],
                "coaching_level": "priority_engine",
            },
        }

    def _portfolio_operating_system_contract(
        self,
        *,
        daily_analysis: Dict[str, Any],
        mission: Dict[str, Any],
        priority_engine: Dict[str, Any],
        memory: Dict[str, Any],
        personal_performance: Optional[Dict[str, Any]] = None,
        trade_journal_intelligence: Optional[Dict[str, Any]] = None,
        governance_events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        personal_performance = personal_performance or {}
        trade_journal_intelligence = trade_journal_intelligence or {}
        portfolio_risk = mission.get("portfolio_risk") or daily_analysis.get("portfolio_risk") or {}
        plan_health = mission.get("plan_health") or []
        summary = mission.get("summary") or {}
        action_count = int(summary.get("open_action_count") or 0)
        blocked_count = int(summary.get("blocked_count") or 0)
        high_priority_count = int((priority_engine.get("open_counts") or {}).get("high_priority_count") or 0)
        memory_pattern = memory.get("memory_pattern")
        memory_confidence = memory.get("confidence_level")
        performance_score = personal_performance.get("performance_score")
        performance_flags = personal_performance.get("performance_risk_flags") or []
        journal_pattern = trade_journal_intelligence.get("journal_pattern")
        governance_types = [str(event.get("type") or "") for event in governance_events or []]
        recent_override_signals = len([t for t in governance_types if t == "finn_plan_adherence_review"])
        recent_review_signals = len([t for t in governance_types if t == "finn_decision_review"])

        if portfolio_risk.get("status") in {"high_attention", "concentrated"} or blocked_count > 0:
            posture = "risk_first"
        elif high_priority_count > 0 or action_count >= 3:
            posture = "review_first"
        elif performance_score is not None and performance_score < 65:
            posture = "performance_rebuild"
        elif memory_pattern not in {None, "insufficient_memory_signal"} and memory_confidence in {"medium", "high"}:
            posture = "discipline_first"
        else:
            posture = "steady_control"

        portfolio_layer = {
            "status": portfolio_risk.get("status") or "unknown",
            "top_asset": portfolio_risk.get("top_asset"),
            "top_reason": portfolio_risk.get("top_reason") or portfolio_risk.get("message"),
            "ignore_today_count": len(portfolio_risk.get("ignore_today_assets") or []),
            "live_hotspot_count": len(portfolio_risk.get("live_bot_hotspots") or []),
        }
        portfolio_pressure = {
            "source": (
                portfolio_risk.get("top_reason")
                or (performance_flags[0] if performance_flags else None)
                or trade_journal_intelligence.get("decision_gap")
                or priority_engine.get("why_now")
            ),
            "level": (
                "high"
                if posture in {"risk_first", "performance_rebuild"} else
                "medium"
                if posture in {"review_first", "discipline_first"} else
                "low"
            ),
            "summary": portfolio_risk.get("message") or portfolio_risk.get("top_reason") or priority_engine.get("headline"),
        }
        capital_focus = {
            "focus_asset": portfolio_risk.get("top_asset"),
            "top_reason": portfolio_risk.get("top_reason") or portfolio_risk.get("message"),
            "ignore_today_assets": portfolio_risk.get("ignore_today_assets") or [],
        }
        conflict_stack = [
            item
            for item in [
                portfolio_risk.get("top_reason"),
                (performance_flags[0] if performance_flags else None),
                trade_journal_intelligence.get("decision_gap"),
                priority_engine.get("why_now"),
            ]
            if item
        ][:4]
        governance_layer = {
            "posture": posture,
            "decision_review_signal_count": recent_review_signals,
            "plan_adherence_signal_count": recent_override_signals,
            "memory_pattern": memory_pattern,
            "memory_confidence": memory_confidence,
            "performance_score": performance_score,
            "journal_pattern": journal_pattern,
            "priority_headline": priority_engine.get("headline"),
        }
        subsystems = {
            "portfolio": portfolio_layer,
            "decision_review": {
                "status": "ready" if recent_review_signals else "quiet",
                "latest_signal_count": recent_review_signals,
            },
            "plan_adherence": {
                "status": "attention" if recent_override_signals else "steady",
                "latest_signal_count": recent_override_signals,
            },
            "outcome_tracking": {
                "status": "ready" if "finn_outcome_tracking_summary" in governance_types else "early",
                "latest_signal_count": len([t for t in governance_types if t == "finn_outcome_tracking_summary"]),
            },
            "priority_engine": {
                "status": "active" if priority_engine.get("top_priorities") else "quiet",
                "queue_count": len(priority_engine.get("review_queue") or []),
            },
            "memory_v2": {
                "status": "active" if memory_confidence in {"medium", "high"} else "early",
                "pattern": memory_pattern,
            },
            "personal_performance": {
                "status": "active" if performance_score is not None else "early",
                "performance_score": performance_score,
                "risk_flag_count": len(performance_flags),
            },
            "trade_journal_intelligence": {
                "status": "active" if journal_pattern and journal_pattern != "insufficient_journal_signal" else "early",
                "pattern": journal_pattern,
                "tag_count": len(trade_journal_intelligence.get("journal_tags") or []),
            },
        }
        control_plane = {
            "headline": (
                "Portfolio Operating System staat nu op risk-first."
                if posture == "risk_first" else
                "Portfolio Operating System staat nu op review-first."
                if posture == "review_first" else
                "Portfolio Operating System staat nu op performance-rebuild."
                if posture == "performance_rebuild" else
                "Portfolio Operating System staat nu op discipline-first."
                if posture == "discipline_first" else
                "Portfolio Operating System draait nu stabiel zonder harde escalatie."
            ),
            "why_now": (
                priority_engine.get("why_now")
                or portfolio_risk.get("message")
                or personal_performance.get("next_growth_target")
                or trade_journal_intelligence.get("decision_gap")
                or memory.get("behavioral_cost")
                or "Er is nu geen enkele subsystem-laag die alle andere overstemt."
            ),
            "next_best_actions": [
                item.get("title")
                for item in (priority_engine.get("top_priorities") or [])
                if item.get("title")
            ][:3],
        }
        do_now = control_plane.get("next_best_actions") or []
        do_next = [
            item.get("title")
            for item in (priority_engine.get("review_queue") or [])
            if item.get("title")
        ][:3]
        ignore_today = priority_engine.get("ignore_today") or capital_focus.get("ignore_today_assets") or []
        return {
            "operating_posture": posture,
            "portfolio_pressure": portfolio_pressure,
            "capital_focus": capital_focus,
            "conflict_stack": conflict_stack,
            "do_now": do_now,
            "do_next": do_next,
            "ignore_today": ignore_today,
            "portfolio_layer": portfolio_layer,
            "governance_layer": governance_layer,
            "subsystems": subsystems,
            "control_plane": control_plane,
            "next_best_actions": do_now,
            "open_counts": {
                "asset_count": len(plan_health),
                "open_action_count": action_count,
                "blocked_count": blocked_count,
                "high_priority_count": high_priority_count,
            },
        }

    def _portfolio_operating_system_message(self, analysis: Dict[str, Any]) -> str:
        control_plane = analysis.get("control_plane") or {}
        governance = analysis.get("governance_layer") or {}
        lines = [
            control_plane.get("headline") or "Hier is je Portfolio Operating System status.",
            control_plane.get("why_now") or "",
        ]
        if governance.get("memory_pattern") and governance.get("memory_pattern") != "insufficient_memory_signal":
            lines.append(
                f"Governance-focus: {governance.get('memory_pattern')} "
                f"({governance.get('memory_confidence')} confidence)."
            )
        if governance.get("performance_score") is not None:
            lines.append(f"Personal performance: {governance.get('performance_score')}/100.")
        if governance.get("journal_pattern") and governance.get("journal_pattern") != "insufficient_journal_signal":
            lines.append(f"Journal-signaal: {governance.get('journal_pattern')}.")
        portfolio_layer = analysis.get("portfolio_layer") or {}
        if portfolio_layer.get("top_reason"):
            lines.append(f"Portfolio-laag: {portfolio_layer.get('top_reason')}")
        portfolio_pressure = analysis.get("portfolio_pressure") or {}
        if portfolio_pressure.get("source"):
            lines.append(f"Drukbron nu: {portfolio_pressure.get('source')}")
        next_actions = analysis.get("next_best_actions") or []
        if next_actions:
            lines.append("Volgende beste acties:")
            for item in next_actions[:3]:
                lines.append(f"- {item}")
        do_next = analysis.get("do_next") or []
        if do_next:
            lines.append("Daarna:")
            for item in do_next[:2]:
                lines.append(f"- {item}")
        ignore_today = analysis.get("ignore_today") or []
        if ignore_today:
            lines.append("Vandaag laten liggen:")
            for item in ignore_today[:2]:
                lines.append(f"- {item}")
        return "\n".join([line for line in lines if line])

    async def build_portfolio_operating_system_response(
        self,
        user_id: int,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        daily = await self.build_portfolio_daily_coach_response(
            user_id,
            "Geef mijn daily brief",
            {
                **(context or {"page": "mission_control"}),
                "scope": "mission_control",
                "mission_control_fast": True,
                "mission_control_preview_only": True,
            },
        )
        daily_analysis = (daily.get("state") or {}).get("analysis") or {}
        mission = self._build_mission_control_from_daily_analysis(daily_analysis)
        activity_feed = await self._get_recent_finn_activity(user_id, limit=180)
        day_log = self._mission_day_log(activity_feed)
        behavioral = self._build_behavioral_insight_from_activity(activity_feed, day_log)
        governance_events = await self._fetch_recent_governance_events(
            user_id,
            event_types=[
                "finn_decision_review",
                "finn_plan_adherence_review",
                "finn_outcome_tracking_summary",
                "finn_outcome_memory_summary",
                "finn_personal_performance_summary",
                "finn_personal_coach_summary",
                "finn_trade_journal_intelligence_summary",
                "finn_portfolio_intelligence",
                "finn_priority_engine_summary",
                "finn_memory_v2_summary",
            ],
            limit=80,
        )
        priority_engine = self._priority_engine_payload(
            mission,
            daily_analysis,
            self._priority_engine_governance_signals(governance_events),
        )
        memory_v2 = self._build_memory_v2_summary(activity_feed, governance_events)
        personal_performance = self._build_personal_performance_summary(activity_feed, governance_events, behavioral)
        trade_journal_intelligence = self._build_trade_journal_intelligence_summary(activity_feed, governance_events)
        memory = {
            **self._build_behavioral_memory_report(activity_feed, behavioral),
            **memory_v2,
        }
        analysis = self._portfolio_operating_system_contract(
            daily_analysis=daily_analysis,
            mission=mission,
            priority_engine=priority_engine,
            memory=memory,
            personal_performance=personal_performance,
            trade_journal_intelligence=trade_journal_intelligence,
            governance_events=governance_events,
        )
        await self._record_governance_event(
            user_id,
            event_type="finn_portfolio_operating_system_summary",
            symbol=context.get("symbol") if isinstance(context, dict) else None,
            title="Finn bouwde een portfolio operating system status",
            description=(analysis.get("control_plane") or {}).get("why_now") or (analysis.get("control_plane") or {}).get("headline"),
            severity="info",
            payload={
                "phase": "portfolio_operating_system",
                "query": query,
                "operating_posture": analysis.get("operating_posture"),
                "control_plane": analysis.get("control_plane"),
                "portfolio_layer": analysis.get("portfolio_layer"),
                "governance_layer": analysis.get("governance_layer"),
                "portfolio_pressure": analysis.get("portfolio_pressure"),
                "capital_focus": analysis.get("capital_focus"),
                "conflict_stack": analysis.get("conflict_stack"),
                "do_now": analysis.get("do_now"),
                "do_next": analysis.get("do_next"),
                "ignore_today": analysis.get("ignore_today"),
                "subsystems": analysis.get("subsystems"),
                "next_best_actions": analysis.get("next_best_actions"),
            },
            cooldown_hours=2,
        )
        return {
            "response": self._portfolio_operating_system_message(analysis),
            "intent": "portfolio_operating_system",
            "flow": "portfolio_operating_system",
            "draft": None,
            "missing_fields": [],
            "invalid_fields": [],
            "next_question": None,
            "can_confirm": False,
            "actions": [],
            "state": {
                "status": "answered",
                "current_flow": "portfolio_operating_system",
                "analysis": analysis,
                "autonomy_level": "advice_only",
            },
            "analysis": analysis,
            "reasoning": {
                "confidence_score": 0.86 if analysis.get("next_best_actions") else 0.72,
                "risk_detected": analysis.get("operating_posture") in {"risk_first", "review_first"},
                "reasons": [(analysis.get("control_plane") or {}).get("why_now") or (analysis.get("control_plane") or {}).get("headline")],
                "coaching_level": "portfolio_operating_system",
            },
        }

    async def build_mission_control_explain_response(
        self,
        user_id: int,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        daily = await self.build_portfolio_daily_coach_response(
            user_id,
            "Geef mijn daily brief",
            {
                **(context or {"page": "mission_control"}),
                "scope": "mission_control",
                "mission_control_fast": True,
                "mission_control_preview_only": True,
            },
        )
        analysis = (daily.get("state") or {}).get("analysis") or {}
        mission = self._build_mission_control_from_daily_analysis(analysis)
        mission["summary"] = {
            **(mission.get("summary") or {}),
            "coaching_loop_status": "preview",
        }
        governance_events = await self._fetch_recent_governance_events(
            user_id,
            event_types=[
                "finn_decision_review",
                "finn_plan_adherence_review",
                "finn_outcome_tracking_summary",
                "finn_portfolio_intelligence",
            ],
            limit=30,
        )
        priority_engine = self._priority_engine_payload(
            mission,
            analysis,
            self._priority_engine_governance_signals(governance_events),
        )
        summary = {
            "headline": priority_engine.get("headline"),
            "top_3": [
                {
                    "title": item.get("title"),
                    "type": item.get("type"),
                    "priority": item.get("priority"),
                    "reason": item.get("why_now") or item.get("source_reason"),
                    "asset": item.get("asset"),
                }
                for item in (priority_engine.get("top_priorities") or [])[:3]
            ],
            "avoid_today": priority_engine.get("ignore_today") or [],
            "open_counts": priority_engine.get("open_counts") or {},
        }
        response_lines = ["Mission Control zegt nu in het kort:"]
        if summary.get("headline"):
            response_lines.append(summary["headline"])
        if summary.get("top_3"):
            response_lines.append("Topprioriteiten voor vandaag:")
            for item in summary["top_3"]:
                title = item.get("title")
                reason = item.get("reason")
                response_lines.append(f"- {title}" + (f": {reason}" if reason else ""))
        if summary.get("avoid_today"):
            response_lines.append("Vandaag bewust niet doen:")
            for item in summary["avoid_today"]:
                response_lines.append(f"- {item.get('title')}: {item.get('reason')}")
        counts = summary.get("open_counts") or {}
        response_lines.append(
            f"Open nu: {counts.get('workqueue_count', 0)} items, "
            f"{counts.get('high_priority_count', 0)} met hoge prioriteit."
        )
        return {
            "response": "\n".join(response_lines),
            "intent": "mission_control_explain",
            "flow": "mission_control_explain",
            "state": {
                "current_flow": "mission_control_explain",
                "analysis": {
                    "mission_control": mission,
                    "mission_control_summary": summary,
                    "priority_engine": priority_engine,
                    "mission_control_source": "daily_coach_preview",
                    "context_confidence": {"level": "high", "entity_type": "mission_control", "entity_id": "mission_control", "reason": "mission control summary requested", "why": "mission control summary requested"},
                },
            },
            "analysis": {
                "mission_control": mission,
                "mission_control_summary": summary,
                "priority_engine": priority_engine,
                "mission_control_source": "daily_coach_preview",
                "context_confidence": {"level": "high", "entity_type": "mission_control", "entity_id": "mission_control", "reason": "mission control summary requested", "why": "mission control summary requested"},
            },
            "actions": [],
        }

    async def build_education_response(self, user_id: int, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        topic = self._match_education_topic(query)
        message = self._build_education_message(topic, query)
        return {
            "response": message["response"],
            "intent": "education",
            "flow": "education",
            "state": {
                "current_flow": "education",
                "topic": topic,
                "analysis": message["analysis"],
            },
            "analysis": message["analysis"],
            "actions": [],
        }

    async def build_context_explain_response(self, user_id: int, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        context = context or {}
        target = self._context_explain_target(query, context)
        confidence = self._context_confidence_for_target(context, target, query=query)
        strategy_id = context.get("strategy_id")
        setup_id = context.get("setup_id")
        bot_id = context.get("bot_id")
        if target == "strategy" and not strategy_id:
            strategy_id = confidence.get("entity_id")
        if target == "setup" and not setup_id:
            setup_id = confidence.get("entity_id")
        if target == "bot" and not bot_id:
            bot_id = confidence.get("entity_id")

        if target == "mission_control":
            return await self.build_mission_control_explain_response(user_id, query, context)

        if target == "page":
            page_type = str(context.get("page_type") or context.get("page") or "Tradamind")
            page_confidence = {
                "level": "high" if context.get("page") or context.get("page_type") else "medium",
                "entity_type": "page",
                "entity_id": context.get("page") or page_type,
                "reason": "page context available" if context.get("page") or context.get("page_type") else "page inferred from generic context",
                "why": "page context available" if context.get("page") or context.get("page_type") else "page inferred from generic context",
            }
            return self._context_explain_payload(
                response=self._page_summary_message(context),
                confidence=page_confidence,
                entity_type="page",
                entity={"page": context.get("page"), "page_type": page_type},
            )

        if target == "score":
            asset = self._asset_from_query_or_context(query, context)
            score_confidence = self._context_confidence_for_target(context, "score", query=query, asset=asset)
            if self.session:
                daily_scores = await self._fetch_daily_scores_with_runtime_refresh(user_id, asset)
                if daily_scores:
                    score_map = {
                        "macro": float(daily_scores.get("macro_score") or 0),
                        "technical": float(daily_scores.get("technical_score") or 0),
                        "market": float(daily_scores.get("market_score") or 0),
                        "setup": float(daily_scores.get("setup_score") or 0),
                    }
                    weakest = min(
                        [{"category": key, "score": value} for key, value in score_map.items()],
                        key=lambda item: item["score"],
                    )
                    strongest = max(
                        [{"category": key, "score": value} for key, value in score_map.items()],
                        key=lambda item: item["score"],
                    )
                    response = (
                        f"Je kijkt nu naar de {asset} daily score. Macro is {score_map['macro']:.1f}, "
                        f"technical {score_map['technical']:.1f}, market {score_map['market']:.1f} en setup {score_map['setup']:.1f}. "
                        f"De grootste rem zit nu in {weakest['category']} met {weakest['score']:.1f}, "
                        f"terwijl {strongest['category']} je meeste steun geeft met {strongest['score']:.1f}. "
                        f"Operator-implicatie: focus eerst op {weakest['category']} voordat je zwaarder leunt op de sterkere scoreblokken."
                    )
                    return self._context_explain_payload(
                        response=response,
                        confidence=score_confidence,
                        entity_type="score",
                        entity={
                            "asset": asset,
                            "daily_scores": daily_scores,
                            "weakest_component": weakest,
                            "strongest_component": strongest,
                            "top_blocker": weakest,
                            "top_support": strongest,
                            "operator_implication": f"Focus nu eerst op {weakest['category']} voordat je zwaarder leunt op de sterkere scoreblokken.",
                        },
                        state_overrides={"asset": asset},
                    )

            response = (
                f"Ik wil je score voor {asset} uitleggen, maar ik heb in deze context nog geen betrouwbare daily score-rij "
                "om veilig te citeren. Vraag gerust ook: ververs daily scores voor dit asset."
            )
            return self._context_explain_payload(
                response=response,
                confidence=score_confidence,
                entity_type="score",
                entity={"asset": asset},
                state_overrides={"asset": asset},
            )

        if target == "report":
            report_confidence = self._context_confidence_for_target(context, "report", query=query)
            if self.session:
                table_name = self._report_table_from_query_or_context(query, context)
                report = await ReportRepository(self.session).get_latest_report(user_id, table_name)
                if report:
                    period_label = {
                        "daily_reports": "dagrapport",
                        "weekly_reports": "weekrapport",
                        "monthly_reports": "maandrapport",
                        "quarterly_reports": "kwartaalrapport",
                    }.get(table_name, "rapport")
                    report_date = report.get("report_date")
                    summary = report.get("summary") or report.get("headline") or report.get("market_summary") or report.get("macro_summary")
                    response = (
                        f"Je kijkt nu naar je meest recente {period_label}"
                        f"{f' van {report_date}' if report_date else ''}. "
                        f"{summary if summary else 'Ik kan dit rapport verder uitsplitsen in score, risico en acties als je wilt.'}"
                    )
                    key_takeaways = [item for item in [
                        report.get("summary"),
                        report.get("market_summary"),
                        report.get("macro_summary"),
                        report.get("technical_summary"),
                    ] if item][:3]
                    risk_or_behavior = report.get("risk_summary") or report.get("behavioral_summary")
                    follow_up = report.get("recommended_action") or "Gebruik dit rapport als startpunt voor Mission Control of een score-uitleg."
                    if key_takeaways:
                        response += f" Belangrijkste punten: {' | '.join(key_takeaways[:2])}."
                    if risk_or_behavior:
                        response += f" Let extra op: {risk_or_behavior}."
                    response += f" Volgende stap: {follow_up}"
                    return self._context_explain_payload(
                        response=response,
                        confidence=report_confidence,
                        entity_type="report",
                        entity={
                            "table_name": table_name,
                            "report": report,
                            "report_date": report_date,
                            "report_type": period_label,
                            "headline": summary,
                            "key_takeaways": key_takeaways,
                            "risk_or_behavior_callout": risk_or_behavior,
                            "recommended_follow_up": follow_up,
                        },
                        state_overrides={"report_type": table_name},
                    )

            response = (
                "Ik kan je rapport uitleggen, maar ik heb in deze context nog geen recente rapport-rij om veilig samen te vatten. "
                "Open gerust het rapport opnieuw of vraag welk dag-, week- of maandrapport je bedoelt."
            )
            return self._context_explain_payload(
                response=response,
                confidence=report_confidence,
                entity_type="report",
                entity={"table_name": self._report_table_from_query_or_context(query, context)},
            )

        if target == "strategy" and strategy_id and self.session:
            repo = StrategyRepository(self.session)
            service = StrategyService(self.session)
            row = await repo.get_raw_strategy_with_setup(int(strategy_id), user_id)
            strategy = service._format_strategy_row(row) if row else None
            if strategy:
                response = (
                    f"Je bekijkt nu strategie #{strategy['id']} '{strategy.get('name')}' voor {strategy.get('symbol')} "
                    f"op {strategy.get('timeframe')}, gekoppeld aan setup #{strategy.get('setup_id')} '{strategy.get('setup_name')}'."
                )
                return self._context_explain_payload(
                    response=response,
                    confidence=self._context_confidence_for_target(context, "strategy", query=query),
                    entity_type="strategy",
                    entity={
                        **strategy,
                        "operator_implication": "Gebruik deze strategie om entry-, stop- en targetlogica te toetsen voordat je een bot laat handelen.",
                    },
                    state_overrides={
                        "strategy_id": strategy["id"],
                        "setup_id": strategy.get("setup_id"),
                        "asset": strategy.get("symbol"),
                    },
                )

        if target == "strategy" and strategy_id:
            asset = self._asset_from_query_or_context(query, context)
            response = (
                f"Ik koppel je huidige context aan strategie #{strategy_id}"
                f"{f' voor {asset}' if asset else ''}. "
                "Ik baseer dat op je recente leescontext, dus ik ben concreet genoeg om deze strategie te volgen "
                "ook als ik in deze turn niet de volledige strategie-rij opnieuw ophaal."
            )
            return self._context_explain_payload(
                response=response,
                confidence=self._context_confidence_for_target(context, "strategy", query=query),
                entity_type="strategy",
                entity={"id": strategy_id, "asset": asset},
                state_overrides={"strategy_id": strategy_id, "asset": asset},
            )

        if target == "setup" and setup_id and self.session:
            service = SetupService(self.session)
            setup = await service.get_setup_by_id(int(setup_id), user_id)
            if setup:
                response = (
                    f"Je hebt nu setup #{setup['id']} '{setup.get('name')}' open voor {setup.get('symbol')} "
                    f"op {setup.get('timeframe')}. Type: {setup.get('setup_type')}."
                )
                return self._context_explain_payload(
                    response=response,
                    confidence=self._context_confidence_for_target(context, "setup", query=query),
                    entity_type="setup",
                    entity=setup,
                    state_overrides={
                        "setup_id": setup["id"],
                        "asset": setup.get("symbol"),
                    },
                )

        if target == "setup" and setup_id:
            asset = self._asset_from_query_or_context(query, context)
            response = (
                f"Ik koppel je huidige context aan setup #{setup_id}"
                f"{f' voor {asset}' if asset else ''}. "
                "Dat komt uit je recente leescontext, dus ik kan hier al concreet over zijn "
                "zonder eerst opnieuw de hele setup-rij op te halen."
            )
            return self._context_explain_payload(
                response=response,
                confidence=self._context_confidence_for_target(context, "setup", query=query),
                entity_type="setup",
                entity={"id": setup_id, "asset": asset},
                state_overrides={"setup_id": setup_id, "asset": asset},
            )

        if target == "bot" and bot_id:
            bot = None
            bot_today = {}
            if self.session:
                bot = await BotService(self.session).repository.get_bot_config(user_id, int(bot_id))
                if bot:
                    try:
                        bot_today = await BotService(self.session).get_bot_today(
                            user_id,
                            symbol=str(bot.get("symbol") or context.get("symbol") or "BTC").upper(),
                            lean=True,
                        )
                    except Exception:
                        bot_today = {}
            if bot:
                status_bits = []
                if bot.get("is_active"):
                    status_bits.append("actief")
                if bot.get("is_live"):
                    status_bits.append("live")
                status_text = ", ".join(status_bits) if status_bits else "niet actief"
                setup_suffix = ""
                if bot.get("setup_id"):
                    setup_name = bot.get("setup_name")
                    setup_suffix = f" op setup #{bot.get('setup_id')}"
                    if setup_name:
                        setup_suffix += f" '{setup_name}'"
                open_decisions = [
                    decision for decision in (bot_today.get("decisions") or [])
                    if int(decision.get("bot_id") or 0) == int(bot["id"])
                ]
                waiting_for = (
                    "een open bot-decision review"
                    if open_decisions else
                    "een nieuwe setup- of score-aanleiding"
                )
                operating_state = (
                    "reviewing"
                    if open_decisions else
                    "ready"
                    if bot.get("is_active") else
                    "waiting"
                )
                next_step = (
                    "Review eerst de open bot-decisions voordat je iets nieuws forceert."
                    if open_decisions else
                    "Wacht op nieuwe score- of setupbevestiging en controleer intussen de gekoppelde strategie."
                    if bot.get("is_active") else
                    "Check eerst waarom deze bot niet actief is en of de gekoppelde strategie nog de juiste context heeft."
                )
                response = (
                    f"Je werkt nu met bot #{bot['id']} '{bot.get('name')}' voor {bot.get('symbol')}. "
                    f"Status: {status_text}. "
                    f"Deze bot volgt strategie #{bot.get('strategy_id')} '{bot.get('strategy_name')}'"
                    f"{setup_suffix}. "
                    f"Mode: {bot.get('mode') or 'manual'}. "
                    f"Op dit moment draait hij inhoudelijk in state '{operating_state}' en wacht hij vooral op {waiting_for}. "
                    f"Er staan nu {len(open_decisions)} open decision(s) klaar voor review. "
                    f"Waarom deze bot bestaat: hij voert de strategie niet autonoom blind uit, maar bewaakt juist de vertaalslag van setup naar concrete review- of execution-momenten. "
                    f"Volgende logische stap: {next_step}"
                )
                return self._context_explain_payload(
                    response=response,
                    confidence=self._context_confidence_for_target(context, "bot", query=query),
                    entity_type="bot",
                    entity={
                        **bot,
                        "what_this_bot_is": f"Een {'live' if bot.get('is_live') else 'paper/manual'} bot voor {bot.get('symbol')}",
                        "linked_strategy": {"id": bot.get("strategy_id"), "name": bot.get("strategy_name")},
                        "linked_setup": {"id": bot.get("setup_id"), "name": bot.get("setup_name")},
                        "operating_mode": bot.get("mode") or "manual",
                        "why_it_exists": f"Deze bot ondersteunt strategie #{bot.get('strategy_id')} voor {bot.get('symbol')} en vertaalt setup-context naar reviewbare bot-beslissingen.",
                        "current_state": operating_state,
                        "what_it_is_waiting_for": waiting_for,
                        "open_decisions": open_decisions[:5],
                        "what_next": next_step,
                    },
                    state_overrides={
                        "bot_id": bot["id"],
                        "strategy_id": bot.get("strategy_id"),
                        "setup_id": bot.get("setup_id"),
                        "asset": bot.get("symbol"),
                    },
                )

            response = f"Je werkt nu met bot #{bot_id}. Als je wilt kan ik uitleggen waarom deze bot actief is, welke strategie hij volgt of welke review-openingen er zijn."
            return self._context_explain_payload(
                response=response,
                confidence=self._context_confidence_for_target(context, "bot", query=query),
                entity_type="bot",
                entity={"id": bot_id},
                state_overrides={"bot_id": bot_id},
            )

        if target == "asset":
            asset = self._asset_from_query_or_context(query, context)
            asset_confidence = self._context_confidence_for_target(context, "asset", query=query, asset=asset)
            related_bot_id = context.get("bot_id")
            if asset_confidence["level"] == "low":
                return self._context_explain_payload(
                    response="Ik zie nog geen zekere asset-context. Wat ik nu wél zie is je pagina- of productcontext, maar niet veilig welk asset centraal staat. Noem gerust het asset expliciet of open de asset-surface opnieuw, dan word ik specifieker.",
                    confidence=asset_confidence,
                    entity_type="asset",
                    entity={"asset": None, "bot_id": related_bot_id},
                )
            bot_fragment = ""
            if related_bot_id:
                bot_fragment = f" en bot #{related_bot_id} als je huidige bot-context"
                if self.session:
                    try:
                        bot = await BotService(self.session).repository.get_bot_config(user_id, int(related_bot_id))
                    except Exception:
                        bot = None
                    if bot:
                        bot_fragment = (
                            f" en bot #{related_bot_id} '{bot.get('name')}'"
                            f" op strategie #{bot.get('strategy_id')}"
                        )
            response = (
                f"Ik zie nu vooral {asset} als actief asset{bot_fragment}. "
                "Daar ben ik voldoende zeker van om concreet te zijn. "
                "Wat ik nog niet automatisch invul is of je nu score-, setup-, strategie- of botuitleg wilt; dat kan ik wel meteen uitsplitsen als je dat vraagt."
            )
            return self._context_explain_payload(
                response=response,
                confidence=asset_confidence,
                entity_type="asset",
                entity={"asset": asset, "bot_id": related_bot_id},
                state_overrides={"asset": asset, "bot_id": related_bot_id},
            )

        if target in {"setup", "strategy", "bot", "report"}:
            asset = self._asset_from_query_or_context(query, context)
            if asset and confidence.get("level") == "low":
                label = {
                    "setup": "setup",
                    "strategy": "strategie",
                    "bot": "bot",
                    "report": "rapport",
                }.get(target, target)
                response = (
                    f"Ik zie wel {asset} als je actieve asset-context, maar ik zie in deze view nog geen zekere {label}-entiteit om veilig specifieker te worden. "
                    f"Ik kan dus al zeggen dat je nu rond {asset} werkt, maar niet welke {label} exact open staat. "
                    f"Open gerust de {label}-surface opnieuw of noem het id expliciet, dan maak ik het concreet."
                )
                return self._context_explain_payload(
                    response=response,
                    confidence=confidence,
                    entity_type=target,
                    entity={"asset": asset},
                    state_overrides={"asset": asset},
                )

        response = (
            "Ik kan je huidige context uitleggen, maar ik zie nog geen zekere entiteit om veilig specifiek te worden. "
            "Wat ik wél zie is je huidige pagina- of assetcontext. Noem gerust het setup-, strategie- of bot-id, "
            "of open die surface opnieuw zodat ik gerichter kan zijn."
        )
        return self._context_explain_payload(
            response=response,
            confidence=confidence,
            entity_type="unknown",
        )

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

        if self._is_plan_deviation_ack(q_lower):
            draft["plan_deviation_ack"] = True

        if explicit_create_intent and not explicit_update_intent:
            draft["operation"] = "create"
            draft["strategy_id"] = None
            draft.pop("changes", None)
            draft.pop("plan_deviation", None)
            draft.pop("plan_deviation_ack", None)

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
                    "Je vraag klinkt nu als een nieuwe strategie, maar ik maak hier niet stilletjes een tweede strategie of verborgen update van. "
                    "Zeg bijvoorbeeld 'pas de strategie aan met 150 euro' als je deze bestaande strategie bewust wilt bijwerken."
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
            pressure_context = await self._plan_deviation_context_for_draft(user_id, draft)
            behavioral_event = self._behavioral_event_from_strategy_draft(draft, pressure_context)
            draft["plan_deviation"] = self._plan_deviation_warning_from_event(behavioral_event, acknowledged=bool(draft.get("plan_deviation_ack")))
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
                    "plan_deviation": draft.get("plan_deviation"),
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
        if self._is_plan_deviation_ack(q_lower):
            draft["plan_deviation_ack"] = True

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

        pressure_context = await self._plan_deviation_context_for_draft(user_id, draft)
        behavioral_event = self._behavioral_event_from_bot_draft(draft, pressure_context)
        draft["plan_deviation"] = self._plan_deviation_warning_from_event(behavioral_event, acknowledged=bool(draft.get("plan_deviation_ack")))
        validation = self._validate_bot_draft(draft)

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
                    "plan_deviation": draft.get("plan_deviation"),
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
            agent_verdicts = self._build_plan_status_agent_verdicts(asset, analysis, source="draft")
            analysis["agent_verdicts"] = agent_verdicts
            response = self._status_message(asset, analysis, source="draft")
        else:
            matching_setups = [s for s in active_setups if str(s.get("symbol", "")).upper() == asset]
            best_setup = next((s for s in matching_setups if s.get("is_active")), None) or (matching_setups[0] if matching_setups else None)
            analysis = self._evaluate_setup_row(best_setup, daily_scores)
            agent_verdicts = self._build_plan_status_agent_verdicts(asset, analysis, source="saved_setup")
            analysis["agent_verdicts"] = agent_verdicts
            response = self._status_message(asset, analysis, source="saved_setup")
        agent_controller = self._build_agent_controller(agent_verdicts, context="plan_status")
        agent_controller["primary_action"] = self._agent_controller_primary_action(
            agent_controller,
            [],
            asset=asset,
        )
        analysis["agent_controller"] = agent_controller
        analysis["execution_review"] = self._build_plan_status_execution_review(asset, analysis, source="draft" if draft and draft.get("asset") == asset else "saved_setup")

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
                "agent_verdicts": agent_verdicts,
                "agent_controller": agent_controller,
                "autonomy_level": "advice_only",
            },
            "reasoning": {
                "confidence_score": 0.55 if analysis.get("confidence") == "medium" else 0.25,
                "risk_detected": not bool(analysis.get("is_active")),
                "reasons": self._analysis_reasons(analysis),
                "coaching_level": "plan_check",
            },
        }

    def _decision_review_subject(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = context or {}
        q = self._normalized_query(query)
        if any(term in q for term in ["trade", "instap", "entry", "kopen", "verkopen"]):
            entity_type = "trade"
        else:
            entity_type = None
        state_entity = self._read_only_state_entity(context)
        entity_type = entity_type or (
            state_entity.get("entity_type")
            or ("bot" if context.get("bot_id") else None)
            or ("strategy" if context.get("strategy_id") else None)
            or ("setup" if context.get("setup_id") else None)
        )
        if "bot" in q and "decision" in q:
            entity_type = "bot"
        elif "setup" in q:
            entity_type = "setup"
        elif "strategie" in q or "strategy" in q:
            entity_type = "strategy"
        entity_type = entity_type or "trade"
        review_type_map = {
            "trade": "trade_intent_review",
            "setup": "setup_readiness_review",
            "strategy": "strategy_fit_review",
            "bot": "bot_decision_review",
        }
        return {
            "entity_type": entity_type,
            "entity_id": (
                context.get("bot_id") if entity_type == "bot" else
                context.get("strategy_id") if entity_type == "strategy" else
                context.get("setup_id") if entity_type == "setup" else
                None
            ),
            "review_type": review_type_map.get(entity_type, "trade_intent_review"),
        }

    def _risk_pct_from_query(self, query: str) -> Optional[float]:
        q = self._normalized_query(query)
        if "all-in" in q or "all in" in q:
            return 100.0
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", q)
        if not match:
            return None
        try:
            return float(match.group(1).replace(",", "."))
        except ValueError:
            return None

    def _explicit_setup_score_from_query(self, query: str) -> Optional[float]:
        q = self._normalized_query(query)
        match = re.search(r"(?:setup\s*score|score)\s*[:=]?\s*(\d+(?:[.,]\d+)?)", q)
        if not match:
            return None
        try:
            return float(match.group(1).replace(",", "."))
        except ValueError:
            return None

    def _qualitative_level_from_query(self, query: str, field: str) -> Optional[str]:
        q = self._normalized_query(query)
        match = re.search(
            rf"{re.escape(field)}\s*[:=]?\s*(hoog|high|medium|gemiddeld|laag|low)",
            q,
        )
        if not match:
            return None
        value = str(match.group(1)).lower()
        if value in {"hoog", "high"}:
            return "high"
        if value in {"laag", "low"}:
            return "low"
        return "medium"

    def _portfolio_context_from_explicit_mix(self, explicit_mix: Dict[str, Any]) -> Dict[str, Any]:
        allocations = explicit_mix.get("allocations") or {}
        asset_risk: List[Dict[str, Any]] = []
        concentration_warnings: List[Dict[str, Any]] = []
        risk_stacks: List[Dict[str, Any]] = []
        ranked_conflicts: List[Dict[str, Any]] = []
        asset_priority: List[Dict[str, Any]] = []
        for asset_name, pct in allocations.items():
            risk_level = "high" if pct >= 60 else "medium" if pct >= 40 else "low"
            risk_score = min(95, max(10, int(round(float(pct)))))
            warning = None
            if pct >= 60:
                warning = f"{asset_name} draagt al ongeveer {pct:.0f}% van je allocatie."
                concentration_warnings.append({"asset": asset_name, "reason": warning})
                risk_stacks.append({"asset": asset_name, "reason": f"{asset_name} stapelt concentratierisico."})
                ranked_conflicts.append({"asset": asset_name, "reason": warning})
            asset_risk.append({
                "asset": asset_name,
                "risk_level": risk_level,
                "risk_score": risk_score,
                "allocation_pct": pct,
                "next_best_action": (
                    f"Voeg niet meer toe aan {asset_name} voordat je concentratie verlaagt."
                    if pct >= 60 else None
                ),
            })
            asset_priority.append({
                "asset": asset_name,
                "risk_score": risk_score,
                "reason": "high_exposure" if pct >= 60 else "watch_exposure",
            })
        dominant_asset = str(explicit_mix.get("dominant_asset") or "").upper() or None
        dominant_pct = float(explicit_mix.get("dominant_pct") or 0)
        status = "concentrated" if dominant_pct >= 60 else "watch" if dominant_pct >= 40 else "balanced"
        message = (
            f"{dominant_asset} domineert deze expliciete portfolio-mix met ongeveer {dominant_pct:.0f}% allocatie."
            if dominant_asset and dominant_pct >= 60 else
            f"{dominant_asset} draagt nu relatief veel gewicht in je expliciete mix."
            if dominant_asset and dominant_pct >= 40 else
            "Je expliciete portfolio-mix oogt niet extreem geconcentreerd."
        )
        return {
            "global": {"allocations_pct": allocations},
            "status": status,
            "message": message,
            "asset_risk": sorted(asset_risk, key=lambda item: item.get("risk_score") or 0, reverse=True),
            "concentration_warnings": concentration_warnings,
            "risk_stacks": risk_stacks,
            "ranked_conflicts": ranked_conflicts,
            "asset_priority": sorted(asset_priority, key=lambda item: item.get("risk_score") or 0, reverse=True),
        }

    def _decision_review_snapshot(
        self,
        *,
        subject: Dict[str, Any],
        asset: str,
        checks: List[Dict[str, Any]],
        decision_status: str,
        top_blockers: List[str],
        recommended_changes: List[str],
    ) -> Dict[str, Any]:
        return {
            "subject_type": subject.get("entity_type"),
            "subject_id": subject.get("entity_id"),
            "asset": asset,
            "triggered_checks": [check.get("id") for check in checks],
            "outcome": decision_status,
            "top_blocker": top_blockers[0] if top_blockers else None,
            "recommendation_summary": recommended_changes[0] if recommended_changes else None,
            "timestamp": _utc_now().isoformat(),
        }

    def _decision_review_label(self, review_type: str) -> str:
        return {
            "trade_intent_review": "trade review",
            "setup_readiness_review": "setup review",
            "strategy_fit_review": "strategie review",
            "bot_decision_review": "bot review",
        }.get(review_type, review_type.replace("_", " "))

    def _decision_review_message(self, analysis: Dict[str, Any]) -> str:
        checks = analysis.get("checks") or []
        top_blockers = analysis.get("top_blockers") or []
        recommended_changes = analysis.get("recommended_changes") or []
        lines = [
            analysis.get("headline") or "Hier is mijn review van je volgende trading-beslissing.",
            f"Status: {analysis.get('decision_status')}.",
            analysis.get("risk_summary") or "",
        ]
        if analysis.get("context_anchor"):
            lines.append(f"Contextanker: {analysis.get('context_anchor')}.")
        if checks:
            lines.append("Checks:")
            for check in checks[:4]:
                lines.append(f"- {check.get('label')}: {check.get('detail')}")
        if top_blockers:
            lines.append("Top blockers:")
            lines.extend(f"- {item}" for item in top_blockers[:3])
        if recommended_changes:
            lines.append("Aanpassingen:")
            lines.extend(f"- {item}" for item in recommended_changes[:3])
        if analysis.get("operator_next_step"):
            lines.append(f"Volgende stap: {analysis.get('operator_next_step')}")
        return "\n".join([line for line in lines if line])

    def _governance_event_signature(self, event_type: str, payload: Dict[str, Any]) -> str:
        stable_payload = {
            "type": event_type,
            "asset": payload.get("asset"),
            "subject": payload.get("subject"),
            "decision_status": payload.get("decision_status"),
            "adherence_status": payload.get("adherence_status"),
            "behavior_pattern": payload.get("behavior_pattern"),
            "query": self._normalized_query(str(payload.get("query") or "")),
        }
        digest = hashlib.sha256(json.dumps(stable_payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        return digest[:24]

    async def _record_governance_event(
        self,
        user_id: int,
        *,
        event_type: str,
        symbol: Optional[str],
        title: str,
        description: str,
        severity: str,
        payload: Dict[str, Any],
        cooldown_hours: int = 6,
    ) -> None:
        if not self.session:
            return
        signature = self._governance_event_signature(event_type, payload)
        cooldown_threshold = _utc_db_timestamp() - timedelta(hours=max(1, cooldown_hours))
        existing = await self.session.execute(text("""
            SELECT 1
            FROM ai_intelligence_events
            WHERE user_id = :user_id
              AND type = :event_type
              AND COALESCE(symbol, '') = COALESCE(:symbol, '')
              AND created_at >= :cooldown_threshold
              AND COALESCE(payload->>'signature', '') = :signature
            LIMIT 1
        """), {
            "user_id": user_id,
            "event_type": event_type,
            "symbol": symbol,
            "cooldown_threshold": cooldown_threshold,
            "signature": signature,
        })
        if existing.fetchone():
            return

        stored_payload = {**payload, "signature": signature, "trace_id": self.trace_id}
        await self.session.execute(text("""
            INSERT INTO ai_intelligence_events (user_id, type, symbol, title, description, severity, payload, status)
            VALUES (:user_id, :event_type, :symbol, :title, :description, :severity, CAST(:payload AS JSONB), 'active')
        """), {
            "user_id": user_id,
            "event_type": event_type,
            "symbol": symbol,
            "title": title,
            "description": description,
            "severity": severity,
            "payload": json.dumps(stored_payload, default=str),
        })
        await self.session.commit()

    async def _fetch_recent_governance_events(
        self,
        user_id: int,
        *,
        event_types: List[str],
        limit: int = 40,
    ) -> List[Dict[str, Any]]:
        if not self.session or not event_types or not hasattr(self.session, "execute"):
            return []
        rows = await self.session.execute(text("""
            SELECT id, type, symbol, title, description, severity, payload, status, created_at
            FROM ai_intelligence_events
            WHERE user_id = :user_id
              AND type = ANY(:event_types)
            ORDER BY created_at DESC
            LIMIT :limit
        """), {
            "user_id": user_id,
            "event_types": event_types,
            "limit": max(1, min(limit, 200)),
        })
        events: List[Dict[str, Any]] = []
        for row in rows.fetchall():
            mapping = dict(row._mapping)
            payload = mapping.get("payload")
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = {}
            mapping["payload"] = payload if isinstance(payload, dict) else {}
            events.append(mapping)
        return events

    def _governance_event_follow_through(
        self,
        event: Dict[str, Any],
        activity_feed: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        created_at = self._parse_mission_timestamp(event.get("created_at"))
        subject = payload.get("subject") if isinstance(payload.get("subject"), dict) else {}
        subject_type = subject.get("type")
        subject_id = subject.get("id")
        asset = payload.get("asset") or event.get("symbol")
        matches: List[Dict[str, Any]] = []
        for item in activity_feed or []:
            item_at = self._parse_mission_timestamp(item.get("created_at"))
            if not item_at or not created_at or item_at < created_at:
                continue
            if item_at > created_at + timedelta(days=14):
                continue
            item_ids = item.get("entity_ids") if isinstance(item.get("entity_ids"), dict) else {}
            if subject_type == "bot" and subject_id and item_ids.get("bot_id") == subject_id:
                matches.append(item)
                continue
            if subject_type == "strategy" and subject_id and item_ids.get("strategy_id") == subject_id:
                matches.append(item)
                continue
            if subject_type == "setup" and subject_id and item_ids.get("setup_id") == subject_id:
                matches.append(item)
                continue
            if asset and str(item.get("asset") or "").upper() == str(asset).upper():
                matches.append(item)

        counters = {
            "executed": 0,
            "blocked": 0,
            "skipped": 0,
            "reviewed": 0,
        }
        for item in matches:
            item_type = str(item.get("type") or "")
            resolve_state = str(item.get("resolve_state") or "")
            if item_type in {"paper_execute_bot_decision", "live_manual_order_confirmed", "manual_order"}:
                counters["executed"] += 1
            elif item_type in {"live_manual_order_blocked"}:
                counters["blocked"] += 1
            elif item_type in {"live_preflight_bot_decision", "live_manual_order_preflight"}:
                counters["reviewed"] += 1
            elif resolve_state == "skipped" or item_type == "skip_bot_decision":
                counters["skipped"] += 1

        if counters["executed"] > max(counters["blocked"], counters["skipped"]):
            resolution = "executed"
        elif counters["blocked"] > 0 and counters["blocked"] >= counters["executed"]:
            resolution = "blocked"
        elif counters["skipped"] > 0 and counters["skipped"] >= counters["executed"]:
            resolution = "skipped"
        elif counters["reviewed"] > 0:
            resolution = "reviewed_only"
        else:
            resolution = "no_follow_through_yet"

        return {
            "resolution": resolution,
            "counters": counters,
            "sample": matches[:5],
        }

    def _outcome_tracking_message(self, analysis: Dict[str, Any]) -> str:
        lines = [
            analysis.get("headline") or "Hier is wat Finn voorzichtig uit je uitkomsten kan halen.",
            analysis.get("historical_result_summary") or "",
            analysis.get("net_effect") or "",
            analysis.get("confidence_note") or "",
        ]
        if analysis.get("operator_next_step"):
            lines.append(f"Volgende stap: {analysis.get('operator_next_step')}")
        return "\n".join([line for line in lines if line])

    def _outcome_memory_message(self, analysis: Dict[str, Any]) -> str:
        lines = [
            analysis.get("headline") or "Hier is wat Finn nu echt uit je uitkomsten onthoudt.",
            f"Pattern: {analysis.get('memory_pattern')}.",
            analysis.get("behavioral_cost") or "",
        ]
        if analysis.get("repeat_trigger"):
            lines.append(f"Terugkerende trigger: {analysis.get('repeat_trigger')}")
        if analysis.get("supporting_evidence_count") is not None:
            lines.append(
                f"Evidence: {analysis.get('supporting_evidence_count')} signalen in {analysis.get('time_window')} "
                f"({analysis.get('confidence_level')} confidence)."
            )
        if analysis.get("latest_outcome_summary"):
            lines.append(f"Laatste duidelijke uitkomstlijn: {analysis.get('latest_outcome_summary')}")
        if analysis.get("recommended_rule"):
            lines.append(f"Aanbevolen regel: {analysis.get('recommended_rule')}")
        evidence = analysis.get("supporting_evidence") or []
        if evidence:
            lines.append("Waarom Finn dit onthoudt:")
            for item in evidence[:3]:
                lines.append(f"- {item}")
        if analysis.get("operator_next_step"):
            lines.append(f"Volgende stap: {analysis.get('operator_next_step')}")
        return "\n".join([line for line in lines if line])

    def _personal_performance_message(self, analysis: Dict[str, Any]) -> str:
        lines = [
            analysis.get("headline") or "Hier is hoe Finn je persoonlijke trading performance nu leest.",
            (
                f"Performance-score: {analysis.get('performance_score')}/100."
                if analysis.get("performance_score") is not None else
                "Performance-score: nog niet sterk genoeg te onderbouwen."
            ),
        ]
        breakdown = analysis.get("score_breakdown") or []
        if breakdown:
            lines.append("Score-opbouw:")
            for item in breakdown[:5]:
                lines.append(f"- {item.get('label')}: {item.get('score')}/100 - {item.get('summary')}")
        drivers = analysis.get("performance_drivers") or []
        if drivers:
            lines.append("Wat nu het zwaarst meeweegt:")
            for item in drivers[:4]:
                lines.append(f"- {item.get('label')}: {item.get('summary')}")
        if analysis.get("discipline_delta"):
            delta = analysis.get("discipline_delta") or {}
            lines.append(f"Discipline-delta: {delta.get('summary') or delta.get('direction')}")
        if analysis.get("recovery_status"):
            lines.append(f"Herstelstatus: {analysis.get('recovery_status')}")
        risk_flags = analysis.get("performance_risk_flags") or []
        if risk_flags:
            lines.append("Prestatie-risico's:")
            for item in risk_flags[:3]:
                lines.append(f"- {item}")
        if analysis.get("next_growth_target"):
            lines.append(f"Volgende groeidoel: {analysis.get('next_growth_target')}")
        if analysis.get("operator_next_step"):
            lines.append(f"Veilige volgende stap: {analysis.get('operator_next_step')}")
        return "\n".join([line for line in lines if line])

    def _trade_journal_intelligence_message(self, analysis: Dict[str, Any]) -> str:
        lines = [
            analysis.get("headline") or "Hier is wat Finn uit je trade-journal signalen en reviewtaal haalt.",
            f"Journal-pattern: {analysis.get('journal_pattern')}.",
        ]
        tags = analysis.get("journal_tags") or []
        if tags:
            lines.append("Tags: " + ", ".join(tags[:6]))
        if analysis.get("thesis_quality"):
            lines.append(f"Thesis-kwaliteit: {analysis.get('thesis_quality')}")
        if analysis.get("emotion_signal"):
            lines.append(f"Emotioneel signaal: {analysis.get('emotion_signal')}")
        if analysis.get("decision_gap"):
            lines.append(f"Beslisgat: {analysis.get('decision_gap')}")
        if analysis.get("post_trade_lesson"):
            lines.append(f"Post-trade les: {analysis.get('post_trade_lesson')}")
        if analysis.get("journal_coaching_note"):
            lines.append(f"Coachnotitie: {analysis.get('journal_coaching_note')}")
        evidence = analysis.get("supporting_evidence") or []
        if evidence:
            lines.append("Ondersteunend bewijs:")
            for item in evidence[:3]:
                lines.append(f"- {item}")
        if analysis.get("operator_next_step"):
            lines.append(f"Volgende stap: {analysis.get('operator_next_step')}")
        return "\n".join([line for line in lines if line])

    def _personal_coach_message(self, analysis: Dict[str, Any]) -> str:
        mode = str(analysis.get("coach_mode") or "")
        if mode == "interruptive":
            lines = [
                "Stop even en onderbreek deze lus nu.",
                analysis.get("current_pattern") or "Ik zie een patroon dat nu niet geholpen moet worden door snelheid.",
                f"Wat dit kost: {analysis.get('what_it_costs')}",
                f"Wat je nu moet onderbreken: {analysis.get('what_to_interrupt_now')}",
                f"Volgende regel: {analysis.get('next_best_rule')}",
            ]
        elif mode == "recovery":
            lines = [
                "Je hoeft dit nu niet terug te winnen; eerst herstel.",
                analysis.get("current_pattern") or "Ik zie herstelgedrag als eerstvolgende prioriteit.",
                f"Wat dit kost: {analysis.get('what_it_costs')}",
                f"Wat je nu moet onderbreken: {analysis.get('what_to_interrupt_now')}",
                f"Volgende regel: {analysis.get('next_best_rule')}",
            ]
        elif mode == "pre_trade":
            lines = [
                "Voor je iets nieuws doet: laat kwaliteit eerst winnen van drang.",
                analysis.get("current_pattern") or "Ik zie pre-trade druk op je oordeel.",
                f"Wat dit kost: {analysis.get('what_it_costs')}",
                f"Wat je nu moet onderbreken: {analysis.get('what_to_interrupt_now')}",
                f"Volgende regel: {analysis.get('next_best_rule')}",
            ]
        elif mode == "post_trade":
            lines = [
                "Gebruik dit moment niet om jezelf gelijk te geven, maar om iets bruikbaars te leren.",
                analysis.get("current_pattern") or "Ik zie een patroon dat beter wordt als je het expliciet terugleest.",
                f"Wat dit kost: {analysis.get('what_it_costs')}",
                f"Wat je nu moet onderbreken: {analysis.get('what_to_interrupt_now')}",
                f"Volgende regel: {analysis.get('next_best_rule')}",
            ]
        else:
            lines = [
                "Ik coach je hier op je echte gedrag, niet alleen op de trade voor je neus.",
                analysis.get("current_pattern") or "Ik zie nog geen enkelvoudig patroon dat alles overstemt.",
                f"Wat dit kost: {analysis.get('what_it_costs')}",
                f"Wat je nu moet onderbreken: {analysis.get('what_to_interrupt_now')}",
                f"Volgende regel: {analysis.get('next_best_rule')}",
            ]
        if analysis.get("coach_follow_up"):
            lines.append(f"Follow-up: {analysis.get('coach_follow_up')}")
        evidence = analysis.get("supporting_signals") or []
        if evidence:
            lines.append("Waar ik dit op baseer:")
            for item in evidence[:3]:
                lines.append(f"- {item}")
        return "\n".join([line for line in lines if line])

    def _portfolio_intelligence_contract(
        self,
        *,
        risk: Dict[str, Any],
        asset: Optional[str] = None,
    ) -> Dict[str, Any]:
        asset_risk = risk.get("asset_risk") or []
        focus = None
        if asset:
            focus = next((item for item in asset_risk if str(item.get("asset") or "").upper() == str(asset).upper()), None)
        focus = focus or (asset_risk[0] if asset_risk else {})
        concentration = (risk.get("concentration_warnings") or [None])[0] or {}
        stack = next(
            (item for item in (risk.get("risk_stacks") or []) if not asset or str(item.get("asset") or "").upper() == str(asset).upper()),
            None,
        ) or ((risk.get("risk_stacks") or [None])[0] or {})
        blockers = []
        for item in (risk.get("ranked_conflicts") or risk.get("conflicts") or [])[:4]:
            if asset and str(item.get("asset") or "").upper() != str(asset).upper():
                continue
            blockers.append(item.get("reason"))
        portfolio_impact = {
            "status": risk.get("status"),
            "message": risk.get("message"),
            "focus_asset": focus.get("asset") or asset,
            "focus_risk_level": focus.get("risk_level"),
            "focus_risk_score": focus.get("risk_score"),
        }
        exposure_delta = None
        if focus.get("allocation_pct") is not None:
            exposure_delta = f"{focus.get('asset')} zit nu rond {focus.get('allocation_pct')}% allocatie."
        concentration_warning = concentration.get("reason")
        stacked_risk_warning = stack.get("reason")
        portfolio_safe_alternative = (
            focus.get("next_best_action")
            or (risk.get("ignore_today_assets") or [{}])[0].get("unblock_condition")
            or "Kies eerst de asset met de laagste risk stack voordat je exposure toevoegt."
        )
        return {
            "portfolio_impact": portfolio_impact,
            "exposure_delta": exposure_delta,
            "concentration_warning": concentration_warning,
            "stacked_risk_warning": stacked_risk_warning,
            "portfolio_blockers": [item for item in blockers if item][:3],
            "portfolio_safe_alternative": portfolio_safe_alternative,
        }

    def _portfolio_intelligence_message(self, analysis: Dict[str, Any]) -> str:
        lines = [
            analysis.get("headline") or "Hier is mijn portfolio-intelligence review.",
            (analysis.get("portfolio_impact") or {}).get("message") or "",
        ]
        if analysis.get("exposure_delta"):
            lines.append(f"Exposure: {analysis.get('exposure_delta')}")
        if analysis.get("concentration_warning"):
            lines.append(f"Concentratie: {analysis.get('concentration_warning')}")
        if analysis.get("stacked_risk_warning"):
            lines.append(f"Stacked risk: {analysis.get('stacked_risk_warning')}")
        blockers = analysis.get("portfolio_blockers") or []
        if blockers:
            lines.append("Portfolio blockers:")
            lines.extend(f"- {item}" for item in blockers[:3])
        if analysis.get("portfolio_safe_alternative"):
            lines.append(f"Veiliger alternatief: {analysis.get('portfolio_safe_alternative')}")
        return "\n".join([line for line in lines if line])

    def _governed_action_review_message(self, analysis: Dict[str, Any]) -> str:
        status = str(analysis.get("governance_status") or "recommend")
        action_type = str(analysis.get("action_type") or "actie").replace("_", " ")
        labels = {
            "explain": f"Deze {action_type} is nu vooral iets om uit te leggen en voor te bereiden.",
            "recommend": f"Deze {action_type} lijkt inhoudelijk verdedigbaar, maar ik zou hem nog niet blind doorzetten.",
            "confirm": f"Deze {action_type} mag alleen verder via expliciete bevestiging en guardrails.",
            "block": f"Deze {action_type} blokkeer ik nu op governance-gronden.",
        }
        lines = [labels.get(status, labels["recommend"])]
        if analysis.get("blocking_reason"):
            lines.append(f"Waarom: {analysis.get('blocking_reason')}")
        warnings = analysis.get("warnings") or []
        if warnings:
            lines.append("Let op:")
            lines.extend(f"- {item}" for item in warnings[:3])
        confirmation_required = analysis.get("confirmation_required")
        if confirmation_required is not None:
            lines.append(f"Bevestiging nodig: {'ja' if confirmation_required else 'nee'}.")
        auditability = analysis.get("auditability") or {}
        if auditability.get("audit_required") is not None:
            lines.append(
                f"Logging: {'audit log verplicht' if auditability.get('audit_required') else 'lichte trace voldoende'}."
            )
        required_agents = analysis.get("required_agents") or []
        if required_agents:
            lines.append(
                "Betrek eerst: "
                + ", ".join(str(agent.get("name") or "").strip() for agent in required_agents[:3] if agent.get("name"))
                + "."
            )
        lines.append(f"Volgende stap: {analysis.get('recommended_next_step')}")
        return "\n".join([line for line in lines if line])

    async def build_governed_action_review_response(
        self,
        user_id: int,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = dict(context or {})
        context["query"] = query
        action = self._infer_governed_action_from_query(query, context)
        policy = self.action_policy_service.resolve_action_policy(
            action["action_type"],
            subject_type=action.get("subject_type"),
            subject_id=action.get("subject_id"),
        )
        lightweight_prompt = self._is_lightweight_governance_prompt(query)
        lightweight_snapshot = self._lightweight_governance_snapshot(
            query=query,
            context=context,
            action=action,
        ) if lightweight_prompt else {}

        decision_review = {}
        if action["action_type"] in {
            "decision_review",
            "setup_review",
            "strategy_review",
            "bot_review",
            "activate_setup",
            "activate_bot",
            "live_manual_order",
            "save_trade_plan",
            "portfolio_rebalance",
        } and not lightweight_prompt:
            decision_review = await self.build_decision_review_response(user_id, query, context)

        plan_adherence = {}
        if action["action_type"] in {"activate_setup", "activate_bot", "live_manual_order", "save_trade_plan", "portfolio_rebalance"} and not lightweight_prompt:
            plan_adherence = await self.build_plan_adherence_review_response(user_id, query, context)

        portfolio_intelligence = {}
        if (
            action["action_type"] in {"portfolio_review", "activate_bot", "live_manual_order", "portfolio_rebalance", "decision_review"}
            and not lightweight_prompt
        ):
            portfolio_intelligence = await self.build_portfolio_intelligence_response(user_id, query, context)

        decision_analysis = (
            (decision_review.get("analysis") if isinstance(decision_review.get("analysis"), dict) else {})
            or (decision_review.get("state") or {}).get("analysis")
            or {}
        )
        if not decision_analysis and lightweight_snapshot.get("decision_analysis"):
            decision_analysis = lightweight_snapshot.get("decision_analysis") or {}
        adherence_analysis = (
            (plan_adherence.get("analysis") if isinstance(plan_adherence.get("analysis"), dict) else {})
            or (plan_adherence.get("state") or {}).get("analysis")
            or {}
        )
        if not adherence_analysis and lightweight_snapshot.get("adherence_analysis"):
            adherence_analysis = lightweight_snapshot.get("adherence_analysis") or {}
        portfolio_analysis = (
            (portfolio_intelligence.get("analysis") if isinstance(portfolio_intelligence.get("analysis"), dict) else {})
            or (portfolio_intelligence.get("state") or {}).get("analysis")
            or {}
        )
        if not portfolio_analysis and lightweight_snapshot.get("portfolio_analysis"):
            portfolio_analysis = lightweight_snapshot.get("portfolio_analysis") or {}

        context_sufficiency = self._governed_action_context_sufficiency(
            action_type=action["action_type"],
            context=context,
            decision_status=decision_analysis.get("decision_status"),
        )

        plan_alignment = "aligned"
        adherence_status = str(adherence_analysis.get("adherence_status") or "")
        if adherence_status in {"outside_plan", "forced_override"}:
            plan_alignment = "conflict"
        elif adherence_status in {"insufficiently_justified", "warn"}:
            plan_alignment = "warn"

        portfolio_conflict_level = "low"
        blockers = portfolio_analysis.get("portfolio_blockers") or []
        if blockers:
            portfolio_conflict_level = "high"
        elif portfolio_analysis.get("concentration_warning") or portfolio_analysis.get("stacked_risk_warning"):
            portfolio_conflict_level = "medium"

        governance = self.execution_governance_service.evaluate(
            action_policy=policy,
            context_sufficiency=context_sufficiency,
            plan_alignment=plan_alignment,
            portfolio_conflict_level=portfolio_conflict_level,
            explicit_execution_sensitive=action["action_type"] in {"live_manual_order", "activate_bot", "portfolio_rebalance"},
            decision_status=decision_analysis.get("decision_status"),
            portfolio_blockers=blockers,
        )
        required_agents = self._governed_action_required_agents(
            action_type=action["action_type"],
            query=query,
            context=context,
        )

        analysis = {
            **governance,
            "policy": policy,
            "action_subject": action,
            "required_agents": required_agents,
            "agent_orchestration": {
                "required_agents": required_agents,
                "orchestration_status": "pre_execution_review" if required_agents else "minimal",
                "autonomous_execution_allowed": False,
            },
            "auditability": {
                "audit_required": governance.get("audit_required"),
                "rollback_mode": governance.get("rollback_mode"),
                "trace_required": True,
            },
            "decision_review": {
                "decision_status": decision_analysis.get("decision_status"),
                "risk_summary": decision_analysis.get("risk_summary"),
                "operator_next_step": decision_analysis.get("operator_next_step"),
            } if decision_analysis else {},
            "plan_adherence": {
                "adherence_status": adherence_analysis.get("adherence_status"),
                "threatened_rule": adherence_analysis.get("threatened_rule"),
                "suggested_recovery_step": adherence_analysis.get("suggested_recovery_step"),
            } if adherence_analysis else {},
            "portfolio_intelligence": {
                "concentration_warning": portfolio_analysis.get("concentration_warning"),
                "stacked_risk_warning": portfolio_analysis.get("stacked_risk_warning"),
                "portfolio_safe_alternative": portfolio_analysis.get("portfolio_safe_alternative"),
            } if portfolio_analysis else {},
            "mode": "read_only",
            "route_source": "finn",
        }

        return {
            "response": self._governed_action_review_message(analysis),
            "intent": "governed_action_review",
            "flow": "governed_action_review",
            "draft": None,
            "missing_fields": [],
            "invalid_fields": [],
            "next_question": None,
            "can_confirm": False,
            "actions": [],
            "state": {
                "current_flow": "governed_action_review",
                "analysis": analysis,
                "advice_only": True,
            },
            "analysis": analysis,
            "suggested_actions": [
                "Vraag: welke bevestiging is hiervoor nodig?",
                "Vraag: waarom blokkeer je deze actie?",
                "Vraag: welke context mist nog voor uitvoering?",
            ],
        }

    async def build_decision_review_response(
        self,
        user_id: int,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = context or {}
        explicit_asset = next(iter(_asset_mentions(query)), None) or context.get("symbol") or context.get("asset")
        asset = self._asset_from_query_or_context(query, context)
        subject = self._decision_review_subject(query, context)
        review_type = subject["review_type"]
        state_entity = self._read_only_state_entity(context)
        last_context = self._last_context_entity(context)
        setup_id = context.get("setup_id") or (state_entity.get("entity_id") if state_entity.get("entity_type") == "setup" else None)
        strategy_id = context.get("strategy_id") or (state_entity.get("entity_id") if state_entity.get("entity_type") == "strategy" else None)
        bot_id = context.get("bot_id") or (state_entity.get("entity_id") if state_entity.get("entity_type") == "bot" else None)
        explicit_risk_pct = self._risk_pct_from_query(query)
        explicit_setup_score = self._explicit_setup_score_from_query(query)
        explicit_portfolio_level = self._qualitative_level_from_query(query, "portfolio exposure")
        explicit_risk_level = self._qualitative_level_from_query(query, "risico") or self._qualitative_level_from_query(query, "risk")
        explicit_mix = self._explicit_portfolio_mix_from_query(query)

        portfolio_context = context.get("portfolio_intelligence") if isinstance(context.get("portfolio_intelligence"), dict) else {}
        setup_analysis: Dict[str, Any] = {"is_active": False, "confidence": "low", "reason": "Nog geen setup-data."}
        daily_scores = None
        if explicit_setup_score is not None:
            daily_scores = {"setup_score": explicit_setup_score}
            setup_analysis = {
                "is_active": explicit_setup_score >= 40,
                "confidence": "medium" if explicit_setup_score >= 40 else "low",
                "reason": f"Expliete query noemt een setup-score rond {explicit_setup_score:.0f}.",
                "has_scores": True,
            }
        if explicit_mix and not portfolio_context:
            portfolio_context = self._portfolio_context_from_explicit_mix(explicit_mix)
        if self.session and (daily_scores is None or not portfolio_context):
            score_repo = ScoreRepository(self.session)
            if daily_scores is None:
                daily_scores = await self._fetch_daily_scores_with_runtime_refresh(user_id, asset)
                active_setups = await score_repo.fetch_active_setups(user_id)
                matching_setups = [s for s in active_setups if str(s.get("symbol", "")).upper() == asset]
                best_setup = next((s for s in matching_setups if s.get("is_active")), None) or (matching_setups[0] if matching_setups else None)
                if best_setup and not setup_id:
                    setup_id = best_setup.get("id")
                setup_analysis = self._evaluate_setup_row(best_setup, daily_scores)
            if not portfolio_context:
                try:
                    from backend.infrastructure.repositories.bot_repository import BotRepository
                    portfolio_context = await BotRepository(self.session).get_portfolio_intelligence_context(user_id)
                except Exception:
                    portfolio_context = {}

        checks: List[Dict[str, Any]] = []
        context_ready = bool(explicit_asset and (setup_id or strategy_id or bot_id or review_type == "trade_intent_review"))
        context_anchor = (
            f"setup #{setup_id}" if setup_id else
            f"strategie #{strategy_id}" if strategy_id else
            f"bot #{bot_id}" if bot_id else
            "expliciete trade-context uit je prompt"
            if explicit_risk_pct is not None or explicit_setup_score is not None or explicit_mix else
            "de huidige pagina- en sessiecontext"
        )
        checks.append({
            "id": "context_ready",
            "label": "Context",
            "status": "pass" if context_ready else "needs_context",
            "severity": "high" if not context_ready else "low",
            "detail": (
                f"Ik review dit nu voor {asset} met {context_anchor}."
                if context_ready else
                "Ik mis nog te veel concrete context om deze beslissing veilig te reviewen."
            ),
        })

        has_setup_context = bool(setup_id or subject.get("entity_type") == "setup" or last_context.get("entity_type") == "setup")
        setup_status = "pass" if setup_analysis.get("is_active") or has_setup_context else "warn"
        checks.append({
            "id": "setup_validity",
            "label": "Setup-validiteit",
            "status": setup_status,
            "severity": "medium" if setup_status == "warn" else "low",
            "detail": (
                "Je setup-context is aanwezig en oogt bruikbaar voor review."
                if setup_status == "pass" else
                "Ik zie wel asset-context, maar nog geen duidelijk actieve setup om deze trade hard op te toetsen."
            ),
        })

        has_strategy_context = bool(strategy_id or subject.get("entity_type") == "strategy" or last_context.get("entity_type") == "strategy")
        strategy_status = "pass" if has_strategy_context else "warn"
        checks.append({
            "id": "strategy_fit",
            "label": "Strategie-fit",
            "status": strategy_status,
            "severity": "medium" if strategy_status == "warn" else "low",
            "detail": (
                "Ik kan deze beslissing aan een concrete strategie koppelen."
                if strategy_status == "pass" else
                "Ik zie nog geen harde strategie-koppeling; dit maakt de review minder planvast."
            ),
        })

        risk_status = "pass"
        risk_detail = "Ik zie geen direct sizing-signaal dat je risico nu uit proportie trekt."
        if explicit_risk_pct is not None and explicit_risk_pct > 5:
            risk_status = "block"
            risk_detail = f"Je noemt ongeveer {explicit_risk_pct}% risico. Dat is te groot voor een rustige planmatige entry."
        elif explicit_risk_pct is not None and explicit_risk_pct > 2:
            risk_status = "modify"
            risk_detail = f"Je noemt ongeveer {explicit_risk_pct}% risico. Dat is aan de hoge kant; ik zou dit eerst terugbrengen."
        elif explicit_risk_level == "high":
            risk_status = "modify"
            risk_detail = "Je noemt het risicobeeld zelf al hoog. Ik zou dit eerst kleiner en strakker maken voordat je verdergaat."
        elif "all-in" in self._normalized_query(query) or "all in" in self._normalized_query(query):
            risk_status = "block"
            risk_detail = "All-in taal is een harde guardrail-breuk voor een planmatige review."
        checks.append({
            "id": "risk_sizing",
            "label": "Risico en sizing",
            "status": risk_status,
            "severity": "high" if risk_status == "block" else "medium" if risk_status == "modify" else "low",
            "detail": risk_detail,
        })

        allocations = ((portfolio_context.get("global") or {}).get("allocations_pct") if isinstance(portfolio_context.get("global"), dict) else {}) or {}
        allocation_pct = allocations.get(asset)
        portfolio_status = "pass"
        portfolio_detail = "Ik zie geen directe portfolio-concentratie die deze beslissing nu blokkeert."
        if isinstance(allocation_pct, (int, float)) and allocation_pct >= 70:
            portfolio_status = "block"
            portfolio_detail = f"{asset} neemt al ongeveer {allocation_pct}% van je portfolio in. Extra exposure toevoegen is nu niet logisch."
        elif isinstance(allocation_pct, (int, float)) and allocation_pct >= 45:
            portfolio_status = "modify"
            portfolio_detail = f"{asset} zit al rond {allocation_pct}% allocatie. Ik zou alleen kleiner of selectiever toevoegen."
        elif explicit_portfolio_level == "high":
            portfolio_status = "modify"
            portfolio_detail = f"Je noemt de portfolio exposure rond {asset} zelf al als hoog. Ik zou nu eerst exposure verlagen of niet verder stapelen."
        checks.append({
            "id": "portfolio_exposure",
            "label": "Portfolio-impact",
            "status": portfolio_status,
            "severity": "high" if portfolio_status == "block" else "medium" if portfolio_status == "modify" else "low",
            "detail": portfolio_detail,
        })

        daily_status = "pass"
        daily_detail = "Ik zie geen score-signaal dat deze context direct onderuit haalt."
        if isinstance(daily_scores, dict):
            setup_score = daily_scores.get("setup_score")
            if isinstance(setup_score, (int, float)) and setup_score < 40:
                daily_status = "block"
                daily_detail = f"De actuele setup-score voor {asset} ligt rond {setup_score}. Dat is te zwak om dit nu goed te keuren."
            elif isinstance(setup_score, (int, float)) and setup_score < 60:
                daily_status = "modify"
                daily_detail = f"De actuele setup-score voor {asset} ligt rond {setup_score}. Ik zou extra bevestiging willen voordat je opschaalt."
        checks.append({
            "id": "market_readiness",
            "label": "Markt- en setupsignaal",
            "status": daily_status,
            "severity": "high" if daily_status == "block" else "medium" if daily_status == "modify" else "low",
            "detail": daily_detail,
        })

        status_rank = {"needs_context": 4, "block": 3, "warn": 2, "modify": 2, "pass": 1}
        highest = max(checks, key=lambda item: status_rank.get(str(item.get("status")), 0))
        if highest["status"] == "needs_context":
            decision_status = "insufficient_context"
        elif any(check["status"] == "block" for check in checks):
            decision_status = "block"
        elif any(check["status"] in {"modify", "warn"} for check in checks):
            decision_status = "modify"
        else:
            decision_status = "approve"

        top_blockers = [
            check["detail"]
            for check in checks
            if check["status"] in {"block", "needs_context", "warn", "modify"}
        ][:3]
        recommended_changes: List[str] = []
        if risk_status in {"block", "modify"}:
            recommended_changes.append("Breng je risico of positiegrootte terug voordat je verdergaat.")
        if portfolio_status in {"block", "modify"}:
            recommended_changes.append(f"Voeg geen extra {asset}-exposure toe zonder eerst je huidige allocatie te reviewen.")
        if strategy_status != "pass":
            recommended_changes.append("Koppel deze beslissing eerst expliciet aan je strategie of setup.")
        if not recommended_changes:
            recommended_changes.append("Houd je entry compact en voer pas uit als deze context ook over een uur nog verdedigbaar is.")

        risk_summary = {
            "approve": "Mijn review is overwegend groen: de beslissing oogt verdedigbaar binnen je huidige context.",
            "modify": "Mijn review is deels groen, maar ik zou deze beslissing eerst aanscherpen voordat je iets doet.",
            "block": "Mijn review blokkeert dit nu: de context of het risico klopt nog niet hard genoeg.",
            "insufficient_context": "Ik kan dit nog niet eerlijk goedkeuren omdat de kerncontext te dun is.",
        }[decision_status]
        operator_next_step = (
            "Voer niets uit; verzamel eerst de ontbrekende setup- of strategiecontext."
            if decision_status == "insufficient_context" else
            "Pas de sizing of exposure aan en review daarna opnieuw."
            if decision_status == "modify" else
            "Niet doen in deze vorm. Los eerst de blocker op en check daarna opnieuw."
            if decision_status == "block" else
            "Je kunt dit verder beoordelen tegen entry, invalidatie en execution timing."
        )

        portfolio_contract = self._portfolio_intelligence_contract(
            risk={
                "status": "balanced" if portfolio_status == "pass" else "watch" if portfolio_status == "modify" else "high_attention",
                "message": portfolio_detail,
                "asset_risk": [{
                    "asset": asset,
                    "risk_level": "low" if portfolio_status == "pass" else "medium" if portfolio_status == "modify" else "high",
                    "risk_score": 20 if portfolio_status == "pass" else 58 if portfolio_status == "modify" else 85,
                    "allocation_pct": allocation_pct,
                    "next_best_action": recommended_changes[0] if recommended_changes else None,
                }],
                "concentration_warnings": [{"reason": portfolio_detail}] if portfolio_status in {"modify", "block"} else [],
                "risk_stacks": [{"reason": portfolio_detail}] if portfolio_status == "block" else [],
                "ranked_conflicts": [{"reason": portfolio_detail}] if portfolio_status in {"modify", "block"} else [],
            },
            asset=asset,
        )
        analysis = {
            "review_type": review_type,
            "decision_status": decision_status,
            "context_anchor": context_anchor if context_ready else None,
            "checks": checks,
            "top_blockers": top_blockers,
            "recommended_changes": recommended_changes,
            "risk_summary": risk_summary,
            "operator_next_step": operator_next_step,
            "subject": {
                "type": subject.get("entity_type"),
                "id": subject.get("entity_id"),
                "asset": asset,
            },
            "headline": (
                f"Ik review nu je {self._decision_review_label(review_type)} voor {asset}."
                if asset else
                "Ik review nu je volgende trading-beslissing."
            ),
            **portfolio_contract,
            "snapshot": self._decision_review_snapshot(
                subject=subject,
                asset=asset,
                checks=checks,
                decision_status=decision_status,
                top_blockers=top_blockers,
                recommended_changes=recommended_changes,
            ),
        }
        await self._record_governance_event(
            user_id,
            event_type="finn_decision_review",
            symbol=asset,
            title=f"Finn reviewde een {review_type.replace('_', ' ')} voor {asset}",
            description=risk_summary,
            severity="warning" if decision_status in {"block", "modify", "insufficient_context"} else "info",
            payload={
                "phase": "decision_review_engine",
                "query": query,
                "asset": asset,
                "subject": analysis["subject"],
                "review_type": review_type,
                "decision_status": decision_status,
                "checks": checks,
                "top_blockers": top_blockers,
                "recommended_changes": recommended_changes,
                "snapshot": analysis["snapshot"],
            },
        )

        return {
            "response": self._decision_review_message(analysis),
            "intent": "decision_review",
            "flow": "decision_review",
            "draft": None,
            "missing_fields": [] if decision_status != "insufficient_context" else ["context"],
            "invalid_fields": [],
            "next_question": None if decision_status != "insufficient_context" else "context",
            "can_confirm": False,
            "actions": [],
            "state": {
                "status": "answered",
                "current_flow": "decision_review",
                "asset": asset,
                "review_snapshot": analysis["snapshot"],
                "analysis": analysis,
                "autonomy_level": "advice_only",
            },
            "analysis": analysis,
            "reasoning": {
                "confidence_score": 0.8 if decision_status == "approve" else 0.68 if decision_status == "modify" else 0.54,
                "risk_detected": decision_status in {"block", "modify"},
                "reasons": top_blockers or [risk_summary],
                "coaching_level": "decision_review",
            },
        }

    def _plan_adherence_message(self, analysis: Dict[str, Any]) -> str:
        lines = [
            analysis.get("headline") or "Hier is mijn plan-adherence check.",
            f"Status: {analysis.get('adherence_status')}.",
            analysis.get("adherence_reason") or "",
        ]
        threatened_rule = analysis.get("threatened_rule")
        if threatened_rule:
            lines.append(f"Bedreigde regel: {threatened_rule}.")
        if analysis.get("discipline_score") is not None:
            lines.append(f"Discipline-score: {analysis.get('discipline_score')}/100.")
        if analysis.get("week_delta"):
            lines.append(f"Week-op-week: {analysis.get('week_delta')}.")
        if analysis.get("suggested_recovery_step"):
            lines.append(f"Herstelstap: {analysis.get('suggested_recovery_step')}")
        return "\n".join([line for line in lines if line])

    def _plan_adherence_override_signal(self, query: str) -> Optional[Dict[str, Any]]:
        q = self._normalized_query(query)
        if "mijn plan zegt wachten" in q and any(term in q for term in ["ik wil kopen", "ik wil instappen", "ik wil toch kopen", "ik wil toch instappen"]):
            return {
                "threatened_rule": "Je plan zegt wachten, maar je probeert nu toch een entry te forceren.",
                "adherence_status": "forced_override",
                "suggested_recovery_step": "Doe nu niets nieuws. Herbevestig eerst je trigger, richting en waarom wachten niet meer geldt.",
            }
        if any(term in q for term in ["stop-loss verwijderen", "stop loss verwijderen"]):
            return {
                "threatened_rule": "Je verwijdert je vooraf afgesproken exit-grens en maakt het verlieskader open.",
                "adherence_status": "forced_override",
                "suggested_recovery_step": "Laat de stop-loss staan of herdefinieer eerst je ongeldigingspunt voordat je ook maar iets uitvoert.",
            }
        if any(term in q for term in ["grotere positie openen", "positie vergroten", "meer risico nemen", "groter gaan"]):
            return {
                "threatened_rule": "Je wilt sizing of risico verhogen zonder eerst opnieuw te valideren of dat binnen je plan valt.",
                "adherence_status": "insufficiently_justified",
                "suggested_recovery_step": "Check eerst je maximale risico per idee en bewijs waarom grotere sizing nu planmatig klopt.",
            }
        if any(term in q for term in PLAN_ADHERENCE_HARD_OVERRIDE_TERMS):
            return {
                "threatened_rule": "Je taal wijst op het overrulen van een bestaande plan- of risicogrens.",
                "adherence_status": "forced_override",
                "suggested_recovery_step": "Leg eerst vast welke regel je wilt breken en waarom die regel nu niet meer geldig zou zijn.",
            }
        return None

    def _explicit_outcome_scenario_from_query(self, query: str) -> Optional[Dict[str, Any]]:
        q = self._normalized_query(query)
        trade_match = re.search(r"\b(\d+)\s+(?:fomo\s+)?trades?\b", q)
        win_match = re.search(r"\b(\d+)\s+winst(?:trades?)?\b", q)
        loss_match = re.search(r"\b(\d+)\s+verlies(?:trades?)?\b", q)
        avg_match = re.search(r"gemiddeld(?:\s+resultaat)?\s*[:=]?\s*(-?\d+(?:[.,]\d+)?)\s*%", q)
        if not any([trade_match, win_match, loss_match, avg_match]):
            return None
        sample_size = int(trade_match.group(1)) if trade_match else 0
        wins = int(win_match.group(1)) if win_match else None
        losses = int(loss_match.group(1)) if loss_match else None
        avg_pct = None
        if avg_match:
            try:
                avg_pct = float(avg_match.group(1).replace(",", "."))
            except ValueError:
                avg_pct = None
        if sample_size == 0 and wins is not None and losses is not None:
            sample_size = wins + losses
        if sample_size == 0 and avg_pct is None:
            return None
        if "fomo" in q:
            behavior_pattern = "fomo_outcomes"
        elif any(term in q for term in ["override", "planafwijk", "afwijk"]):
            behavior_pattern = "plan_override_outcomes"
        elif any(term in q for term in OVERTRADING_DIRECT_COACH_TERMS):
            behavior_pattern = "overtrading_outcomes"
        else:
            behavior_pattern = "decision_outcomes"
        return {
            "sample_size": sample_size,
            "wins": wins,
            "losses": losses,
            "average_pct": avg_pct,
            "behavior_pattern": behavior_pattern,
        }

    def _explicit_portfolio_mix_from_query(self, query: str) -> Optional[Dict[str, Any]]:
        raw_query = (query or "").upper()
        pattern = re.compile(
            r"(?:(BTC|ETH|SOL|DOGE|XRP|ADA|BNB|AVAX|LINK|MATIC|PEPE|CASH)\s*(\d+(?:[.,]\d+)?)\s*%"
            r"|(\d+(?:[.,]\d+)?)\s*%\s*(BTC|ETH|SOL|DOGE|XRP|ADA|BNB|AVAX|LINK|MATIC|PEPE|CASH))"
        )
        matches = list(pattern.finditer(raw_query))
        if not matches:
            return None
        allocations: Dict[str, float] = {}
        ordered_assets: List[str] = []
        for match in matches:
            asset_raw = match.group(1) or match.group(4)
            pct_raw = match.group(2) or match.group(3)
            if not asset_raw or not pct_raw:
                continue
            try:
                allocations[str(asset_raw).upper()] = float(str(pct_raw).replace(",", "."))
                ordered_assets.append(str(asset_raw).upper())
            except ValueError:
                continue
        if not allocations:
            return None
        dominant_asset = max(allocations.items(), key=lambda item: item[1])[0]
        requested_asset = None
        if any(term in self._normalized_query(query) for term in ["long", "short", "openen", "toevoegen", "extra", "risico"]):
            positional_mentions = list(re.finditer(r"\b(BTC|ETH|SOL|DOGE|XRP|ADA|BNB|AVAX|LINK|MATIC|PEPE|CASH)\b", raw_query))
            if positional_mentions:
                requested_asset = str(positional_mentions[-1].group(1)).upper()
        return {
            "allocations": allocations,
            "dominant_asset": dominant_asset,
            "dominant_pct": allocations[dominant_asset],
            "requested_asset": requested_asset,
            "ordered_assets": ordered_assets,
        }

    async def build_plan_adherence_review_response(
        self,
        user_id: int,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = context or {}
        decision_review = await self.build_decision_review_response(user_id, query, context)
        review_analysis = decision_review.get("analysis") if isinstance(decision_review.get("analysis"), dict) else {}
        q = self._normalized_query(query)
        override_detected = any(term in q for term in [
            "ik wijk af", "buiten mijn plan", "buiten mijn strategie", "ik wil toch", "regels loslaten", "override",
        ])

        activity_feed = await self._get_recent_finn_activity(user_id, limit=180)
        day_log = self._mission_day_log(activity_feed)
        behavioral = self._build_behavioral_insight_from_activity(activity_feed, day_log)
        reflection = self._build_weekly_reflection_from_behavioral(behavioral, activity_feed)
        review_status = review_analysis.get("decision_status")
        explicit_override = self._plan_adherence_override_signal(query)

        threatened_rule = None
        if explicit_override:
            threatened_rule = explicit_override.get("threatened_rule")
        elif override_detected:
            threatened_rule = "Je probeert een plan- of strategiegrens te overrulen."
        elif review_analysis.get("checks"):
            first_flagged = next(
                (check for check in review_analysis["checks"] if check.get("status") in {"block", "modify", "warn"}),
                None,
            )
            threatened_rule = first_flagged.get("label") if isinstance(first_flagged, dict) else None

        adherence_status = "in_plan"
        if explicit_override:
            adherence_status = str(explicit_override.get("adherence_status") or "forced_override")
            override_detected = True
        elif override_detected:
            adherence_status = "forced_override"
        elif review_status == "block":
            adherence_status = "outside_plan"
        elif review_status in {"modify", "insufficient_context"}:
            adherence_status = "insufficiently_justified"

        adherence_reason = {
            "in_plan": "Op basis van je huidige context oogt deze beslissing nog planmatig verdedigbaar.",
            "outside_plan": "Deze beslissing botst nu met je plan, risico of portfolio-kaders.",
            "forced_override": "Je taal en context wijzen op een bewuste override van je bestaande planregels.",
            "insufficiently_justified": "Ik zie nog niet genoeg bevestiging om te zeggen dat dit echt binnen je plan valt.",
        }[adherence_status]
        if explicit_override and explicit_override.get("adherence_status") == "forced_override":
            adherence_reason = "Dit is geen kleine nuance maar een directe override van een expliciete plan- of risicoregel."
        elif explicit_override and explicit_override.get("adherence_status") == "insufficiently_justified":
            adherence_reason = "Je wilt nu wel versnellen, maar zonder genoeg onderbouwing dat grotere sizing of extra risico nog binnen je plan valt."

        week_over_week = reflection.get("week_over_week") or {}
        analysis = {
            "adherence_status": adherence_status,
            "adherence_reason": adherence_reason,
            "threatened_rule": threatened_rule,
            "override_detected": override_detected,
            "discipline_score": reflection.get("discipline_score"),
            "week_delta": week_over_week.get("summary"),
            "suggested_recovery_step": (
                explicit_override.get("suggested_recovery_step")
                if explicit_override else
                "Leg je plan naast deze beslissing en herbevestig eerst trigger, sizing en exposure."
                if adherence_status != "in_plan" else
                "Houd dit klein en voer alleen uit als dezelfde argumenten over een uur nog steeds kloppen."
            ),
            "review_reference": review_analysis.get("snapshot"),
            "headline": "Ik check nu of deze beslissing nog binnen je plan valt.",
        }
        await self._record_governance_event(
            user_id,
            event_type="finn_plan_adherence_review",
            symbol=(decision_review.get("state") or {}).get("asset"),
            title="Finn checkte plan-adherence op je huidige beslissing",
            description=adherence_reason,
            severity="warning" if adherence_status in {"outside_plan", "forced_override", "insufficiently_justified"} else "info",
            payload={
                "phase": "plan_adherence_engine",
                "query": query,
                "asset": (decision_review.get("state") or {}).get("asset"),
                "subject": (review_analysis.get("subject") or {}),
                "adherence_status": adherence_status,
                "threatened_rule": threatened_rule,
                "override_detected": override_detected,
                "discipline_score": reflection.get("discipline_score"),
                "week_delta": week_over_week.get("summary"),
                "review_reference": review_analysis.get("snapshot"),
            },
        )
        return {
            "response": self._plan_adherence_message(analysis),
            "intent": "plan_adherence_review",
            "flow": "plan_adherence_review",
            "draft": None,
            "missing_fields": [],
            "invalid_fields": [],
            "next_question": None,
            "can_confirm": False,
            "actions": [],
            "state": {
                "status": "answered",
                "current_flow": "plan_adherence_review",
                "asset": (decision_review.get("state") or {}).get("asset"),
                "analysis": analysis,
                "autonomy_level": "advice_only",
            },
            "analysis": analysis,
            "reasoning": {
                "confidence_score": 0.82 if adherence_status == "in_plan" else 0.72 if adherence_status == "insufficiently_justified" else 0.78,
                "risk_detected": adherence_status != "in_plan",
                "reasons": [adherence_reason],
                "coaching_level": "plan_adherence_review",
            },
        }

    async def build_outcome_tracking_response(
        self,
        user_id: int,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = context or {}
        q = self._normalized_query(query)
        if any(term in q for term in ["plan", "afwijk", "override", "regels"]):
            event_types = ["finn_plan_adherence_review"]
            behavior_pattern = "plan_adherence_outcomes"
        else:
            event_types = ["finn_decision_review", "finn_plan_adherence_review"]
            behavior_pattern = "decision_follow_through_outcomes"

        governance_events = await self._fetch_recent_governance_events(user_id, event_types=event_types, limit=60)
        activity_feed = await self._get_recent_finn_activity(user_id, limit=200)
        linked = [
            {
                "event": event,
                "follow_through": self._governance_event_follow_through(event, activity_feed),
            }
            for event in governance_events
        ]
        matched = []
        for item in linked:
            payload = item["event"].get("payload") if isinstance(item["event"].get("payload"), dict) else {}
            if behavior_pattern == "plan_adherence_outcomes":
                if payload.get("adherence_status") in {"outside_plan", "forced_override", "insufficiently_justified"}:
                    matched.append(item)
            else:
                matched.append(item)

        sample_size = len(matched)
        executed = sum(item["follow_through"]["counters"]["executed"] for item in matched)
        blocked = sum(item["follow_through"]["counters"]["blocked"] for item in matched)
        skipped = sum(item["follow_through"]["counters"]["skipped"] for item in matched)
        reviewed_only = sum(item["follow_through"]["counters"]["reviewed"] for item in matched)
        explicit_scenario = self._explicit_outcome_scenario_from_query(query)

        if explicit_scenario:
            sample_size = int(explicit_scenario.get("sample_size") or sample_size)
            wins = explicit_scenario.get("wins")
            losses = explicit_scenario.get("losses")
            avg_pct = explicit_scenario.get("average_pct")
            behavior_pattern = explicit_scenario.get("behavior_pattern") or behavior_pattern
            historical_parts = [f"Je beschrijft hier {sample_size} relevante momenten"]
            if wins is not None or losses is not None:
                historical_parts.append(
                    f"met {losses or 0} verliestrades en {wins or 0} winsttrades"
                )
            if avg_pct is not None:
                historical_parts.append(f"en een gemiddeld resultaat van {avg_pct:.1f}%")
            historical_result_summary = " ".join(historical_parts) + "."
            if avg_pct is not None and avg_pct < 0:
                net_effect = "Het netto-effect van dit gedrag is negatief. Dat betekent dat herhaling eerder kapitaal lekt dan helpt."
            elif losses is not None and wins is not None and losses > wins:
                net_effect = "Dit patroon eindigt vaker slecht dan goed. Dat is een operator-waarschuwing, niet alleen een gedragsobservatie."
            elif wins is not None and losses is not None and wins > losses:
                net_effect = "Dit patroon eindigt niet automatisch slecht, maar je moet nog steeds toetsen of de winst uit planmatige uitvoering kwam en niet uit toeval."
            else:
                net_effect = "Het scenario is gemengd, maar sterk genoeg om het als echt besluitpatroon te reviewen in plaats van als losse emotie."
            confidence_note = (
                "Confidence medium: dit gebruikt het expliciete scenario dat jij geeft, aangevuld met Finn follow-through waar aanwezig."
            )
            operator_next_step = "Gebruik deze uitkomstlijn als rem: als hetzelfde patroon vaker slecht eindigt, moet je de trigger eerder blokkeren dan de trade achteraf verklaren."
        elif sample_size == 0:
            historical_result_summary = "Ik heb nog te weinig gekoppelde review/adherence-events om hier een harde uitkomstlijn van te maken."
            net_effect = "Nog geen netto patroon: ik wacht liever op meer echte review- en follow-through data."
            confidence_note = "Confidence laag: zonder genoeg gekoppelde events doe ik hier geen causale uitspraken."
            operator_next_step = "Blijf review, adherence-checks en uitvoering via Finn laten lopen; dan wordt deze laag snel rijker."
        else:
            historical_result_summary = (
                f"In {sample_size} relevante momenten zag ik {executed} execution-follow-through, "
                f"{skipped} bewuste skips, {blocked} blocks en {reviewed_only} review-only vervolgacties."
            )
            if blocked + skipped > executed:
                net_effect = "Het patroon eindigt vaker in remmen of niet-doen dan in overtuigende uitvoering. Dat wijst op frictie die je plan vermoedelijk juist beschermt."
            elif executed > blocked + skipped:
                net_effect = "Dit patroon eindigt vaker in echte follow-through. Dat kan gezond zijn, maar ik wil dan vooral zien of die uitvoering ook planmatig en klein bleef."
            else:
                net_effect = "Het netto-effect is gemengd: ik zie zowel doorzetten als remmen, zonder duidelijke dominante uitkomst."
            confidence_note = (
                "Confidence medium: dit is gekoppelde follow-through uit audit-events. "
                "Ik trek pas PnL-conclusies zodra resultaten expliciet aan deze beslissingen hangen."
            )
            operator_next_step = (
                "Gebruik dit als governance-signaal: als een patroon vaak eindigt in blocks of skips, probeer het eerder in je beslisproces al af te remmen."
            )

        analysis = {
            "outcome_window": "last_90_days",
            "sample_size": sample_size,
            "behavior_pattern": behavior_pattern,
            "historical_result_summary": historical_result_summary,
            "net_effect": net_effect,
            "confidence_note": confidence_note,
            "operator_next_step": operator_next_step,
            "headline": "Ik koppel nu review- en adherence-momenten aan wat er daarna echt gebeurde.",
            "linked_outcomes": [
                {
                    "created_at": item["event"].get("created_at"),
                    "type": item["event"].get("type"),
                    "asset": item["event"].get("symbol"),
                    "resolution": item["follow_through"]["resolution"],
                    "counters": item["follow_through"]["counters"],
                }
                for item in matched[:8]
            ],
        }
        await self._record_governance_event(
            user_id,
            event_type="finn_outcome_tracking_summary",
            symbol=context.get("symbol") or context.get("asset"),
            title="Finn bouwde een outcome-tracking samenvatting",
            description=net_effect,
            severity="info",
            payload={
                "phase": "outcome_linking_engine",
                "query": query,
                "behavior_pattern": behavior_pattern,
                "sample_size": sample_size,
                "historical_result_summary": historical_result_summary,
                "net_effect": net_effect,
                "confidence_note": confidence_note,
            },
            cooldown_hours=3,
        )
        return {
            "response": self._outcome_tracking_message(analysis),
            "intent": "outcome_tracking",
            "flow": "outcome_tracking",
            "draft": None,
            "missing_fields": [],
            "invalid_fields": [],
            "next_question": None,
            "can_confirm": False,
            "actions": [],
            "state": {
                "status": "answered",
                "current_flow": "outcome_tracking",
                "analysis": analysis,
                "autonomy_level": "advice_only",
            },
            "analysis": analysis,
            "reasoning": {
                "confidence_score": 0.74 if sample_size >= 3 else 0.48,
                "risk_detected": blocked + skipped > executed,
                "reasons": [net_effect],
                "coaching_level": "outcome_tracking",
            },
        }

    async def build_portfolio_intelligence_response(
        self,
        user_id: int,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = context or {}
        asset = self._asset_from_query_or_context(query, context)
        explicit_mix = self._explicit_portfolio_mix_from_query(query)
        if explicit_mix:
            risk = self._portfolio_context_from_explicit_mix(explicit_mix)
            contract = self._portfolio_intelligence_contract(risk=risk, asset=asset)
        else:
            daily = await self.build_portfolio_daily_coach_response(user_id, query, context)
            daily_analysis = (daily.get("state") or {}).get("analysis") if isinstance((daily.get("state") or {}).get("analysis"), dict) else {}
            risk = daily_analysis.get("portfolio_risk") or {}
            contract = self._portfolio_intelligence_contract(risk=risk, asset=asset)
        if explicit_mix:
            dominant_asset = explicit_mix.get("dominant_asset")
            dominant_pct = explicit_mix.get("dominant_pct")
            allocations = explicit_mix.get("allocations") or {}
            requested_asset = str(explicit_mix.get("requested_asset") or "").upper() or None
            ask_asset = requested_asset or str((context or {}).get("symbol") or asset or dominant_asset or "").upper() or None
            focus_asset = ask_asset or dominant_asset
            focus_pct = allocations.get(focus_asset) if focus_asset else None
            if focus_pct is None:
                focus_asset = dominant_asset
                focus_pct = dominant_pct
            add_more_same_asset = bool(ask_asset and focus_asset and str(ask_asset).upper() == str(focus_asset).upper())
            contract["portfolio_impact"] = {
                "status": "concentrated" if (focus_pct or 0) >= 60 else "watch",
                "message": (
                    f"Je portfolio is nu al zwaar geconcentreerd in {focus_asset}."
                    if (focus_pct or 0) >= 60 else
                    f"Je portfolio-mix rond {focus_asset} vraagt eerst een exposure-check voordat je nieuw risico toevoegt."
                ),
                "focus_asset": focus_asset,
                "focus_risk_level": "high" if (focus_pct or 0) >= 60 else "medium",
                "focus_risk_score": focus_pct,
            }
            contract["exposure_delta"] = ", ".join(
                f"{asset_name} {pct:.0f}%"
                for asset_name, pct in allocations.items()
            )
            if add_more_same_asset and (focus_pct or 0) >= 60:
                contract["concentration_warning"] = (
                    f"{focus_asset} zit al rond {focus_pct:.0f}% allocatie. Extra {focus_asset}-risico stapelt concentratie in plaats van spreiding."
                )
                contract["portfolio_blockers"] = [
                    *([contract["concentration_warning"]] if contract.get("concentration_warning") else []),
                    *list(contract.get("portfolio_blockers") or []),
                ][:3]
                contract["portfolio_safe_alternative"] = (
                    "Voeg nu geen extra risico toe in dezelfde asset; verlaag eerst concentratie of kies een niet-gestapelde exposure."
                )
            contract["stacked_risk_warning"] = (
                f"{focus_asset} domineert deze scenario-mix en verdient nu de strengste portfolio-check."
                if (focus_pct or 0) >= 60 else contract.get("stacked_risk_warning")
            )
            asset = focus_asset or asset
        analysis = {
            **contract,
            "headline": (
                f"Ik beoordeel nu je portfolio-impact rond {asset}."
                if asset else
                "Ik beoordeel nu je portfolio-impact over je actieve assets."
            ),
            "portfolio_status": (contract.get("portfolio_impact") or {}).get("status") or risk.get("status"),
            "why_now": (contract.get("portfolio_impact") or {}).get("message") or risk.get("message"),
            "review_queue": (risk.get("asset_priority") or [])[:3],
        }
        await self._record_governance_event(
            user_id,
            event_type="finn_portfolio_intelligence",
            symbol=asset,
            title="Finn maakte een portfolio-intelligence review",
            description=(analysis.get("portfolio_impact") or {}).get("message") or "Portfolio review uitgevoerd.",
            severity="warning" if analysis.get("portfolio_status") in {"high_attention", "concentrated"} else "info",
            payload={
                "phase": "portfolio_intelligence_summary",
                "query": query,
                "asset": asset,
                "portfolio_status": analysis.get("portfolio_status"),
                "portfolio_impact": analysis.get("portfolio_impact"),
                "portfolio_blockers": analysis.get("portfolio_blockers"),
                "concentration_warning": analysis.get("concentration_warning"),
                "stacked_risk_warning": analysis.get("stacked_risk_warning"),
            },
            cooldown_hours=3,
        )
        return {
            "response": self._portfolio_intelligence_message(analysis),
            "intent": "portfolio_intelligence",
            "flow": "portfolio_intelligence",
            "draft": None,
            "missing_fields": [],
            "invalid_fields": [],
            "next_question": None,
            "can_confirm": False,
            "actions": [],
            "state": {
                "status": "answered",
                "current_flow": "portfolio_intelligence",
                "asset": asset,
                "analysis": analysis,
                "autonomy_level": "advice_only",
            },
            "analysis": analysis,
            "reasoning": {
                "confidence_score": 0.88 if explicit_mix else 0.79 if risk else 0.52,
                "risk_detected": analysis.get("portfolio_status") not in {None, "balanced"},
                "reasons": [(contract.get("portfolio_impact") or {}).get("message") or risk.get("message") or "Portfolio-impact beoordeeld."],
                "coaching_level": "portfolio_intelligence",
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
        analysis["execution_review"] = self._build_indicator_execution_review(asset, analysis)

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
                if best_setup and not active_strategy.get("active"):
                    setup_strategy = await StrategyService(self.session).repository.get_strategy_by_setup(
                        int(best_setup.get("id")),
                        user_id,
                    )
                    if setup_strategy:
                        active_strategy = {
                            "active": False,
                            "strategy_exists": True,
                            "strategy": StrategyService(self.session)._format_strategy_row(setup_strategy),
                        }
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
        setup_context_by_asset: Dict[str, Dict[str, Any]] = {}
        mission_control_fast = bool(
            context.get("scope") == "mission_control"
            or context.get("mission_control_fast")
        )
        mission_control_preview_only = bool(context.get("mission_control_preview_only"))

        if self.session:
            score_repo = ScoreRepository(self.session)
            active_setups = await score_repo.fetch_active_setups(user_id)
            onboarding_status = await self._fetch_onboarding_status(user_id)
            best_setups_by_asset: Dict[str, Dict[str, Any]] = {}
            setups_by_asset: Dict[str, List[Dict[str, Any]]] = {}
            for setup in active_setups:
                symbol = str(setup.get("symbol") or "").upper()
                if symbol not in SUPPORTED_ASSETS:
                    continue
                setups_by_asset.setdefault(symbol, []).append(setup)
                current = best_setups_by_asset.get(symbol)
                if not current or (setup.get("is_active") and not current.get("is_active")):
                    best_setups_by_asset[symbol] = setup
            setup_context_by_asset = self._portfolio_setup_context(setups_by_asset)

            for asset in sorted(best_setups_by_asset.keys()):
                setup = best_setups_by_asset[asset]
                daily_scores = await self._fetch_daily_scores_with_runtime_refresh(
                    user_id,
                    asset,
                    allow_refresh=not mission_control_fast,
                )
                setup_analysis = self._evaluate_setup_row(setup, daily_scores)
                active_strategy = {"active": False, "portfolio_scope": True}
                if mission_control_preview_only:
                    active_strategy["preview_only"] = True
                    bot_today = {
                        "decisions": [],
                        "scores": {},
                        "orders": [],
                        "executions": [],
                        "preview_only": True,
                    }
                    indicator_analysis = {
                        "asset": asset,
                        "has_daily_scores": bool(daily_scores),
                        "categories": {},
                        "warnings": [],
                        "suggestions": [],
                        "suggested_actions": [],
                        "preview_only": True,
                    }
                else:
                    try:
                        setup_strategy = await StrategyService(self.session).repository.get_strategy_by_setup(
                            int(setup.get("id")),
                            user_id,
                        )
                        if setup_strategy:
                            active_strategy = {
                                "active": False,
                                "portfolio_scope": True,
                                "strategy_exists": True,
                                "strategy": StrategyService(self.session)._format_strategy_row(setup_strategy),
                            }
                    except Exception as exc:
                        active_strategy = {"active": False, "portfolio_scope": True, "error": str(exc)}
                    try:
                        bot_today = await BotService(self.session).get_bot_today(
                            user_id,
                            symbol=asset,
                            lean=mission_control_fast,
                        )
                    except Exception as exc:
                        bot_today = {"decisions": [], "scores": {}, "orders": [], "executions": [], "error": str(exc)}
                    if mission_control_fast:
                        indicator_analysis = await self._build_indicator_analysis_fast(user_id, asset, daily_scores)
                    else:
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
                    active_strategy=active_strategy,
                    bot_today=bot_today,
                    indicator_analysis=indicator_analysis,
                    onboarding_status=onboarding_status,
                ))

        portfolio_context: Dict[str, Any] = {}
        if self.session:
            try:
                from backend.infrastructure.repositories.bot_repository import BotRepository
                portfolio_context = await BotRepository(self.session).get_portfolio_intelligence_context(user_id)
            except Exception:
                portfolio_context = {}

        analysis = self._build_portfolio_daily_coach_analysis(asset_analyses, portfolio_context, setup_context_by_asset)
        analysis["question_focus"] = self._portfolio_question_focus(query)
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

    async def build_daily_score_refresh_response(
        self,
        user_id: int,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = context or {}
        explicit_assets = [asset for asset in _asset_mentions(query) if asset in SUPPORTED_ASSETS]
        if explicit_assets:
            assets = explicit_assets
            scope = "asset"
        else:
            assets = await self._portfolio_setup_assets(user_id)
            scope = "portfolio" if len(assets) > 1 else "asset"
        assets = sorted(set(assets or ["BTC"]))
        action = {
            "id": self._maintenance_action_id("refresh_daily_scores", assets),
            "type": "refresh_daily_scores",
            "label": "Daily scores verversen",
            "payload": {"assets": assets, "scope": scope},
            "risk_level": "low",
            "requires_confirmation": True,
            "autonomy_level": "confirm_required",
            "guardrails": {
                "requires_confirmation": True,
                "can_execute_without_user": False,
                "execution_allowed": "score_refresh_only",
            },
        }
        asset_text = ", ".join(assets)
        return {
            "response": (
                f"Ik kan de daily scores verversen voor {asset_text}. "
                "Dit haalt/geneert scoredata opnieuw op, maar voert geen trade uit en wijzigt geen setup, strategie of bot."
            ),
            "intent": "daily_score_refresh",
            "flow": "maintenance_action",
            "draft": None,
            "missing_fields": [],
            "invalid_fields": [],
            "next_question": None,
            "can_confirm": True,
            "actions": [action],
            "state": {
                "status": "ready_for_confirmation",
                "current_flow": "maintenance_action",
                "maintenance_type": "refresh_daily_scores",
                "assets": assets,
                "autonomy_level": "confirm_required",
                "analysis": {
                    "mode": "read_only",
                    "tool_intent_reason": "explicit_refresh_request",
                },
            },
            "analysis": {
                "mode": "read_only",
                "tool_intent_reason": "explicit_refresh_request",
            },
            "reasoning": {
                "confidence_score": 0.86,
                "risk_detected": False,
                "reasons": ["Daily score refresh is een read/compute maintenance action; geen trading execution."],
                "coaching_level": "maintenance_handoff",
            },
            "suggested_actions": [f"Bevestig daily score refresh voor {asset_text}"],
        }

    async def build_bot_decision_response(
        self,
        user_id: int,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = context or {}
        asset = self._asset_from_query_or_context(query, context)
        bots = []
        if self.session:
            bots = [
                bot for bot in await BotService(self.session).get_bot_configs(user_id)
                if str(bot.get("symbol") or "").upper() == asset
            ]
        bot_id = self._extract_id_after_words(query, ["bot"]) or self._safe_int(context.get("bot_id"))
        selected = next((bot for bot in bots if int(bot.get("id")) == bot_id), None) if bot_id else None
        if not selected and len(bots) == 1:
            selected = bots[0]

        if context.get("current_flow") == "bot_decision" and context.get("pending_behavioral_memory_friction"):
            pending_friction = context.get("pending_behavioral_memory_friction")
            if self._is_behavioral_memory_ack((query or "").lower()):
                context["behavioral_memory_ack"] = True
            elif selected:
                return self._blocked_behavioral_memory_ack_response(asset, int(selected["id"]), pending_friction)

        if not selected:
            if not bots:
                response = f"Ik vind nog geen bot voor {asset}. Maak eerst een bot of kies een bestaande strategie om een bot aan te maken."
                next_question = "bot_id"
            else:
                options = ", ".join(f"#{bot.get('id')} {bot.get('name')}" for bot in bots[:5])
                response = f"Welke bot moet ik gebruiken voor de decision? Beschikbaar voor {asset}: {options}."
                next_question = "bot_id"
            return {
                "response": response,
                "intent": "bot_decision",
                "flow": "bot_decision",
                "draft": None,
                "missing_fields": ["bot_id"],
                "invalid_fields": [],
                "next_question": next_question,
                "can_confirm": False,
                "actions": [],
                "state": {
                    "status": "needs_input",
                    "current_flow": "bot_decision",
                    "asset": asset,
                    "bot_options": bots[:5],
                    "autonomy_level": "confirm_required",
                },
                "reasoning": {
                    "confidence_score": 0.68,
                    "risk_detected": False,
                    "reasons": ["Finn heeft een specifieke bot nodig voordat hij een decision kan genereren."],
                    "coaching_level": "bot_decision_handoff",
                },
                "suggested_actions": ["Noem het bot_id, bijvoorbeeld: Maak bot-decision voor bot #12"],
            }

        action = {
            "id": self._maintenance_action_id(
                "generate_bot_decision",
                self._generate_bot_decision_action_parts(selected, []),
            ),
            "type": "generate_bot_decision",
            "label": "Bot-decision genereren",
            "payload": {"bot_id": int(selected["id"]), "asset": asset},
            "risk_level": "medium",
            "requires_confirmation": True,
            "autonomy_level": "confirm_required",
            "guardrails": {
                "requires_confirmation": True,
                "can_execute_without_user": False,
                "execution_allowed": "generate_decision_only",
                "no_order_execution": True,
            },
        }
        open_reviews = await self._open_bot_reviews_for_bot(user_id, asset, int(selected["id"]))
        memory_friction = await self._behavioral_memory_friction_for_action(user_id, "generate_bot_decision")
        memory_acknowledged = bool(context.get("behavioral_memory_ack")) or self._is_behavioral_memory_ack((query or "").lower())
        if memory_friction and not memory_acknowledged:
            return self._blocked_behavioral_memory_ack_response(asset, int(selected["id"]), memory_friction)
        if open_reviews:
            open_decision_ids = [int(item["decision_id"]) for item in open_reviews if item.get("decision_id")]
            action["id"] = self._maintenance_action_id(
                "generate_bot_decision",
                self._generate_bot_decision_action_parts(selected, open_decision_ids),
            )
            action["risk_level"] = "high"
            action["payload"]["behavioral_context"] = {
                "decision_churn": {
                    "existing_decision_ids": open_decision_ids,
                    "existing_open_count": len(open_decision_ids),
                }
            }
            action["guardrails"]["open_decision_review_exists"] = True
        if memory_friction:
            memory_friction = {**memory_friction, "acknowledged": memory_acknowledged}
            action["guardrails"]["behavioral_memory_friction"] = True
            action["guardrails"]["behavioral_memory_acknowledged"] = memory_acknowledged
            action["payload"]["memory_friction"] = memory_friction
            if action.get("risk_level") != "high":
                action["risk_level"] = "medium"

        response_prefix = ""
        if open_reviews:
            response_prefix = (
                f"Er staat al {len(open_reviews)} open bot-decision(s) voor {selected.get('name')}. "
                "Als je nu opnieuw een decision maakt, leg ik dat vast als decision churn. "
            )
        elif memory_friction:
            response_prefix = (
                f"Memory check: {memory_friction.get('message')} "
                "Je hebt dit bewust bevestigd; ik maak alleen een nieuw voorstel. "
            )
        return {
            "response": response_prefix + (
                "" if response_prefix else f"Ik kan een bot-decision genereren voor {selected.get('name')} (bot #{selected.get('id')}). "
            ) + (
                "Dit maakt alleen een voorstel/decision; orders uitvoeren blijft apart bevestigd."
            ),
            "intent": "bot_decision",
            "flow": "bot_decision",
            "draft": None,
            "missing_fields": [],
            "invalid_fields": [],
            "next_question": None,
            "can_confirm": True,
            "actions": [action],
            "state": {
                "status": "ready_for_confirmation",
                "current_flow": "bot_decision",
                "asset": asset,
                "bot_id": int(selected["id"]),
                "open_decision_count": len(open_reviews),
                "open_decision_ids": [item.get("decision_id") for item in open_reviews],
                "memory_friction": memory_friction,
                "autonomy_level": "confirm_required",
            },
            "reasoning": {
                "confidence_score": 0.82,
                "risk_detected": bool(open_reviews or memory_friction),
                "reasons": (
                    ["Er staat al een open bot-decision; opnieuw genereren wordt als decision churn gelogd."]
                    if open_reviews else
                    [memory_friction.get("message")]
                    if memory_friction else
                    ["Bot decision generation creates a proposal only; no order execution."]
                ),
                "coaching_level": "bot_decision_handoff",
            },
            "suggested_actions": [f"Bevestig bot-decision voor bot #{selected.get('id')}"],
        }

    async def build_bot_decision_review_response(
        self,
        user_id: int,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = context or {}
        decision_id = self._extract_id_after_words(query, ["bot-decision", "decision", "beslissing", "proposal", "voorstel"])
        asset = self._asset_from_query_or_context(query, context)
        bot_today = await BotService(self.session).get_bot_today(user_id, symbol=asset) if self.session else {"decisions": []}
        decisions = bot_today.get("decisions") or []

        selected = None
        if decision_id:
            selected = next((decision for decision in decisions if int(decision.get("id") or 0) == decision_id), None)
        elif len(decisions) == 1:
            selected = decisions[0]

        if not selected:
            queue = [self._mission_bot_review_item(decision, {"asset": decision.get("symbol") or asset, "setup": {"id": decision.get("setup_id")}}) for decision in decisions[:5]]
            options = ", ".join(f"#{item.get('decision_id')} {item.get('action')} ({item.get('review_status')})" for item in queue)
            return {
                "response": (
                    f"Welke bot-decision wil je reviewen? Open voor {asset}: {options}."
                    if queue else f"Ik vind geen open bot-decisions voor {asset} om te reviewen."
                ),
                "intent": "bot_decision_review",
                "flow": "bot_decision_review",
                "draft": None,
                "missing_fields": ["decision_id"] if queue else [],
                "invalid_fields": [],
                "next_question": "decision_id" if queue else None,
                "can_confirm": False,
                "actions": [],
                "state": {
                    "status": "needs_input" if queue else "empty",
                    "current_flow": "bot_decision_review",
                    "asset": asset,
                    "bot_review_queue": queue,
                    "autonomy_level": "advice_only",
                },
                "reasoning": {
                    "confidence_score": 0.72,
                    "risk_detected": False,
                    "reasons": ["Finn reviewt bot-decisions read-only; order execution blijft buiten deze flow."],
                    "coaching_level": "bot_decision_review",
                },
                "suggested_actions": ["Noem het decision_id dat je wilt reviewen."] if queue else ["Maak eerst een bot-decision voor dit asset."],
            }

        review = self._mission_bot_review_item(selected, {"asset": selected.get("symbol") or asset, "setup": {"id": selected.get("setup_id")}})
        confidence_label = (
            f"{round(review['confidence'] * 100)}%"
            if isinstance(review.get("confidence"), (int, float))
            else "onbekend"
        )
        lines = [
            f"Bot-decision #{review['decision_id']} voor {review.get('asset')}: {review.get('action')} ({review.get('review_status')}).",
            f"Risico: {review.get('risk_level')}. Confidence: {confidence_label}.",
        ]
        if review.get("action") == "hold":
            lines.append("Uitvoering: hold-decision; geen orderbedrag, alleen monitoren.")
        elif review.get("amount_eur") is not None:
            lines.append(f"Bedrag: EUR {review.get('amount_eur')}.")
        if review.get("guardrail_reason"):
            lines.append(f"Guardrail: {review.get('guardrail_reason')}.")
        if review.get("setup_match"):
            match = review["setup_match"]
            lines.append(f"Setup-match: {match.get('status') or 'unknown'} {match.get('score') or ''}.")
        reasons = review.get("reasons") or []
        if reasons:
            lines.append("Belangrijkste redenen:")
            lines.extend(f"- {reason}" for reason in reasons[:3])
        lines.append("Ik voer niets uit. Gebruik dit als review voordat je handmatig of via bot-acties verdergaat.")
        execution_review = self._build_bot_decision_execution_review(review)

        return {
            "response": "\n".join(lines),
            "intent": "bot_decision_review",
            "flow": "bot_decision_review",
            "draft": None,
            "missing_fields": [],
            "invalid_fields": [],
            "next_question": None,
            "can_confirm": False,
            "actions": [],
            "state": {
                "status": "review_ready",
                "current_flow": "bot_decision_review",
                "asset": review.get("asset"),
                "review": review,
                "analysis": {"execution_review": execution_review},
                "autonomy_level": "advice_only",
            },
            "reasoning": {
                "confidence_score": 0.84,
                "risk_detected": review.get("risk_level") in {"medium", "high"},
                "reasons": ["Bot-decision review is read-only; no_order_execution."],
                "coaching_level": "bot_decision_review",
            },
            "suggested_actions": ["Controleer guardrails en trade plan voordat je uitvoert."],
        }

    async def build_bot_execution_decision_response(
        self,
        user_id: int,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = context or {}
        execution_choice = self._bot_execution_choice(query)
        decision = await self._find_bot_decision_for_query(user_id, query, context)
        asset = self._asset_from_query_or_context(query, context)

        if not decision:
            return {
                "response": f"Welke bot-decision bedoel je? Noem het decision_id, bijvoorbeeld: sla bot-decision 123 over.",
                "intent": "bot_execution_decision",
                "flow": "bot_execution_decision",
                "draft": None,
                "missing_fields": ["decision_id"],
                "invalid_fields": [],
                "next_question": "decision_id",
                "can_confirm": False,
                "actions": [],
                "state": {
                    "status": "needs_input",
                    "current_flow": "bot_execution_decision",
                    "asset": asset,
                    "autonomy_level": "confirm_required",
                },
                "reasoning": {
                    "confidence_score": 0.7,
                    "risk_detected": False,
                    "reasons": ["Finn heeft een specifieke bot-decision nodig voordat hij een execution-keuze kan voorbereiden."],
                    "coaching_level": "bot_execution_handoff",
                },
                "suggested_actions": ["Noem het decision_id dat je wilt overslaan, monitoren of uitvoeren."],
            }

        review = self._mission_bot_review_item(decision, {"asset": decision.get("symbol") or asset, "setup": {"id": decision.get("setup_id")}})
        bot = await BotService(self.session).repository.get_bot_config(user_id, int(review["bot_id"])) if self.session else None
        is_live = bool((bot or {}).get("is_live"))
        action = None
        can_confirm = False
        invalid_fields: List[Dict[str, Any]] = []
        response = ""
        next_question = None
        operator_resolution_preview = None

        if execution_choice == "monitor":
            response = (
                f"Ik zet bot-decision #{review['decision_id']} in monitor-modus voor je dagbeeld: "
                f"{review.get('summary')}. Ik voer niets uit en wijzig geen status."
            )
        elif execution_choice == "skip":
            action = self._bot_execution_action("skip_bot_decision", review, is_live=is_live)
            can_confirm = True
            response = f"Ik kan bot-decision #{review['decision_id']} overslaan. Dit annuleert bijbehorende open orders, maar voert geen trade uit."
            operator_resolution_preview = {
                "type": "operator_resolution",
                "title": f"Wat verandert er als je bot-decision #{review['decision_id']} overslaat?",
                "status": "preview",
                "summary": "Finn legt dit vast als bewuste keuze om deze decision vandaag niet door te zetten.",
                "what_changed": [
                    f"Decision #{review['decision_id']} schuift uit je open review-stack zodra je bevestigt.",
                    "Bijbehorende open orders of vervolgdruk worden niet verder nagejaagd vanuit deze decision.",
                ],
                "what_next": [
                    "Pak liever de volgende open review of de hoogste Mission Control-prioriteit op.",
                    "Kom alleen terug als de setup, context of overtuiging echt verandert.",
                ],
            }
        elif execution_choice == "live_preflight":
            action = self._bot_execution_action("live_preflight_bot_decision", review, is_live=is_live)
            can_confirm = True
            response = (
                f"Ik kan een live preflight doen voor bot-decision #{review['decision_id']}. "
                "Dit controleert live-bot en exchange-key readiness, maar voert geen order uit."
            )
        else:
            if is_live:
                invalid_fields.append({
                    "field": "bot.execution_mode",
                    "reason": "Deze bot is live. Gebruik eerst live preflight; Finn voert live orders niet vanuit deze stap uit.",
                })
                next_question = "bot.execution_mode"
                response = (
                    f"Bot-decision #{review['decision_id']} hoort bij een live bot. "
                    "Ik kan eerst een live preflight doen, maar niet direct uitvoeren vanuit Finn."
                )
            elif review.get("action") not in {"buy", "sell"}:
                invalid_fields.append({
                    "field": "bot_decision.action",
                    "reason": "Alleen buy/sell decisions kunnen als paper execution worden gemarkeerd.",
                })
                next_question = "bot_decision.action"
                response = f"Bot-decision #{review['decision_id']} is {review.get('action')}; er is niets om paper uit te voeren."
            else:
                action = self._bot_execution_action("paper_execute_bot_decision", review, is_live=is_live)
                can_confirm = True
                response = (
                    f"Ik kan bot-decision #{review['decision_id']} als paper/manual execution verwerken. "
                    "Dit blijft paper/manual en plaatst geen live order."
                )

        actions = [action] if action else []
        return {
            "response": response,
            "intent": "bot_execution_decision",
            "flow": "bot_execution_decision",
            "draft": None,
            "missing_fields": [],
            "invalid_fields": invalid_fields,
            "next_question": next_question,
            "can_confirm": can_confirm,
            "actions": actions,
            "state": {
                "status": "ready_for_confirmation" if can_confirm else ("blocked" if invalid_fields else "advice_only"),
                "current_flow": "bot_execution_decision",
                "asset": review.get("asset"),
                "execution_choice": execution_choice,
                "review": review,
                "bot": {
                    "id": (bot or {}).get("id"),
                    "name": (bot or {}).get("name"),
                    "is_live": is_live,
                },
                "autonomy_level": "confirm_required" if can_confirm else "advice_only",
                "analysis": {
                    "operator_resolution": operator_resolution_preview,
                    "action_follow_through": operator_resolution_preview,
                } if operator_resolution_preview else {},
            },
            "reasoning": {
                "confidence_score": 0.82,
                "risk_detected": execution_choice in {"paper_execute", "live_preflight"} or bool(invalid_fields),
                "reasons": ["Execution decisions require explicit confirmation and preserve live-trading guardrails."],
                "coaching_level": "bot_execution_handoff",
            },
            "suggested_actions": ["Bevestig alleen als dit overeenkomt met je eigen plan."],
        }

    def _bot_execution_choice(self, query: str) -> str:
        q = (query or "").lower()
        if any(phrase in q for phrase in ["sla over", "sla bot-decision", "sla decision", "overslaan", "skip"]):
            return "skip"
        if "monitor" in q:
            return "monitor"
        if any(phrase in q for phrase in ["live preflight", "live check", "live uitvoeren"]):
            return "live_preflight"
        return "paper_execute"

    async def _find_bot_decision_for_query(
        self,
        user_id: int,
        query: str,
        context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        decision_id = self._extract_id_after_words(query, ["bot-decision", "decision", "beslissing", "proposal", "voorstel"])
        asset = self._asset_from_query_or_context(query, context)
        assets = [asset] + [candidate for candidate in sorted(SUPPORTED_ASSETS) if candidate != asset]
        seen = set()
        decisions: List[Dict[str, Any]] = []
        for symbol in assets:
            bot_today = await BotService(self.session).get_bot_today(user_id, symbol=symbol) if self.session else {"decisions": []}
            for decision in bot_today.get("decisions") or []:
                key = decision.get("id")
                if key in seen:
                    continue
                seen.add(key)
                decisions.append(decision)
        if decision_id:
            return next((decision for decision in decisions if int(decision.get("id") or 0) == decision_id), None)
        return decisions[0] if len(decisions) == 1 else None

    def _bot_execution_action(self, action_type: str, review: Dict[str, Any], *, is_live: bool) -> Dict[str, Any]:
        decision_id = int(review["decision_id"])
        bot_id = int(review["bot_id"])
        setup_match = review.get("setup_match") if isinstance(review.get("setup_match"), dict) else {}
        labels = {
            "skip_bot_decision": "Bot-decision overslaan",
            "paper_execute_bot_decision": "Paper execution bevestigen",
            "live_preflight_bot_decision": "Live preflight controleren",
        }
        risk = "high" if action_type in {"paper_execute_bot_decision", "live_preflight_bot_decision"} or is_live else "medium"
        return {
            "id": self._maintenance_action_id(action_type, [str(bot_id), str(decision_id)]),
            "type": action_type,
            "label": labels.get(action_type, "Bot-decision bevestigen"),
            "payload": {
                "bot_id": bot_id,
                "decision_id": decision_id,
                "asset": review.get("asset"),
                "is_live": is_live,
                "behavioral_context": {
                    "decision_action": review.get("action"),
                    "risk_level": review.get("risk_level"),
                    "confidence": review.get("confidence"),
                    "guardrail_reason": review.get("guardrail_reason"),
                    "guardrails_result": review.get("guardrails_result"),
                    "setup_match_status": setup_match.get("status"),
                    "setup_match_score": setup_match.get("score"),
                },
            },
            "risk_level": risk,
            "requires_confirmation": True,
            "autonomy_level": "confirm_required",
            "guardrails": {
                "requires_confirmation": True,
                "can_execute_without_user": False,
                "no_live_order_execution": action_type != "paper_execute_bot_decision",
                "live_preflight_only": action_type == "live_preflight_bot_decision",
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

        if self._draft_requires_plan_deviation_ack(draft) and not draft.get("plan_deviation_ack"):
            missing.append("plan_deviation_ack")

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
        if next_question == "plan_deviation_ack":
            warning = draft.get("plan_deviation") or {}
            reasons = warning.get("reasons") or []
            lines = [
                "Let op: je houdt je nu niet aan je eigen plan.",
                warning.get("message") or "Deze strategie-wijziging wijkt af van je huidige setup-context.",
            ]
            if reasons:
                lines.append("Waarom Finn remt:")
                lines.extend([f"- {reason}" for reason in reasons[:4]])
            lines.append("Zeg 'bewuste override' als je dit alsnog wilt bevestigen, of 'annuleer' om te stoppen.")
            return "\n".join(lines)
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
        if draft.get("plan_deviation"):
            warning = draft.get("plan_deviation") or {}
            lines.extend([
                "- Plan-afwijking: ja",
                f"- Override bevestigd: {'ja' if draft.get('plan_deviation_ack') else 'nee'}",
                f"- Reden: {warning.get('message')}",
            ])
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
        operation = draft.get("operation") or "create"
        return {
            "status": "ready_for_confirmation" if validation["can_confirm"] else "collecting",
            "current_flow": "strategy_creation",
            "asset": draft.get("asset"),
            "setup_id": draft.get("setup_id"),
            "strategy_id": draft.get("strategy_id"),
            "operation": operation,
            "setup_type": draft.get("setup_type"),
            "setup_options": setup_options or [],
            "changes": draft.get("changes") or [],
            "plan_deviation": draft.get("plan_deviation"),
            "plan_deviation_ack": bool(draft.get("plan_deviation_ack")),
            "next_question": validation["next_question"],
            "autonomy_level": "confirm_required",
            "analysis": {
                "tool_intent_reason": "explicit_update_request" if operation == "update" else "explicit_create_request",
            },
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
        if self._draft_requires_plan_deviation_ack(draft):
            reasons.append("Plan-afwijking gedetecteerd: bewuste override is vereist voordat Finn dit bevestigbaar maakt.")
        return {
            "confidence_score": 0.9 if validation["can_confirm"] else 0.55,
            "risk_detected": bool(validation["invalid_fields"]) or self._draft_requires_plan_deviation_ack(draft),
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

        if self._draft_requires_plan_deviation_ack(draft) and not draft.get("plan_deviation_ack"):
            missing.append("plan_deviation_ack")

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
        if next_question == "plan_deviation_ack":
            warning = draft.get("plan_deviation") or {}
            reasons = warning.get("reasons") or []
            lines = [
                "Let op: je houdt je nu niet aan je eigen plan.",
                warning.get("message") or "Deze bot-wijziging wijkt af van je huidige setup-context.",
            ]
            if reasons:
                lines.append("Waarom Finn remt:")
                lines.extend([f"- {reason}" for reason in reasons[:4]])
            lines.append("Zeg 'bewuste override' als je dit alsnog wilt bevestigen, of 'annuleer' om te stoppen.")
            return "\n".join(lines)

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
            + (
                "\n- Plan-afwijking: ja"
                f"\n- Override bevestigd: {'ja' if draft.get('plan_deviation_ack') else 'nee'}"
                f"\n- Reden: {(draft.get('plan_deviation') or {}).get('message')}"
                if draft.get("plan_deviation") else ""
            )
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
            "plan_deviation": draft.get("plan_deviation"),
            "plan_deviation_ack": bool(draft.get("plan_deviation_ack")),
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
        if self._draft_requires_plan_deviation_ack(draft):
            reasons.append("Plan-afwijking gedetecteerd: bewuste override is vereist voordat Finn dit bevestigbaar maakt.")
        return {
            "confidence_score": 0.9 if validation["can_confirm"] else 0.55,
            "risk_detected": bool(validation["invalid_fields"]) or bool((draft.get("bot") or {}).get("is_live")) or self._draft_requires_plan_deviation_ack(draft),
            "reasons": reasons,
            "coaching_level": "bot_creation",
        }

    def _bot_action_id(self, payload: Dict[str, Any]) -> str:
        normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return f"finn-bot-{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:24]}"

    def _indicator_config_action_id(self, payload: Dict[str, Any]) -> str:
        normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return f"finn-indicator-{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:24]}"

    def _maintenance_action_id(self, action_type: str, parts: List[str]) -> str:
        normalized = json.dumps({"type": action_type, "parts": parts}, sort_keys=True, separators=(",", ":"), default=str)
        return f"finn-maint-{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:24]}"

    def _generate_bot_decision_action_parts(self, bot: Dict[str, Any], open_decision_ids: List[int]) -> List[str]:
        parts = [str(bot.get("id"))]
        if open_decision_ids:
            parts.extend(["open_review", *[str(decision_id) for decision_id in sorted(open_decision_ids)]])
        return parts

    def _is_behavioral_memory_ack(self, q_lower: str) -> bool:
        return any(phrase in q_lower for phrase in [
            "bewust doorgaan",
            "ik bevestig dit",
            "toch decision maken",
            "toch bot-decision",
            "memory akkoord",
            "gedrag akkoord",
            "ik snap het",
            "begrepen",
            "ga door",
        ])

    def _blocked_behavioral_memory_ack_response(
        self,
        asset: str,
        bot_id: int,
        memory_friction: Dict[str, Any],
    ) -> Dict[str, Any]:
        friction = {
            **(memory_friction or {}),
            "requires_ack": True,
            "acknowledged": False,
            "ack_phrase": "bewust doorgaan",
        }
        response = (
            f"Memory check: {friction.get('message')} "
            "Je vroeg eerder opnieuw bot-decisions aan terwijl review nog openstond. "
            "Wil je dit bewust toch doen? Antwoord met 'bewust doorgaan' om pas daarna een nieuwe bot-decision klaar te zetten."
        )
        return {
            "response": response,
            "intent": "bot_decision",
            "flow": "bot_decision",
            "draft": None,
            "missing_fields": ["behavioral_memory_ack"],
            "invalid_fields": [],
            "next_question": "behavioral_memory_ack",
            "can_confirm": False,
            "actions": [],
            "state": {
                "status": "blocked_by_behavioral_memory",
                "current_flow": "bot_decision",
                "asset": asset,
                "bot_id": bot_id,
                "memory_friction": friction,
                "pending_behavioral_memory_friction": friction,
                "autonomy_level": "confirm_required",
            },
            "reasoning": {
                "confidence_score": 0.84,
                "risk_detected": True,
                "reasons": [friction.get("message")],
                "coaching_level": "behavioral_memory_guardrail",
            },
            "suggested_actions": [
                "Review of skip eerst de open bot-decisions.",
                "Antwoord 'bewust doorgaan' als je toch een nieuwe bot-decision wilt.",
            ],
        }

    async def _behavioral_memory_friction_for_action(self, user_id: int, action_type: str) -> Optional[Dict[str, Any]]:
        if not self.session or action_type != "generate_bot_decision":
            return None
        activity_feed = await self._get_recent_finn_activity(user_id, limit=180)
        if not activity_feed:
            return None
        behavioral = self._build_behavioral_insight_from_activity(activity_feed)
        memory = self._build_behavioral_memory_report(activity_feed, behavioral)
        return self._behavioral_memory_friction_from_report(memory, action_type)

    def _behavioral_memory_friction_from_report(self, memory: Dict[str, Any], action_type: str) -> Optional[Dict[str, Any]]:
        if action_type != "generate_bot_decision":
            return None
        for card in memory.get("memory_cards") or []:
            if card.get("type") == "decision_churn":
                return {
                    "type": "decision_churn",
                    "severity": "medium",
                    "message": "je recente memory laat decision-churn zien.",
                    "source": "behavioral_memory",
                    "evidence": card.get("evidence") or [],
                    "safe_alternative": "review of skip eerst de open bot-decisions voordat je nieuwe voorstellen maakt.",
                    "requires_ack": True,
                    "ack_phrase": "bewust doorgaan",
                }
        return None

    async def _open_bot_reviews_for_bot(self, user_id: int, asset: str, bot_id: int) -> List[Dict[str, Any]]:
        if not self.session or bot_id <= 0:
            return []
        try:
            bot_today = await BotService(self.session).get_bot_today(user_id, symbol=asset)
        except Exception:
            return []
        reviews = []
        for decision in bot_today.get("decisions") or []:
            if int(decision.get("bot_id") or 0) != int(bot_id):
                continue
            review = self._mission_bot_review_item(decision, {"asset": decision.get("symbol") or asset, "setup": {"id": decision.get("setup_id")}})
            if review.get("review_status") == "needs_review":
                reviews.append(review)
        return reviews

    def _extract_id_after_words(self, query: str, words: List[str]) -> Optional[int]:
        q = query or ""
        for word in words:
            match = re.search(rf"\b{re.escape(word)}\s*#?\s*(\d+)\b", q, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None

    def _safe_int(self, value: Any) -> Optional[int]:
        try:
            if value is None or value == "":
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

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
            "grootste portfolio risico",
            "grootste risico",
            "welke asset vraagt",
            "welke assets vragen",
            "te veel exposure",
            "risico per asset",
            "portfolio exposure",
            "portefeuille risico",
            "welke bots stapelen",
            "welke plannen stapelen",
            "stapelen risico",
            "welke assets moet ik vandaag negeren",
            "welke asset moet ik vandaag negeren",
            "welke assets laat ik vandaag liggen",
            "welke asset laat ik vandaag liggen",
            "assets negeren",
            "assets laten liggen",
            "welke live bots vragen review",
            "welke live bots vragen vandaag review",
            "welke live bots botsen",
            "live bots botsen",
            "live bots conflict",
            "live bot conflict",
            "welke setups conflicteren",
            "conflicterende setups",
            "bots met overlappende budgetten",
            "overlappende budgetten",
            "dca en trade",
        ]
        return any(phrase in q for phrase in portfolio_phrases)

    def _portfolio_question_focus(self, query: str) -> str:
        q = (query or "").lower()
        if any(phrase in q for phrase in [
            "welke assets moet ik vandaag negeren",
            "welke asset moet ik vandaag negeren",
            "welke assets laat ik vandaag liggen",
            "welke asset laat ik vandaag liggen",
            "assets negeren",
            "asset negeren",
            "assets laten liggen",
            "asset laten liggen",
        ]):
            return "ignore_today"
        if any(phrase in q for phrase in [
            "welke live bots botsen",
            "live bots botsen",
            "live bots conflict",
            "live bot conflict",
            "welke live bots vragen review",
        ]):
            return "live_bot_conflicts"
        if any(phrase in q for phrase in ["te veel exposure", "portfolio exposure", "exposure", "allocatie", "allocation"]):
            return "exposure"
        if any(phrase in q for phrase in ["overlappende budgetten", "bots met overlappende budgetten", "budget overlap", "budgetten"]):
            return "budget_overlap"
        if any(phrase in q for phrase in ["welke setups conflicteren", "conflicterende setups", "dca en trade"]):
            return "setup_conflicts"
        if any(phrase in q for phrase in ["welke bots stapelen", "welke plannen stapelen", "stapelen risico"]):
            return "risk_stacking"
        if any(phrase in q for phrase in ["welke asset vraagt", "welke assets vragen", "asset vraagt", "assets vragen"]):
            return "asset_priority"
        if any(phrase in q for phrase in ["grootste portfolio risico", "grootste risico", "portfolio risico", "portefeuille risico", "risico per asset"]):
            return "risk"
        return "brief"

    def _priority_question_focus(self, query: str) -> str:
        q = (query or "").lower()
        if any(phrase in q for phrase in [
            "wat moet ik juist niet doen",
            "wat moet ik niet doen",
            "vandaag niet doen",
        ]):
            return "ignore_today"
        if any(phrase in q for phrase in [
            "wat kan wachten",
            "kan vandaag wachten",
            "wat kan vandaag wachten",
            "wat laat ik vandaag liggen",
        ]):
            return "wait"
        if any(phrase in q for phrase in [
            "waar moet ik mee beginnen",
            "waar begin ik",
            "wat moet ik nu eerst doen",
            "wat moet ik vandaag eerst doen",
            "help me even kiezen wat ik nu moet doen",
        ]):
            return "start_now"
        if any(phrase in q for phrase in [
            "waar moet ik vandaag op focussen",
            "waar moet ik nu op focussen",
            "wat verdient nu mijn aandacht",
            "wat is nu het belangrijkste",
        ]):
            return "focus"
        if any(phrase in q for phrase in [
            "wat zijn vandaag mijn 3 belangrijkste acties",
            "wat zijn vandaag mijn topprioriteiten",
            "geef mijn top prioriteiten",
        ]):
            return "top3"
        return "headline"

    async def _fetch_daily_scores_with_runtime_refresh(
        self,
        user_id: int,
        asset: str,
        *,
        allow_refresh: bool = True,
    ) -> Optional[Dict[str, Any]]:
        if not self.session:
            return None
        score_repo = ScoreRepository(self.session)
        scores = await score_repo.fetch_daily_scores(user_id, asset)
        if scores or not allow_refresh:
            return scores
        try:
            await ScoreService(score_repo).get_daily_scores(user_id, asset)
            return await score_repo.fetch_daily_scores(user_id, asset)
        except Exception:
            return scores

    async def _build_indicator_analysis_fast(
        self,
        user_id: int,
        asset: str,
        daily_scores: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not self.session:
            return {
                "asset": asset,
                "has_daily_scores": bool(daily_scores),
                "categories": {},
                "warnings": [],
                "suggestions": [],
            }

        macro_repo = MacroDataRepository(self.session)
        technical_repo = TechnicalDataRepository(self.session)
        market_repo = MarketDataRepository(self.session)

        try:
            macro_rows = await macro_repo.get_active_day_macro_data(user_id)
        except Exception:
            macro_rows = []
        try:
            technical_rows = await technical_repo.get_day_data(user_id, asset)
        except Exception:
            technical_rows = []
        try:
            market_rows = await market_repo.get_active_day_indicators(user_id, asset)
        except Exception:
            market_rows = []

        categories = {
            "macro": {"active_count": len(macro_rows)},
            "technical": {"active_count": len(technical_rows)},
            "market": {"active_count": len(market_rows)},
        }
        warnings: List[str] = []
        suggestions: List[str] = []

        for category in ["macro", "technical", "market"]:
            if categories[category]["active_count"] == 0:
                warnings.append(f"Geen actieve {category}-data voor {asset}.")
                suggestions.append(f"Controleer of {category} voor {asset} goed is ingericht.")

        if not daily_scores:
            warnings.append(f"Daily score ontbreekt nog voor {asset}.")
            suggestions.append(f"Genereer of ververs daily scores voor {asset} voordat je dit forceert.")

        return {
            "asset": asset,
            "has_daily_scores": bool(daily_scores),
            "categories": categories,
            "warnings": warnings[:4],
            "suggestions": suggestions[:4],
        }

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

    async def _portfolio_setup_assets(self, user_id: int) -> List[str]:
        if not self.session:
            return ["BTC"]
        try:
            setups = await ScoreRepository(self.session).fetch_active_setups(user_id)
            assets = sorted({
                str(setup.get("symbol") or "").upper()
                for setup in setups
                if str(setup.get("symbol") or "").upper() in SUPPORTED_ASSETS
            })
            return assets or ["BTC"]
        except Exception:
            return ["BTC"]

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
        follow_up_actions = self._daily_follow_up_actions(asset, data_readiness, blockers, decisions)
        agent_verdicts = self._build_daily_agent_verdicts(
            asset=asset,
            stance=stance,
            data_readiness=data_readiness,
            blockers=blockers,
            active_strategy=active_strategy,
            decisions=decisions,
            indicator_analysis=indicator_analysis,
        )
        agent_controller = self._build_agent_controller(agent_verdicts, context="daily_coach")
        agent_controller["primary_action"] = self._agent_controller_primary_action(
            agent_controller,
            follow_up_actions,
            asset=asset,
        )

        return {
            "asset": asset,
            "date": _utc_now().date().isoformat(),
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
            "agent_verdicts": agent_verdicts,
            "agent_controller": agent_controller,
            "follow_up_actions": follow_up_actions,
            "reasons": reasons,
            "suggested_actions": suggested_actions[:5],
        }

    def _build_daily_agent_verdicts(
        self,
        *,
        asset: str,
        stance: str,
        data_readiness: Dict[str, Any],
        blockers: List[Dict[str, Any]],
        active_strategy: Dict[str, Any],
        decisions: List[Dict[str, Any]],
        indicator_analysis: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        categories = indicator_analysis.get("categories") or {}
        config_gaps = set(data_readiness.get("config_gaps") or [])

        def blocker_for(category: str) -> Optional[Dict[str, Any]]:
            return next((item for item in blockers if item.get("category") == category), None)

        def score_agent(category: str, label: str) -> Dict[str, Any]:
            blocker = blocker_for(category)
            active_count = (categories.get(category) or {}).get("active_count", 0)
            if blocker:
                status = "blocks_plan"
                priority = "high"
                reason = f"{label} blokkeert: score {blocker.get('score')} buiten range {blocker.get('range')}."
                next_action = f"Vraag waarom {category} {asset} blokkeert."
            elif category in config_gaps:
                status = "needs_config"
                priority = "high"
                reason = f"{label} heeft nog geen actieve indicatorlaag."
                next_action = f"Voeg {label.lower()} indicatorconfig toe."
            else:
                status = "clear" if active_count else "unknown"
                priority = "low" if active_count else "medium"
                reason = f"{label} geeft geen blocker." if active_count else f"{label} heeft onvoldoende actieve data."
                next_action = "Geen actie nodig." if active_count else f"Controleer {label.lower()} data."
            return {
                "agent": f"{category}_agent",
                "label": f"{label} Agent",
                "status": status,
                "priority": priority,
                "reason": reason,
                "evidence": {
                    "asset": asset,
                    "active_indicator_count": active_count,
                    "blocker": blocker,
                },
                "next_action": next_action,
            }

        risk_status = "blocked" if blockers else ("ready" if stance == "plan_is_active" else "waiting_for_data")
        strategy_active = bool(active_strategy.get("active"))
        return [
            score_agent("macro", "Macro"),
            score_agent("technical", "Technical"),
            {
                "agent": "risk_agent",
                "label": "Risk Agent",
                "status": risk_status,
                "priority": "high" if blockers else "low",
                "reason": "Setup blokkeert volgens je eigen ranges." if blockers else "Geen setup-blocker gevonden." if stance == "plan_is_active" else data_readiness.get("message"),
                "evidence": {"blocker_count": len(blockers), "stance": stance},
                "next_action": "Niet forceren; los eerst blockers op." if blockers else "Gebruik confirm-flows voor elke vervolgstap.",
            },
            {
                "agent": "strategy_agent",
                "label": "Strategy Agent",
                "status": "active_today" if strategy_active else "no_active_strategy",
                "priority": "medium" if not strategy_active else "low",
                "reason": "Er is een actieve strategie voor vandaag." if strategy_active else "Geen actieve strategie voor vandaag gevonden.",
                "evidence": {"active_strategy": active_strategy},
                "next_action": "Review strategy voordat je execution zoekt." if not strategy_active else "Controleer alleen wijzigingen via confirm.",
            },
            {
                "agent": "execution_agent",
                "label": "Execution Agent",
                "status": "review_ready" if decisions else "no_decision",
                "priority": "medium" if decisions else "low",
                "reason": f"{len(decisions)} bot-decision(s) staan klaar." if decisions else "Geen bot-decision voor vandaag gevonden.",
                "evidence": {"decision_count": len(decisions)},
                "next_action": "Review bot-decision voordat je uitvoert." if decisions else "Maak alleen een bot-decision als het plan dat vraagt.",
            },
        ]

    def _daily_follow_up_actions(
        self,
        asset: str,
        data_readiness: Dict[str, Any],
        blockers: List[Dict[str, Any]],
        decisions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        actions = []
        config_gaps = data_readiness.get("config_gaps") or []
        if "macro" in config_gaps:
            actions.append({
                "type": "chat_prompt",
                "label": "Macro toevoegen",
                "prompt": "Voeg Bitcoin Dominance toe aan macro",
                "handoff": "indicator_config",
                "requires_confirmation": True,
            })
        if "technical" in config_gaps:
            actions.append({
                "type": "chat_prompt",
                "label": "Technical toevoegen",
                "prompt": f"Voeg RSI toe aan technical voor {asset} met standaard scoring weight 1",
                "handoff": "indicator_config",
                "requires_confirmation": True,
            })
        if data_readiness.get("status") in {"score_generation_missing", "indicator_config_missing", "onboarding_incomplete", "ready_with_gaps"}:
            actions.append({
                "type": "confirmable_action_prompt",
                "label": "Daily scores verversen",
                "prompt": f"Ververs daily scores voor {asset}",
                "handoff": "daily_score_refresh",
                "requires_confirmation": True,
            })
        if blockers:
            category = blockers[0].get("category") or "macro"
            actions.append({
                "type": "chat_prompt",
                "label": f"Waarom blokkeert {category}?",
                "prompt": f"Waarom blokkeert {category} mijn {asset} setup?",
                "handoff": "indicator_insight",
                "requires_confirmation": False,
            })
        if not decisions:
            actions.append({
                "type": "confirmable_action_prompt",
                "label": "Bot-decision maken",
                "prompt": f"Maak bot-decision voor {asset}",
                "handoff": "bot_decision",
                "requires_confirmation": True,
            })
        return actions[:5]

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
            if config_gaps:
                message = f"Daily scores zijn beschikbaar, maar deze indicatorlagen zijn nog niet actief ingericht: {', '.join(config_gaps)}."
            else:
                message = "Daily scores zijn beschikbaar en de indicatorlagen zijn ingericht."
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

    def _build_portfolio_daily_coach_analysis(
        self,
        asset_analyses: List[Dict[str, Any]],
        portfolio_context: Optional[Dict[str, Any]] = None,
        setup_context_by_asset: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        ranked = sorted(asset_analyses, key=self._portfolio_priority_sort_key)
        actionable_assets = [a for a in ranked if a.get("stance") == "plan_is_active"]
        blocked_assets = [a for a in ranked if a.get("stance") == "wait_for_plan"]
        scoreless_assets = [a for a in ranked if a.get("stance") == "wait_for_scores"]
        warning_assets = [
            a for a in ranked
            if (a.get("indicator_summary") or {}).get("warnings")
        ]
        portfolio_readiness = self._build_portfolio_data_readiness(ranked)

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
                "active_strategy": item.get("active_strategy") or {},
                "bot_decision_count": (item.get("bot_today") or {}).get("decision_count", 0),
                "warnings": ((item.get("indicator_summary") or {}).get("warnings") or [])[:2],
                "data_readiness": item.get("data_readiness") or {},
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
        portfolio_risk = self._build_portfolio_risk_analysis(ranked, portfolio_context or {}, setup_context_by_asset or {})
        if portfolio_risk.get("top_asset"):
            suggested_actions.append(
                f"Bekijk portfolio-risico voor {portfolio_risk.get('top_asset')}: {portfolio_risk.get('top_reason')}"
            )
        ignore_today_assets = portfolio_risk.get("ignore_today_assets") or []
        if ignore_today_assets:
            assets = ", ".join(item.get("asset") for item in ignore_today_assets[:3] if item.get("asset"))
            suggested_actions.append(f"Laat vandaag liever liggen: {assets}.")
        for action in portfolio_readiness.get("suggested_actions") or []:
            if action not in suggested_actions:
                suggested_actions.append(action)
        if not asset_analyses:
            suggested_actions.append("Maak eerst een setup aan; daarna kan Finn echte portfolio-prioriteiten bepalen.")

        reasons = []
        if not asset_analyses:
            reasons.append("Geen opgeslagen setups gevonden voor portfolio-briefing.")
        else:
            reasons.append(f"{len(asset_analyses)} setup-assets gecontroleerd.")
            reasons.append(f"{len(actionable_assets)} actief, {len(blocked_assets)} geblokkeerd, {len(scoreless_assets)} zonder daily scores.")
        follow_up_actions = self._portfolio_follow_up_actions(ranked, portfolio_readiness, portfolio_risk)
        agent_verdicts = self._build_portfolio_agent_verdicts(
            ranked,
            portfolio_risk,
            portfolio_readiness,
        )
        agent_controller = self._build_agent_controller(agent_verdicts, context="portfolio_daily_coach")
        agent_controller["primary_action"] = self._agent_controller_primary_action(
            agent_controller,
            follow_up_actions,
            asset=(ranked[0].get("asset") if ranked else None),
        )

        return {
            "scope": "portfolio",
            "date": _utc_now().date().isoformat(),
            "asset_count": len(asset_analyses),
            "has_any_scores": any(a.get("has_scores") for a in asset_analyses),
            "actionable_assets": actionable_assets,
            "blocked_assets": blocked_assets,
            "scoreless_assets": scoreless_assets,
            "warning_assets": warning_assets,
            "data_readiness": portfolio_readiness,
            "portfolio_risk": portfolio_risk,
            "agent_verdicts": agent_verdicts,
            "agent_controller": agent_controller,
            "top_priorities": top_priorities,
            "assets": ranked,
            "follow_up_actions": follow_up_actions,
            "reasons": reasons,
            "suggested_actions": suggested_actions[:5],
        }

    def _build_portfolio_agent_verdicts(
        self,
        assets: List[Dict[str, Any]],
        portfolio_risk: Dict[str, Any],
        portfolio_readiness: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        def count_category_blockers(category: str) -> int:
            return sum(
                1 for asset in assets
                for blocker in (asset.get("blockers") or [])
                if blocker.get("category") == category
            )

        macro_blocks = count_category_blockers("macro")
        technical_blocks = count_category_blockers("technical")
        ready_gaps = portfolio_readiness.get("config_gap_assets") or []
        risk_status = portfolio_risk.get("status") or "unknown"
        conflicts = portfolio_risk.get("conflicts") or []
        review_decisions = sum((asset.get("bot_today") or {}).get("decision_count", 0) for asset in assets)
        active_strategies = len([asset for asset in assets if (asset.get("active_strategy") or {}).get("active")])

        return [
            {
                "agent": "macro_agent",
                "label": "Macro Agent",
                "status": "blocks_portfolio" if macro_blocks else ("needs_config" if ready_gaps else "clear"),
                "priority": "high" if macro_blocks or ready_gaps else "low",
                "reason": f"{macro_blocks} asset(s) worden door macro geblokkeerd." if macro_blocks else "Geen macro-blocker in de portfolio-brief.",
                "evidence": {"blocked_assets": macro_blocks, "config_gap_assets": ready_gaps},
                "next_action": "Review macro-blockers of voeg macro coverage toe." if macro_blocks or ready_gaps else "Geen macro-actie nodig.",
            },
            {
                "agent": "technical_agent",
                "label": "Technical Agent",
                "status": "blocks_portfolio" if technical_blocks else "clear",
                "priority": "high" if technical_blocks else "low",
                "reason": f"{technical_blocks} asset(s) worden technisch geblokkeerd." if technical_blocks else "Geen technical-blocker in de portfolio-brief.",
                "evidence": {"blocked_assets": technical_blocks},
                "next_action": "Review technical indicators." if technical_blocks else "Geen technical-actie nodig.",
            },
            {
                "agent": "risk_agent",
                "label": "Risk Agent",
                "status": risk_status,
                "priority": "high" if risk_status in {"high_attention", "needs_data"} or conflicts else "medium",
                "reason": portfolio_risk.get("message") or "Portfolio risk geanalyseerd.",
                "evidence": {
                    "top_asset": portfolio_risk.get("top_asset"),
                    "conflict_count": len(conflicts),
                    "risk_stack_count": len(portfolio_risk.get("risk_stacks") or []),
                },
                "next_action": "Werk eerst het hoogste portfolio-risico af.",
            },
            {
                "agent": "strategy_agent",
                "label": "Strategy Agent",
                "status": "strategies_active" if active_strategies else "no_active_strategy",
                "priority": "medium" if not active_strategies and assets else "low",
                "reason": f"{active_strategies} actieve strategie-context(en) gevonden.",
                "evidence": {"active_strategy_count": active_strategies, "asset_count": len(assets)},
                "next_action": "Check strategy-context per risicovol asset.",
            },
            {
                "agent": "execution_agent",
                "label": "Execution Agent",
                "status": "review_ready" if review_decisions else "no_open_decision",
                "priority": "high" if review_decisions else "low",
                "reason": f"{review_decisions} bot-decision(s) vragen review." if review_decisions else "Geen open bot-decision in deze briefing.",
                "evidence": {"decision_count": review_decisions},
                "next_action": "Review open bot-decisions voordat je nieuwe maakt." if review_decisions else "Geen execution-actie nodig.",
            },
        ]

    def _build_portfolio_risk_analysis(
        self,
        asset_analyses: List[Dict[str, Any]],
        portfolio_context: Dict[str, Any],
        setup_context_by_asset: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        setup_context_by_asset = setup_context_by_asset or {}
        bots = portfolio_context.get("bots") or []
        global_ctx = portfolio_context.get("global") or {}
        allocations = global_ctx.get("allocations_pct") or {}
        total_equity = self._to_float(global_ctx.get("total_equity")) or 0.0
        total_position_value = self._to_float(global_ctx.get("current_position_value")) or 0.0
        bots_by_asset: Dict[str, List[Dict[str, Any]]] = {}
        for bot in bots:
            symbol = str(bot.get("symbol") or "").upper()
            if not symbol:
                continue
            bots_by_asset.setdefault(symbol, []).append(bot)

        asset_risk = []
        conflicts = []
        concentration_warnings = []
        risk_stacks = []

        for item in asset_analyses:
            asset = str(item.get("asset") or "").upper()
            asset_bots = bots_by_asset.get(asset, [])
            exposure_eur = sum(
                self._to_float(bot.get("position_value")) or self._to_float(bot.get("current_position_value")) or 0.0
                for bot in asset_bots
            )
            budget_eur = sum(self._to_float(bot.get("budget_total")) or self._to_float(bot.get("budget_total_eur")) or 0.0 for bot in asset_bots)
            allocation_pct = self._to_float(allocations.get(asset))
            if allocation_pct is None and total_equity > 0:
                allocation_pct = round((exposure_eur / total_equity) * 100, 2)
            position_share_pct = round((exposure_eur / total_position_value) * 100, 2) if total_position_value > 0 else None

            blockers = item.get("blockers") or []
            warnings = (item.get("indicator_summary") or {}).get("warnings") or []
            readiness = item.get("data_readiness") or {}
            setup_context = setup_context_by_asset.get(asset) or {}
            bot_count = len(asset_bots)
            live_bot_count = len([bot for bot in asset_bots if bot.get("is_live")])
            active_bot_count = len([bot for bot in asset_bots if bot.get("is_active")])
            active_strategy = item.get("active_strategy") or {}
            strategy_active = bool(active_strategy.get("active"))

            risk_flags = []
            if item.get("stance") == "wait_for_plan":
                risk_flags.append("blocked_setup")
            if item.get("stance") == "wait_for_scores":
                risk_flags.append("score_missing")
            if readiness.get("config_gaps"):
                risk_flags.append("data_gap")
            if allocation_pct is not None and allocation_pct >= 60:
                risk_flags.append("high_exposure")
            elif allocation_pct is not None and allocation_pct >= 40:
                risk_flags.append("elevated_exposure")
            if bot_count > 1:
                risk_flags.append("multiple_bots")
            if live_bot_count:
                risk_flags.append("live_bot")
            if live_bot_count > 1:
                risk_flags.append("multiple_live_bots")
            if setup_context.get("setup_count", 0) > 1:
                risk_flags.append("multiple_setups")
            if setup_context.get("mixed_setup_types"):
                risk_flags.append("mixed_setup_types")
            budget_overlap = budget_eur > 0 and (
                (total_equity > 0 and budget_eur > total_equity)
                or (total_equity <= 0 and bot_count > 1)
            )
            if budget_overlap:
                risk_flags.append("budget_overlap")
            if strategy_active and live_bot_count and (
                item.get("stance") != "plan_is_active"
                or bool(blockers)
                or setup_context.get("mixed_setup_types")
                or budget_overlap
            ):
                risk_flags.append("live_strategy_conflict")

            score = 0
            if item.get("stance") == "wait_for_plan":
                score += 55
            elif item.get("stance") == "wait_for_scores":
                score += 45
            elif item.get("stance") == "plan_is_active":
                score += 30
            score += min(len(blockers) * 8, 24)
            score += min(len(warnings) * 5, 15)
            if allocation_pct is not None:
                if allocation_pct >= 60:
                    score += 25
                elif allocation_pct >= 40:
                    score += 12
            score += min(max(bot_count - 1, 0) * 8, 16)
            if live_bot_count:
                score += 10
            if live_bot_count > 1:
                score += 12
            if readiness.get("config_gaps"):
                score += 8
            if setup_context.get("setup_count", 0) > 1:
                score += 8
            if setup_context.get("mixed_setup_types"):
                score += 12
            if budget_overlap:
                score += 15
            if "live_strategy_conflict" in risk_flags:
                score += 18
            score = min(score, 100)
            risk_level = "high" if score >= 75 else "medium" if score >= 50 else "low"

            if item.get("stance") == "wait_for_plan" and bot_count:
                conflicts.append({
                    "type": "blocked_setup_with_bot",
                    "asset": asset,
                    "severity": "high" if live_bot_count else "medium",
                    "reason": f"{asset} heeft een geblokkeerde setup maar ook {bot_count} bot(s) gekoppeld.",
                })
            if bot_count > 1:
                conflicts.append({
                    "type": "multiple_bots_same_asset",
                    "asset": asset,
                    "severity": "medium",
                    "reason": f"{asset} heeft {bot_count} bot-configuraties; controleer overlap en budgetstapeling.",
                })
            if live_bot_count > 1:
                conflicts.append({
                    "type": "multiple_live_bots_same_asset",
                    "asset": asset,
                    "severity": "high",
                    "reason": f"{asset} heeft {live_bot_count} live bots tegelijk; review execution-volgorde en dubbele exposure.",
                })
            if setup_context.get("setup_count", 0) > 1:
                conflicts.append({
                    "type": "multiple_setups_same_asset",
                    "asset": asset,
                    "severity": "medium",
                    "reason": f"{asset} heeft {setup_context.get('setup_count')} setups; controleer of de regels elkaar niet tegenspreken.",
                    "setup_ids": setup_context.get("setup_ids") or [],
                    "setup_types": setup_context.get("setup_types") or [],
                })
            if setup_context.get("mixed_setup_types"):
                conflicts.append({
                    "type": "mixed_setup_types_same_asset",
                    "asset": asset,
                    "severity": "high",
                    "reason": f"{asset} heeft DCA en trade setups tegelijk; Finn moet zeker weten welke intent vandaag leidend is.",
                    "setup_ids": setup_context.get("setup_ids") or [],
                    "setup_types": setup_context.get("setup_types") or [],
                })
            if budget_overlap:
                equity_label = f"portfolio equity EUR {round(total_equity, 2)}" if total_equity > 0 else "onbekende of nul portfolio equity"
                conflicts.append({
                    "type": "bot_budget_overlap",
                    "asset": asset,
                    "severity": "high" if total_equity <= 0 or budget_eur >= total_equity * 1.5 else "medium",
                    "reason": f"{asset} botbudgetten tellen op tot EUR {round(budget_eur, 2)}, tegenover {equity_label}.",
                })
            if "live_strategy_conflict" in risk_flags:
                conflicts.append({
                    "type": "live_strategy_conflict",
                    "asset": asset,
                    "severity": "high" if live_bot_count > 1 or item.get("stance") == "wait_for_plan" else "medium",
                    "reason": (
                        f"{asset} heeft een actieve strategie én {live_bot_count} live bot(s), "
                        "maar de setup/risklaag is niet schoon genoeg om execution blind te vertrouwen."
                    ),
                })
            if item.get("stance") == "plan_is_active" and allocation_pct is not None and allocation_pct >= 60:
                conflicts.append({
                    "type": "active_plan_high_exposure",
                    "asset": asset,
                    "severity": "medium",
                    "reason": f"{asset} plan lijkt actief, maar de asset heeft al {allocation_pct}% allocatie; review exposure voordat je opschaalt.",
                })
            if allocation_pct is not None and allocation_pct >= 60:
                concentration_warnings.append({
                    "asset": asset,
                    "allocation_pct": allocation_pct,
                    "reason": f"{asset} draagt {allocation_pct}% van de portfolio equity.",
                })
            elif position_share_pct is not None and position_share_pct >= 70:
                concentration_warnings.append({
                    "asset": asset,
                    "position_share_pct": position_share_pct,
                    "reason": f"{asset} draagt {position_share_pct}% van de open positie-waarde.",
                })

            first_blocker = (blockers or [{}])[0]
            if first_blocker.get("category"):
                next_best_action = f"Vraag waarom {first_blocker.get('category')} {asset} blokkeert."
                top_reason = f"{first_blocker.get('category')} blokkeert"
            elif readiness.get("config_gaps"):
                next_best_action = f"Vul datakwaliteit voor {asset} aan."
                top_reason = "datakwaliteit is dun"
            elif risk_flags:
                next_best_action = f"Review {asset} exposure en bot-configuratie."
                top_reason = ", ".join(risk_flags[:2])
            else:
                next_best_action = f"Monitor {asset}; geen harde portfolio-risk vlag."
                top_reason = "geen harde vlag"

            asset_risk.append({
                "asset": asset,
                "risk_score": score,
                "risk_level": risk_level,
                "risk_flags": risk_flags,
                "stance": item.get("stance"),
                "blocker_count": len(blockers),
                "has_scores": bool(item.get("has_scores")),
                "exposure_eur": round(exposure_eur, 2),
                "budget_eur": round(budget_eur, 2),
                "allocation_pct": allocation_pct,
                "position_share_pct": position_share_pct,
                "bot_count": bot_count,
                "active_bot_count": active_bot_count,
                "live_bot_count": live_bot_count,
                "next_best_action": next_best_action,
                "top_reason": top_reason,
            })
            stack_factors = []
            if "blocked_setup" in risk_flags:
                stack_factors.append("setup geblokkeerd")
            if "high_exposure" in risk_flags:
                stack_factors.append("hoge exposure")
            elif "elevated_exposure" in risk_flags:
                stack_factors.append("verhoogde exposure")
            if "multiple_bots" in risk_flags:
                stack_factors.append("meerdere bots")
            if "live_bot" in risk_flags:
                stack_factors.append("live bot actief")
            if "multiple_live_bots" in risk_flags:
                stack_factors.append("meerdere live bots")
            if "data_gap" in risk_flags:
                stack_factors.append("dunne datalaag")
            if "multiple_setups" in risk_flags:
                stack_factors.append("meerdere setups")
            if "mixed_setup_types" in risk_flags:
                stack_factors.append("DCA en trade tegelijk")
            if "budget_overlap" in risk_flags:
                stack_factors.append("botbudget boven equity")
            if "live_strategy_conflict" in risk_flags:
                stack_factors.append("live bot en strategie wringen")
            if len(stack_factors) >= 2:
                risk_stacks.append({
                    "asset": asset,
                    "severity": "high" if score >= 75 else "medium",
                    "risk_score": score,
                    "factors": stack_factors,
                    "reason": f"{asset} stapelt risico: {', '.join(stack_factors[:4])}.",
                    "next_best_action": next_best_action,
                })

        asset_risk = sorted(asset_risk, key=lambda item: (-item["risk_score"], item["asset"]))
        risk_stacks = sorted(risk_stacks, key=lambda item: (-item["risk_score"], item["asset"]))
        ranked_conflicts = self._portfolio_ranked_conflicts(conflicts, asset_risk)
        live_bot_hotspots = self._portfolio_live_bot_hotspots(asset_risk)
        high_assets = [item for item in asset_risk if item["risk_level"] == "high"]
        medium_assets = [item for item in asset_risk if item["risk_level"] == "medium"]
        ignore_today_assets = self._portfolio_ignore_today_assets(asset_risk)
        hard_ignore_assets = [
            item for item in ignore_today_assets
            if item.get("risk_level") == "high"
            or item.get("reason") not in {
                "setup blokkeert nog",
                "daily score of datalaag is nog niet betrouwbaar",
            }
        ]
        if not asset_analyses:
            status = "no_assets"
            message = "Geen setups gevonden om portfolio-risk te bepalen."
        elif hard_ignore_assets:
            status = "high_attention"
            message = "Er zijn assets die je vandaag beter laat liggen totdat de risk stack rustiger is."
        elif high_assets or conflicts:
            status = "high_attention"
            message = "Er zijn portfolio-risico's die vandaag aandacht vragen."
        elif concentration_warnings:
            status = "concentrated"
            message = "De portfolio lijkt geconcentreerd in een of meer assets."
        elif any("score_missing" in item["risk_flags"] or "data_gap" in item["risk_flags"] for item in asset_risk):
            status = "needs_data"
            message = "Portfolio-risk is deels onzeker door ontbrekende of dunne datalagen."
        elif medium_assets:
            status = "watch"
            message = "Geen harde portfolio-conflicten, maar enkele assets vragen monitoring."
        else:
            status = "balanced"
            message = "Geen duidelijke portfolio-risk vlaggen gevonden."

        top = asset_risk[0] if asset_risk else {}
        asset_priority = [
            {
                "rank": index,
                "asset": item.get("asset"),
                "priority": "eerst oplossen" if item.get("risk_level") == "high" else "reviewen" if item.get("risk_level") == "medium" else "monitoren",
                "risk_score": item.get("risk_score"),
                "risk_level": item.get("risk_level"),
                "reason": item.get("top_reason"),
                "next_best_action": item.get("next_best_action"),
            }
            for index, item in enumerate(asset_risk[:5], start=1)
        ]
        return {
            "status": status,
            "message": message,
            "total_equity": total_equity,
            "current_position_value": total_position_value,
            "cash_balance": self._to_float(global_ctx.get("cash_balance")) or 0.0,
            "allocations_pct": allocations,
            "top_asset": top.get("asset"),
            "top_reason": top.get("top_reason"),
            "asset_priority": asset_priority,
            "asset_risk": asset_risk,
            "ignore_today_assets": ignore_today_assets,
            "ranked_conflicts": ranked_conflicts,
            "live_bot_hotspots": live_bot_hotspots,
            "risk_stacks": risk_stacks,
            "concentration_warnings": concentration_warnings,
            "conflicts": conflicts,
        }

    def _portfolio_ignore_today_assets(self, asset_risk: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        ignore_today = []

        for item in asset_risk:
            flags = set(item.get("risk_flags") or [])
            asset = item.get("asset")
            reason = None
            unblock_condition = None

            if "multiple_live_bots" in flags:
                reason = "meerdere live bots sturen op dezelfde asset"
                unblock_condition = "Beperk eerst welke live bot vandaag leidend is voordat je verder uitvoert."
            elif "live_strategy_conflict" in flags:
                reason = "live bot en strategie-intentie lopen niet netjes in lijn"
                unblock_condition = "Maak eerst de strategie-intentie en live execution-lagen weer consistent."
            elif "blocked_setup" in flags:
                reason = "setup blokkeert nog"
                unblock_condition = "Wacht tot de setup niet meer blokkeert voordat je deze asset opnieuw oppakt."
            elif "score_missing" in flags or "data_gap" in flags:
                reason = "daily score of datalaag is nog niet betrouwbaar"
                unblock_condition = "Ververs eerst daily scores of rond de ontbrekende datalaag af."
            elif "budget_overlap" in flags:
                reason = "botbudgetten stapelen boven portfolio-equity"
                unblock_condition = "Maak eerst botbudgetten en portfolio-equity consistent."
            elif "mixed_setup_types" in flags:
                reason = "DCA en trade-intentie lopen door elkaar"
                unblock_condition = "Kies eerst welke setup-intent vandaag leidend is."
            elif "high_exposure" in flags and ("multiple_bots" in flags or (item.get("live_bot_count") or 0) > 0):
                reason = "exposure is al hoog terwijl meerdere botlagen actief zijn"
                unblock_condition = "Review eerst open exposure en actieve bots voordat je opschaalt."

            if not reason:
                continue

            ignore_today.append({
                "asset": asset,
                "risk_score": item.get("risk_score"),
                "risk_level": item.get("risk_level"),
                "reason": reason,
                "top_reason": item.get("top_reason"),
                "unblock_condition": unblock_condition,
                "next_best_action": item.get("next_best_action"),
            })

        return sorted(
            ignore_today,
            key=lambda entry: (
                -(self._to_float(entry.get("risk_score")) or 0.0),
                str(entry.get("asset") or ""),
            ),
        )

    def _portfolio_ranked_conflicts(
        self,
        conflicts: List[Dict[str, Any]],
        asset_risk: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        asset_lookup = {
            str(item.get("asset") or "").upper(): item
            for item in (asset_risk or [])
            if item.get("asset")
        }
        severity_rank = {"high": 3, "medium": 2, "low": 1}
        ranked = []

        for conflict in conflicts or []:
            asset = str(conflict.get("asset") or "").upper()
            risk = asset_lookup.get(asset) or {}
            severity = str(conflict.get("severity") or risk.get("risk_level") or "low").lower()
            ranked.append({
                **conflict,
                "asset": asset or conflict.get("asset"),
                "risk_score": risk.get("risk_score"),
                "risk_level": risk.get("risk_level"),
                "live_bot_count": risk.get("live_bot_count"),
                "priority_rank": severity_rank.get(severity, 0),
            })

        return sorted(
            ranked,
            key=lambda item: (
                -int(item.get("priority_rank") or 0),
                -(self._to_float(item.get("risk_score")) or 0.0),
                str(item.get("asset") or ""),
            ),
        )

    def _portfolio_live_bot_hotspots(self, asset_risk: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        hotspots = []

        for item in asset_risk or []:
            live_bot_count = int(item.get("live_bot_count") or 0)
            if live_bot_count <= 0:
                continue
            if item.get("risk_level") == "low" and "multiple_bots" not in (item.get("risk_flags") or []):
                continue

            flags = item.get("risk_flags") or []
            summary_bits = []
            if "high_exposure" in flags:
                summary_bits.append("hoge exposure")
            elif "elevated_exposure" in flags:
                summary_bits.append("verhoogde exposure")
            if "multiple_bots" in flags:
                summary_bits.append("meerdere bots")
            if "multiple_live_bots" in flags:
                summary_bits.append("meerdere live bots")
            if "blocked_setup" in flags:
                summary_bits.append("setup blokkeert")
            if "budget_overlap" in flags:
                summary_bits.append("budget overlap")
            if "live_strategy_conflict" in flags:
                summary_bits.append("strategie wringt met live bot")

            hotspots.append({
                "asset": item.get("asset"),
                "risk_score": item.get("risk_score"),
                "risk_level": item.get("risk_level"),
                "live_bot_count": live_bot_count,
                "reason": item.get("top_reason"),
                "summary": ", ".join(summary_bits[:3]) if summary_bits else "live bot vraagt review",
                "next_best_action": item.get("next_best_action"),
            })

        return sorted(
            hotspots,
            key=lambda item: (
                -(self._to_float(item.get("risk_score")) or 0.0),
                -int(item.get("live_bot_count") or 0),
                str(item.get("asset") or ""),
            ),
        )

    def _portfolio_setup_context(self, setups_by_asset: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
        context: Dict[str, Dict[str, Any]] = {}
        for asset, setups in (setups_by_asset or {}).items():
            setup_types = sorted({
                str(setup.get("setup_type") or "").lower()
                for setup in setups
                if setup.get("setup_type")
            })
            context[asset] = {
                "setup_count": len(setups),
                "setup_ids": [setup.get("id") for setup in setups if setup.get("id") is not None],
                "setup_names": [setup.get("name") for setup in setups if setup.get("name")],
                "setup_types": setup_types,
                "timeframes": sorted({
                    str(setup.get("timeframe") or "")
                    for setup in setups
                    if setup.get("timeframe")
                }),
                "mixed_setup_types": len(setup_types) > 1,
            }
        return context

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

    def _build_portfolio_data_readiness(self, asset_analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
        by_asset = []
        onboarding_gap_assets = []
        config_gap_assets = []
        score_generation_gap_assets = []
        ready_with_gaps_assets = []

        for item in asset_analyses:
            asset = item.get("asset")
            readiness = item.get("data_readiness") or {}
            status = readiness.get("status")
            entry = {
                "asset": asset,
                "status": status,
                "message": readiness.get("message"),
                "onboarding_gaps": readiness.get("onboarding_gaps") or [],
                "config_gaps": readiness.get("config_gaps") or [],
            }
            by_asset.append(entry)
            if status == "onboarding_incomplete":
                onboarding_gap_assets.append(asset)
            if readiness.get("config_gaps"):
                config_gap_assets.append(asset)
            if status == "score_generation_missing":
                score_generation_gap_assets.append(asset)
            if status == "ready_with_gaps":
                ready_with_gaps_assets.append(asset)

        if onboarding_gap_assets:
            status = "onboarding_incomplete"
            message = f"Onboarding/config ontbreekt nog voor: {', '.join(onboarding_gap_assets)}."
        elif score_generation_gap_assets:
            status = "score_generation_missing"
            message = f"Configuratie lijkt aanwezig, maar daily score-generatie ontbreekt voor: {', '.join(score_generation_gap_assets)}."
        elif config_gap_assets:
            status = "ready_with_gaps"
            message = f"Scores bestaan, maar indicatorlagen zijn nog dun voor: {', '.join(config_gap_assets)}."
        else:
            status = "ready" if asset_analyses else "no_setups"
            message = "Alle gecontroleerde assets hebben bruikbare data." if asset_analyses else "Geen setups gevonden om data readiness te bepalen."

        suggested_actions = []
        for entry in by_asset:
            for action in (next((a.get("data_readiness") or {} for a in asset_analyses if a.get("asset") == entry.get("asset")), {}).get("suggested_actions") or []):
                if action not in suggested_actions:
                    suggested_actions.append(action)

        return {
            "status": status,
            "message": message,
            "assets": by_asset,
            "onboarding_gap_assets": onboarding_gap_assets,
            "config_gap_assets": config_gap_assets,
            "score_generation_gap_assets": score_generation_gap_assets,
            "ready_with_gaps_assets": ready_with_gaps_assets,
            "suggested_actions": suggested_actions[:5],
        }

    def _portfolio_follow_up_actions(
        self,
        asset_analyses: List[Dict[str, Any]],
        readiness: Dict[str, Any],
        portfolio_risk: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        actions = []
        first_asset = (asset_analyses[0].get("asset") if asset_analyses else "BTC") or "BTC"
        portfolio_risk = portfolio_risk or {}
        if readiness.get("config_gap_assets"):
            actions.append({
                "type": "chat_prompt",
                "label": "Macro-laag aanvullen",
                "prompt": "Voeg Bitcoin Dominance toe aan macro",
                "handoff": "indicator_config",
                "requires_confirmation": True,
            })
            actions.append({
                "type": "chat_prompt",
                "label": f"{first_asset} technical aanvullen",
                "prompt": f"Voeg RSI toe aan technical voor {first_asset} met standaard scoring weight 1",
                "handoff": "indicator_config",
                "requires_confirmation": True,
            })
        if asset_analyses:
            actions.append({
                "type": "confirmable_action_prompt",
                "label": "Daily scores verversen",
                "prompt": "Ververs daily scores",
                "handoff": "daily_score_refresh",
                "requires_confirmation": True,
            })
            actions.append({
                "type": "chat_prompt",
                "label": "Macro blocker uitleg",
                "prompt": f"Waarom blokkeert macro mijn {first_asset} setup?",
                "handoff": "indicator_insight",
                "requires_confirmation": False,
            })
            actions.append({
                "type": "chat_prompt",
                "label": "Portfolio-risico bekijken",
                "prompt": "Waar zit mijn grootste portfolio risico?",
                "handoff": "daily_coach",
                "requires_confirmation": False,
            })
            top_ignore = (portfolio_risk.get("ignore_today_assets") or [None])[0]
            if top_ignore and top_ignore.get("asset"):
                actions.append({
                    "type": "chat_prompt",
                    "label": "Assets vandaag laten liggen",
                    "prompt": "Welke assets moet ik vandaag negeren?",
                    "handoff": "daily_coach",
                    "requires_confirmation": False,
                })
            top_live_hotspot = (portfolio_risk.get("live_bot_hotspots") or [None])[0]
            if top_live_hotspot and top_live_hotspot.get("asset"):
                actions.append({
                    "type": "chat_prompt",
                    "label": "Live bots reviewen",
                    "prompt": f"Welke live bots vragen vandaag review voor {top_live_hotspot.get('asset')}?",
                    "handoff": "daily_coach",
                    "requires_confirmation": False,
                })
            top_conflict = (portfolio_risk.get("ranked_conflicts") or [None])[0]
            if top_conflict and top_conflict.get("asset"):
                actions.append({
                    "type": "chat_prompt",
                    "label": "Portfolio-conflict uitleg",
                    "prompt": f"Welke bots en plannen stapelen risico voor {top_conflict.get('asset')}?",
                    "handoff": "daily_coach",
                    "requires_confirmation": False,
                })
            actions.append({
                "type": "confirmable_action_prompt",
                "label": "Bot-decision maken",
                "prompt": f"Maak bot-decision voor {first_asset}",
                "handoff": "bot_decision",
                "requires_confirmation": True,
            })
        return actions[:8]

    async def build_mission_control_response(
        self,
        user_id: int,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        daily = await self.build_portfolio_daily_coach_response(
            user_id,
            "Geef mijn daily brief",
            {
                **(context or {"page": "mission_control"}),
                "mission_control_fast": True,
            },
        )
        analysis = (daily.get("state") or {}).get("analysis") or {}
        mission = self._build_mission_control_from_daily_analysis(analysis)
        activity_window = await self._get_recent_finn_activity(user_id, limit=180)
        activity_feed = activity_window[:40]
        day_log = self._mission_day_log(activity_window)
        resolved_item_ids = await self._get_today_resolved_mission_item_ids(user_id)
        if resolved_item_ids:
            mission = self._filter_resolved_mission_items(mission, resolved_item_ids)
        mission["summary"] = {
            **mission["summary"],
            "handled_today_count": day_log["handled_count"],
            "skipped_today_count": day_log["skipped_count"],
            "snoozed_today_count": day_log["snoozed_count"],
        }
        behavioral_insight = self._build_behavioral_insight_from_activity(activity_feed, day_log)
        memory: Dict[str, Any] = {}
        if behavioral_insight.get("behavioral_balance_score") is None:
            extended_behavioral = self._build_behavioral_insight_from_activity(activity_window, day_log)
            memory = self._build_behavioral_memory_report(activity_window, extended_behavioral)
            behavioral_insight["behavioral_balance_score"] = memory.get("behavioral_balance_score")
            if not behavioral_insight.get("habit_cards"):
                behavioral_insight["habit_cards"] = memory.get("habit_cards") or []
            if not behavioral_insight.get("risk_flags"):
                behavioral_insight["risk_flags"] = memory.get("risk_flags") or []
            if not behavioral_insight.get("trend"):
                behavioral_insight["trend"] = memory.get("trend") or {}
            if not (behavioral_insight.get("behavioral_profile") or {}).get("type"):
                behavioral_insight["behavioral_profile"] = memory.get("behavioral_profile") or {}
        governance_events = await self._fetch_recent_governance_events(
            user_id,
            event_types=[
                "finn_decision_review",
                "finn_plan_adherence_review",
                "finn_outcome_tracking_summary",
                "finn_outcome_memory_summary",
                "finn_personal_performance_summary",
                "finn_trade_journal_intelligence_summary",
                "finn_portfolio_intelligence",
                "finn_priority_engine_summary",
                "finn_memory_v2_summary",
            ],
            limit=80,
        )
        agent_verdicts = self._merge_mission_agent_verdicts(
            analysis.get("agent_verdicts") or mission.get("agent_verdicts") or [],
            behavioral_insight,
        )
        agent_controller = self._build_agent_controller(agent_verdicts, context="mission_control")
        mission = self._apply_agent_controller_to_mission(mission, agent_controller, activity_feed=activity_feed)
        coaching_loop = self._build_mission_coaching_loop(mission, analysis, behavioral_insight)
        mission["coaching_loop"] = coaching_loop
        priority_engine = self._priority_engine_payload(
            mission,
            analysis,
            self._priority_engine_governance_signals(governance_events),
        )
        memory_v2 = self._build_memory_v2_summary(activity_window, governance_events)
        personal_performance = self._build_personal_performance_summary(activity_window, governance_events, behavioral_insight)
        trade_journal_intelligence = self._build_trade_journal_intelligence_summary(activity_window, governance_events)
        portfolio_operating_system = self._portfolio_operating_system_contract(
            daily_analysis=analysis,
            mission=mission,
            priority_engine=priority_engine,
            memory={**(memory or {}), **memory_v2},
            personal_performance=personal_performance,
            trade_journal_intelligence=trade_journal_intelligence,
            governance_events=governance_events,
        )
        personal_coach = self._build_personal_coach_summary(
            query="Open Mission Control",
            outcome_memory=self._build_outcome_memory_summary(governance_events, activity_window),
            personal_performance=personal_performance,
            trade_journal_intelligence=trade_journal_intelligence,
            portfolio_operating_system=portfolio_operating_system,
        )
        governance_events_summary = {
            "decision_review_count": len([event for event in governance_events if str(event.get("type") or "") == "finn_decision_review"]),
            "plan_adherence_count": len([event for event in governance_events if str(event.get("type") or "") == "finn_plan_adherence_review"]),
            "outcome_tracking_count": len([event for event in governance_events if str(event.get("type") or "") == "finn_outcome_tracking_summary"]),
            "outcome_memory_count": len([event for event in governance_events if str(event.get("type") or "") == "finn_outcome_memory_summary"]),
            "personal_performance_count": len([event for event in governance_events if str(event.get("type") or "") == "finn_personal_performance_summary"]),
            "personal_coach_count": len([event for event in governance_events if str(event.get("type") or "") == "finn_personal_coach_summary"]),
            "trade_journal_intelligence_count": len([event for event in governance_events if str(event.get("type") or "") == "finn_trade_journal_intelligence_summary"]),
            "portfolio_intelligence_count": len([event for event in governance_events if str(event.get("type") or "") == "finn_portfolio_intelligence"]),
            "priority_engine_count": len([event for event in governance_events if str(event.get("type") or "") == "finn_priority_engine_summary"]),
            "memory_v2_count": len([event for event in governance_events if str(event.get("type") or "") == "finn_memory_v2_summary"]),
        }
        mission["summary"] = {
            **(mission.get("summary") or {}),
            "daily_priority_count": len(coaching_loop.get("daily_priority_stack") or []),
            "act_now_count": len(coaching_loop.get("act_now") or []),
            "monitor_only_count": len(coaching_loop.get("monitor_only") or []),
            "suppressed_count": len(coaching_loop.get("suppressed_items") or []),
            "coaching_loop_status": coaching_loop.get("status"),
        }
        return {
            "ok": True,
            "intent": "mission_control",
            "flow": "mission_control",
            "autonomy_level": "advice_only",
            "summary": mission["summary"],
            "workqueue": mission["workqueue"],
            "workqueue_groups": mission["workqueue_groups"],
            "workqueue_labels": mission["workqueue_labels"],
            "open_actions": mission["open_actions"],
            "plan_health": mission["plan_health"],
            "bot_review_queue": mission["bot_review_queue"],
            "activity_feed": activity_feed,
            "day_log": day_log,
            "behavioral_insight": behavioral_insight,
            "behavioral_profile": behavioral_insight.get("behavioral_profile") or {},
            "trend": behavioral_insight.get("trend") or {},
            "risk_flags": behavioral_insight.get("risk_flags") or [],
            "habit_cards": behavioral_insight.get("habit_cards") or [],
            "behavioral_balance_score": behavioral_insight.get("behavioral_balance_score"),
            "agent_verdicts": agent_verdicts,
            "agent_controller": mission.get("agent_controller") or agent_controller,
            "agent_accountability": mission.get("agent_accountability") or {},
            "agent_learning": mission.get("agent_learning") or {},
            "agent_rhythm": mission.get("agent_rhythm") or {},
            "operating_rules": mission.get("operating_rules") or {},
            "coaching_loop": coaching_loop,
            "priority_engine": priority_engine,
            "memory_v2": memory_v2,
            "personal_performance": personal_performance,
            "personal_coach": personal_coach,
            "trade_journal_intelligence": trade_journal_intelligence,
            "portfolio_operating_system": portfolio_operating_system,
            "governance_events_summary": governance_events_summary,
            "data_readiness": analysis.get("data_readiness") or {},
            "portfolio_risk": mission.get("portfolio_risk") or analysis.get("portfolio_risk") or {},
            "analysis": {
                "mode": "read_only",
                "route_source": "finn",
                "priority_engine": priority_engine,
                "memory_v2": memory_v2,
                "personal_performance": personal_performance,
                "personal_coach": personal_coach,
                "trade_journal_intelligence": trade_journal_intelligence,
                "portfolio_operating_system": portfolio_operating_system,
                "governance_events_summary": governance_events_summary,
                "context_confidence": {
                    "level": "high",
                    "entity_type": "mission_control",
                    "entity_id": "mission_control",
                    "reason": "mission control response built directly from deterministic Finn analysis",
                    "why": "mission control response built directly from deterministic Finn analysis",
                },
            },
            "source": {
                "flow": "daily_coach",
                "date": analysis.get("date"),
                "asset_count": analysis.get("asset_count", 0),
            },
        }

    def _merge_mission_agent_verdicts(
        self,
        agent_verdicts: List[Dict[str, Any]],
        behavioral_insight: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        verdicts = list(agent_verdicts or [])
        metrics = behavioral_insight.get("metrics") or {}
        patterns = behavioral_insight.get("patterns") or []
        verdicts.append({
            "agent": "memory_agent",
            "label": "Memory Agent",
            "status": behavioral_insight.get("status") or "unknown",
            "priority": "medium" if behavioral_insight.get("status") == "attention" else "low",
            "reason": (
                "Behavioral memory ziet aandachtspunten."
                if behavioral_insight.get("status") == "attention" else
                "Nog geen zwaar gedragssignaal uit Finn-activiteit."
            ),
            "evidence": {
                "patterns": patterns,
                "possible_overrides_today": metrics.get("possible_overrides_today", 0),
                "decision_churn_events_today": metrics.get("decision_churn_events_today", 0),
            },
            "next_action": "Gebruik extra frictie bij nieuwe decisions." if behavioral_insight.get("status") == "attention" else "Blijf Mission Control gebruiken als auditbron.",
        })
        return verdicts

    def _agent_verdict_score(self, verdict: Dict[str, Any]) -> int:
        priority = str(verdict.get("priority") or "").lower()
        status = str(verdict.get("status") or "").lower()
        score = {
            "critical": 100,
            "high": 80,
            "medium": 50,
            "low": 20,
        }.get(priority, 35)
        if any(token in status for token in ["block", "intervened", "high_attention", "attention", "stale"]):
            score += 25
        elif any(token in status for token in ["need", "missing", "review", "waiting"]):
            score += 12
        elif status in {"clear", "quiet", "ready", "no_open_decision", "no_decision"}:
            score -= 8
        evidence = verdict.get("evidence") or {}
        if isinstance(evidence, dict):
            for key in ["conflict_count", "risk_stack_count", "decision_count", "blocked_assets", "blocker_count"]:
                try:
                    score += min(int(evidence.get(key) or 0), 5) * 3
                except (TypeError, ValueError):
                    continue
        return int(max(0, min(120, score)))

    def _build_agent_controller(
        self,
        agent_verdicts: List[Dict[str, Any]],
        *,
        context: str,
    ) -> Dict[str, Any]:
        ranked = []
        for index, verdict in enumerate(agent_verdicts or []):
            if not isinstance(verdict, dict):
                continue
            item = {**verdict}
            item["controller_score"] = self._agent_verdict_score(item)
            item["_input_order"] = index
            ranked.append(item)
        ranked.sort(key=lambda item: (-item.get("controller_score", 0), item.get("_input_order", 99)))
        for rank, item in enumerate(ranked, start=1):
            item["controller_rank"] = rank
            item.pop("_input_order", None)

        dominant = ranked[0] if ranked else None
        score = int((dominant or {}).get("controller_score") or 0)
        if score >= 90:
            status = "intervene_first"
        elif score >= 65:
            status = "review_first"
        elif score >= 40:
            status = "monitor"
        else:
            status = "stable"

        dominant_agent = (dominant or {}).get("agent")
        return {
            "context": context,
            "status": status,
            "dominant_agent": dominant_agent,
            "dominant_label": (dominant or {}).get("label"),
            "dominant_status": (dominant or {}).get("status"),
            "dominant_priority": (dominant or {}).get("priority"),
            "dominant_score": score,
            "reason": (dominant or {}).get("reason") or "Geen dominante agent gevonden.",
            "next_action": (dominant or {}).get("next_action"),
            "ranked_verdicts": ranked[:6],
            "policy": {
                "source": "deterministic_agent_verdict_scoring",
                "advice_only": True,
                "uses_llm": False,
            },
        }

    def _agent_handoff_preferences(self, agent: Optional[str]) -> List[str]:
        return {
            "risk_agent": ["daily_coach", "indicator_insight", "daily_score_refresh", "bot_decision_review"],
            "macro_agent": ["indicator_insight", "indicator_config", "daily_score_refresh"],
            "technical_agent": ["indicator_insight", "indicator_config", "daily_score_refresh"],
            "market_agent": ["indicator_insight", "daily_score_refresh", "indicator_config"],
            "strategy_agent": ["bot_decision", "indicator_insight"],
            "execution_agent": ["bot_decision_review", "bot_decision", "daily_score_refresh"],
            "memory_agent": ["behavioral_memory", "weekly_reflection", "bot_decision_review"],
        }.get(agent or "", ["daily_coach", "indicator_insight", "daily_score_refresh", "bot_decision"])

    def _agent_controller_primary_action(
        self,
        controller: Dict[str, Any],
        actions: List[Dict[str, Any]],
        *,
        asset: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        preferences = self._agent_handoff_preferences(controller.get("dominant_agent"))
        candidates = [action for action in actions or [] if isinstance(action, dict)]
        for handoff in preferences:
            match = next((action for action in candidates if action.get("handoff") == handoff), None)
            if match:
                return {
                    **match,
                    "source": "agent_controller",
                    "dominant_agent": controller.get("dominant_agent"),
                    "controller_status": controller.get("status"),
                }
        if candidates:
            return {
                **candidates[0],
                "source": "agent_controller",
                "dominant_agent": controller.get("dominant_agent"),
                "controller_status": controller.get("status"),
            }

        symbol = asset or "BTC"
        agent = controller.get("dominant_agent")
        if agent == "execution_agent":
            label = "Maak bot-decision"
            prompt = f"Maak bot-decision voor {symbol}"
            handoff = "bot_decision"
            requires_confirmation = True
        elif agent == "memory_agent":
            label = "Gedragsrapport bekijken"
            prompt = "Geef mijn gedragsrapport van de laatste 30 dagen"
            handoff = "behavioral_memory"
            requires_confirmation = False
        elif agent in {"macro_agent", "technical_agent", "market_agent"}:
            category = (agent or "macro_agent").replace("_agent", "")
            label = f"{category.capitalize()} uitleg"
            prompt = f"Waarom blokkeert {category} mijn {symbol} setup?"
            handoff = "indicator_insight"
            requires_confirmation = False
        else:
            label = "Portfolio-risico bekijken" if not asset else "Planstatus bekijken"
            prompt = "Waar zit mijn grootste portfolio risico?" if not asset else f"Waarom is mijn {symbol} setup inactief?"
            handoff = "daily_coach" if not asset else "plan_status"
            requires_confirmation = False

        return {
            "type": "chat_prompt",
            "label": label,
            "prompt": prompt,
            "handoff": handoff,
            "requires_confirmation": requires_confirmation,
            "source": "agent_controller",
            "dominant_agent": agent,
            "controller_status": controller.get("status"),
            "asset": asset,
        }

    def _build_agent_accountability_summary(
        self,
        controller: Dict[str, Any],
        workqueue: List[Dict[str, Any]],
        activity_feed: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        dominant_agent = controller.get("dominant_agent")
        primary_action = controller.get("primary_action") or {}
        influenced_items = [
            {
                "id": item.get("id"),
                "type": item.get("type"),
                "asset": item.get("asset"),
                "title": item.get("title"),
                "controller_rank_boost": item.get("controller_rank_boost"),
                "reason": item.get("controller_reason") or item.get("reason"),
            }
            for item in workqueue or []
            if item.get("dominant_agent") == dominant_agent or item.get("controller_rank_boost")
        ]
        followed = []
        skipped = []
        monitored = []
        for item in activity_feed or []:
            accountability = item.get("agent_accountability") or {}
            if accountability.get("dominant_agent") != dominant_agent:
                continue
            state = item.get("resolve_state")
            if state == "resolved":
                followed.append(item)
            elif state == "skipped":
                skipped.append(item)
            elif state in {"monitor_today", "snoozed", "waiting_for_data"}:
                monitored.append(item)
        return {
            "dominant_agent": dominant_agent,
            "dominant_label": controller.get("dominant_label"),
            "controller_status": controller.get("status"),
            "controller_score": controller.get("dominant_score"),
            "primary_action": primary_action,
            "primary_item_id": controller.get("primary_item_id"),
            "influenced_items": influenced_items[:5],
            "followed_count": len(followed),
            "skipped_count": len(skipped),
            "monitored_count": len(monitored),
            "performance_light": self._agent_performance_light(activity_feed),
            "policy": {
                "source": "agent_controller",
                "audit_only": True,
                "uses_pnl": False,
                "does_not_execute": True,
            },
        }

    def _agent_performance_light(self, activity_feed: List[Dict[str, Any]]) -> Dict[str, Any]:
        stats: Dict[str, Dict[str, Any]] = {}
        for item in activity_feed or []:
            accountability = item.get("agent_accountability") or {}
            agent = accountability.get("dominant_agent")
            if not agent:
                continue
            label = accountability.get("dominant_label") or agent
            entry = stats.setdefault(agent, {
                "agent": agent,
                "label": label,
                "handoffs": 0,
                "followed": 0,
                "skipped": 0,
                "monitored": 0,
                "last_action": accountability.get("primary_action_label"),
            })
            entry["handoffs"] += 1
            entry["last_action"] = accountability.get("primary_action_label") or entry.get("last_action")
            state = item.get("resolve_state")
            if state == "resolved":
                entry["followed"] += 1
            elif state == "skipped":
                entry["skipped"] += 1
            elif state in {"monitor_today", "snoozed", "waiting_for_data"}:
                entry["monitored"] += 1
        ranked = sorted(stats.values(), key=lambda value: (-value.get("handoffs", 0), value.get("agent", "")))
        top = ranked[0] if ranked else None
        if top:
            summary = (
                f"{top.get('label')} gaf het vaakst de doorslag: "
                f"{top.get('handoffs')} handoff(s), {top.get('followed')} gevolgd."
            )
        else:
            summary = "Nog geen agent-handoff historie om patronen uit af te leiden."
        return {
            "status": "ready" if ranked else "not_enough_data",
            "summary": summary,
            "agents": ranked[:6],
            "policy": {
                "source": "agent_controller_handoff_audit",
                "uses_pnl": False,
                "claims_performance": False,
            },
        }

    def _agent_rhythm_from_learning(self, agent_learning: Dict[str, Any]) -> Dict[str, Any]:
        agents = agent_learning.get("agents") or []
        policy = {
            "source": "agent_learning_light",
            "uses_pnl": False,
            "claims_performance": False,
            "advice_only": True,
        }
        if not agents:
            return {
                "status": "not_enough_data",
                "summary": "Nog geen agent-ritme zichtbaar; volg of handel eerst een paar controller-acties af.",
                "followed_patterns": [],
                "friction_patterns": [],
                "tomorrow_focus": [],
                "policy": policy,
            }

        followed_patterns = []
        friction_patterns = []
        for agent in agents:
            label = agent.get("label") or agent.get("agent")
            handoffs = int(agent.get("handoffs") or 0)
            followed = int(agent.get("followed") or 0)
            skipped = int(agent.get("skipped") or 0)
            monitored = int(agent.get("monitored") or 0)
            if followed:
                followed_patterns.append(f"Je volgde {label} {followed} van {handoffs} keer.")
            if skipped or monitored:
                parts = []
                if skipped:
                    parts.append(f"{skipped} overgeslagen")
                if monitored:
                    parts.append(f"{monitored} gemonitord/later gezet")
                friction_patterns.append(f"{label}: {', '.join(parts)}.")

        top = agents[0]
        summary = (
            f"Je operator-ritme wordt nu vooral gestuurd door {top.get('label') or top.get('agent')} "
            f"({top.get('handoffs', 0)} handoff(s))."
        )
        tomorrow_focus = []
        if friction_patterns:
            tomorrow_focus.append("Review eerst agent-adviezen die je hebt gesnoozed, gemonitord of overgeslagen.")
        else:
            tomorrow_focus.append("Start morgen opnieuw vanuit de dominante agent en werk Mission Control van boven naar beneden af.")
        return {
            "status": "ready",
            "summary": summary,
            "followed_patterns": followed_patterns[:4],
            "friction_patterns": friction_patterns[:4],
            "tomorrow_focus": tomorrow_focus,
            "policy": policy,
        }

    def _personal_operating_rules(
        self,
        agent_rhythm: Dict[str, Any],
        metrics: Optional[Dict[str, Any]] = None,
        interventions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        metrics = metrics or {}
        intervention_types = {item.get("type") for item in (interventions or []) if isinstance(item, dict)}
        rules: List[Dict[str, Any]] = []

        def add_rule(rule_id: str, title: str, trigger: str, rule: str, evidence: Dict[str, Any]):
            if any(existing.get("id") == rule_id for existing in rules):
                return
            rules.append({
                "id": rule_id,
                "title": title,
                "trigger": trigger,
                "rule": rule,
                "mode": "coaching_only",
                "source": "finn_operator_audit",
                "evidence": evidence,
            })

        summary = agent_rhythm.get("summary") or ""
        rhythm_text = " ".join(
            [summary]
            + (agent_rhythm.get("followed_patterns") or [])
            + (agent_rhythm.get("friction_patterns") or [])
        )
        if "Risk Agent" in rhythm_text:
            add_rule(
                "risk_agent_first",
                "Risk Agent eerst",
                "Risk Agent stuurt je werkvolgorde.",
                "Los eerst het bovenste Mission Control risico-item op voordat je nieuwe decisions of execution start.",
                {"agent_rhythm": summary},
            )
        if "Execution Agent" in rhythm_text or metrics.get("execution_pressure_events") or metrics.get("live_order_blocks") or "execution_pressure" in intervention_types:
            add_rule(
                "execution_friction_preflight_first",
                "Execution-frictie betekent eerst preflight",
                "Execution Agent of live guardrails remmen af.",
                "Start geen live/manual order zonder verse preflight, idempotency en expliciete risk acknowledgement.",
                {
                    "execution_pressure_events": metrics.get("execution_pressure_events", 0),
                    "live_order_blocks": metrics.get("live_order_blocks", 0),
                },
            )
        if metrics.get("decision_churn_events") or metrics.get("decision_churn_events_7d") or "decision_churn" in intervention_types:
            add_rule(
                "review_before_new_decision",
                "Eerst review, dan pas nieuwe decision",
                "Decision-churn is geregistreerd.",
                "Maak geen nieuwe bot-decision voordat open reviews zijn afgehandeld, geskipt of bewust gemonitord.",
                {
                    "decision_churn_events": metrics.get("decision_churn_events", metrics.get("decision_churn_events_7d", 0)),
                },
            )
        if metrics.get("plan_deviation_events") or metrics.get("plan_deviation_events_7d") or "plan_deviation" in intervention_types:
            add_rule(
                "deviation_requires_plan_check",
                "Plan-afwijking vraagt setup-check",
                "Je week of dag bevatte een bewuste plan-afwijking.",
                "Check eerst setupstatus en blockers; ga alleen verder na bewuste override als je nog steeds achter de afwijking staat.",
                {
                    "plan_deviation_events": metrics.get("plan_deviation_events", metrics.get("plan_deviation_events_7d", 0)),
                },
            )
        if metrics.get("snoozed") or metrics.get("monitor_today") or metrics.get("skipped") or metrics.get("snoozed_7d") or metrics.get("monitor_7d") or metrics.get("skipped_7d"):
            add_rule(
                "carryover_before_new_work",
                "Carry-over eerst",
                "Je hebt items gesnoozed, gemonitord of overgeslagen.",
                "Begin de volgende sessie met carry-over items voordat je nieuwe flows start.",
                {
                    "skipped": metrics.get("skipped", metrics.get("skipped_7d", 0)),
                    "snoozed": metrics.get("snoozed", metrics.get("snoozed_7d", 0)),
                    "monitor": metrics.get("monitor_today", metrics.get("monitor_7d", 0)),
                },
            )

        status = "ready" if rules else "not_enough_data"
        return {
            "status": status,
            "summary": (
                f"{len(rules)} persoonlijke operator-regel(s) afgeleid uit Finn-auditdata."
                if rules else
                "Nog geen persoonlijke operator-regels afgeleid; er is meer gevolgd/afgehandeld gedrag nodig."
            ),
            "rules": rules[:6],
            "policy": {
                "source": "ai_pending_actions_and_agent_rhythm",
                "stores_new_preferences": False,
                "coaching_only": True,
                "uses_pnl": False,
                "claims_performance": False,
            },
        }

    def _mission_item_matches_agent(self, item: Dict[str, Any], agent: Optional[str]) -> bool:
        if not agent:
            return False
        item_type = str(item.get("type") or "")
        haystack = " ".join([
            str(item.get("title") or ""),
            str(item.get("reason") or ""),
            str(((item.get("next_best_action") or {}).get("label")) or ""),
            str(((item.get("next_best_action") or {}).get("prompt")) or ""),
        ]).lower()
        if agent == "execution_agent":
            return item_type in {"bot_decision", "bot_decision_request", "score_refresh"}
        if agent == "risk_agent":
            return item_type in {"portfolio_risk_stack", "blocked_plan", "data_gap"} or "risk" in haystack or "blokkeert" in haystack
        if agent == "macro_agent":
            return item_type in {"indicator_gap", "blocker_explanation", "blocked_plan"} and "macro" in haystack
        if agent == "technical_agent":
            return item_type in {"indicator_gap", "blocker_explanation", "blocked_plan"} and ("technical" in haystack or "technisch" in haystack)
        if agent == "market_agent":
            return item_type in {"indicator_gap", "blocker_explanation", "blocked_plan", "data_gap"} and "market" in haystack
        if agent == "strategy_agent":
            return item_type in {"blocked_plan", "portfolio_risk_stack"} or "strategie" in haystack or "strategy" in haystack
        if agent == "memory_agent":
            return item_type in {"bot_decision", "bot_decision_request"} or "decision" in haystack
        return False

    def _apply_agent_controller_to_mission(
        self,
        mission: Dict[str, Any],
        controller: Dict[str, Any],
        *,
        activity_feed: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        dominant_agent = controller.get("dominant_agent")
        if not dominant_agent:
            return mission
        dominant_score = int(controller.get("dominant_score") or 0)
        boost = 30 if dominant_score >= 90 else 18 if dominant_score >= 65 else 8
        workqueue = []
        for item in mission.get("workqueue") or []:
            updated = {**item}
            if self._mission_item_matches_agent(updated, dominant_agent):
                original_rank = int(updated.get("priority_rank") or updated.get("sort_rank") or 99)
                updated["controller_rank_boost"] = boost
                updated["controller_reason"] = controller.get("reason")
                updated["dominant_agent"] = dominant_agent
                updated["priority_rank"] = max(1, original_rank - boost)
                updated["sort_rank"] = updated["priority_rank"]
            workqueue.append(updated)
        workqueue = self._dedupe_workqueue(workqueue)[:10]
        workqueue_groups = self._mission_workqueue_groups(workqueue)
        primary_item = next((item for item in workqueue if item.get("controller_rank_boost")), None) or (workqueue[0] if workqueue else None)
        primary_action = (primary_item or {}).get("next_best_action") if primary_item else None
        controller = {
            **controller,
            "primary_action": self._agent_controller_primary_action(
                controller,
                [primary_action] if isinstance(primary_action, dict) else [],
                asset=(primary_item or {}).get("asset") if primary_item else None,
            ),
            "primary_item_id": (primary_item or {}).get("id"),
        }
        mission = {
            **mission,
            "workqueue": self._flatten_mission_workqueue_groups(workqueue_groups),
            "workqueue_groups": workqueue_groups,
            "agent_controller": controller,
        }
        mission["summary"] = {
            **(mission.get("summary") or {}),
            "controller_status": controller.get("status"),
            "dominant_agent": dominant_agent,
            "dominant_agent_score": dominant_score,
            "workqueue_count": len(mission["workqueue"]),
        }
        mission["agent_accountability"] = self._build_agent_accountability_summary(
            controller,
            mission["workqueue"],
            activity_feed or [],
        )
        mission["agent_learning"] = mission["agent_accountability"].get("performance_light") or {}
        mission["agent_rhythm"] = self._agent_rhythm_from_learning(mission["agent_learning"])
        mission["operating_rules"] = self._personal_operating_rules(mission["agent_rhythm"])
        return mission

    async def build_behavioral_intelligence_response(
        self,
        user_id: int,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        activity_feed = await self._get_recent_finn_activity(user_id, limit=50)
        day_log = self._mission_day_log(activity_feed)
        insight = self._build_behavioral_insight_from_activity(activity_feed, day_log)
        coaching = insight.get("coaching") or {}
        risk_flags = insight.get("risk_flags") or []
        primary_flag = risk_flags[0] if risk_flags else {}
        q = self._normalized_query(query)
        variant = self._behavioral_variant_for_query(query)
        overtrading_terms = tuple(OVERTRADING_DIRECT_COACH_TERMS)
        insight["variant"] = variant
        insight["risk_signal"] = primary_flag.get("id") or ("plan_deviation" if variant == "plan_adherence_coach" else "acute_emotion" if variant == "direct_coach" else insight.get("status"))
        insight["what_i_notice"] = coaching.get("primary_reflection") or insight.get("trend", {}).get("summary")
        insight["why_this_is_risky"] = primary_flag.get("summary") or "Emotionele of impulsieve druk maakt het makkelijker om je plan te verlaten."
        insight["what_to_do_now"] = coaching.get("safe_next_step") or "Neem even afstand, check je planstatus en handel pas weer als je setup echt klopt."
        insight["what_not_to_do"] = coaching.get("do_not_do") or "Ga nu niet forceren, opschalen of all-in."
        if variant == "plan_adherence_coach":
            insight["what_i_notice"] = "Ik zie dat je je plan of strategie dreigt te overrulen voordat je setup opnieuw is gevalideerd."
            insight["why_this_is_risky"] = primary_flag.get("summary") or "Zodra je buiten je plan beweegt, laat je regels hun remmende werk los en neemt emotie sneller over."
            insight["what_to_do_now"] = coaching.get("safe_next_step") or "Leg je plan er letterlijk naast en check eerst of je setup, risico en trigger nog echt geldig zijn."
            insight["what_not_to_do"] = coaching.get("do_not_do") or "Ga nu niet improviseren, opschalen of toch instappen voordat je plan opnieuw hard klopt."
        elif variant == "direct_coach" and any(term in q for term in overtrading_terms):
            insight["what_i_notice"] = "Ik zie actie-drang en herhalingsdruk die je richting overtrading trekt."
            risk_summary = primary_flag.get("summary")
            insight["why_this_is_risky"] = (
                f"Overtrading-signaal: {risk_summary}"
                if risk_summary
                else "Overtrading verschuift je focus van kwaliteit naar activiteit, waardoor je sneller buiten je plan en risicokaders beweegt."
            )
            insight["what_to_do_now"] = coaching.get("safe_next_step") or "Doe nu geen nieuwe trade. Neem eerst een korte cooldown, werk open beslissingen af en wacht alleen op een verse valide trigger."
            insight["what_not_to_do"] = coaching.get("do_not_do") or "Open nu niet nog een trade uit onrust, verveling of de drang om iets terug te verdienen."
        elif variant == "direct_coach" and any(term in q for term in [
            "emotionele beslissing", "geen goed gevoel", "dit voelt niet goed", "ik twijfel", "ik durf niet", "ik ben bang",
            "gefrustreerd", "gemiste move", "ik baal", "ik wil het terugpakken", "ik moet nu iets doen", "ik wil nu handelen omdat",
        ]):
            insight["what_i_notice"] = "Ik zie twijfel of emotionele druk die je oordeel nu vertroebelt."
            insight["why_this_is_risky"] = primary_flag.get("summary") or "Twijfel of emotionele druk leidt vaak tot half-commit, overrides of een trade die je later niet kunt verdedigen."
            insight["what_to_do_now"] = coaching.get("safe_next_step") or "Doe nu geen nieuwe trade. Check eerst je setup-criteria en beslis pas opnieuw als je plan nog steeds hard klopt."
            insight["what_not_to_do"] = coaching.get("do_not_do") or "Ga nu niet uit ongemak toch klikken, middelen of je regels verbuigen."
        if variant == "direct_coach" and any(term in q for term in ["gefrustreerd", "gemiste move", "ik baal", "ik wil het terugpakken", "ik moet nu iets doen", "ik wil nu handelen omdat"]):
            insight["what_i_notice"] = "Ik zie frustratie en actie-drang na een gemiste move."
            insight["why_this_is_risky"] = primary_flag.get("summary") or "Frustratie na een gemiste move trekt je snel in een hersteltrade die niet uit je plan komt."
            insight["what_to_do_now"] = coaching.get("safe_next_step") or "Open nu geen nieuwe trade. Laat de move los, check je setup-criteria opnieuw en wacht op een verse valide trigger."
            insight["what_not_to_do"] = coaching.get("do_not_do") or "Ga nu niets terugpakken, jaag de markt niet na en vergroot je risico niet uit frustratie."
        insight["plan_anchor"] = "Volg eerst je planstatus en guardrails voordat je iets nieuws forceert." if variant in {"direct_coach", "plan_adherence_coach"} else None
        insight["behavioral_intelligence"] = {
            "variant": variant,
            "risk_signal": insight["risk_signal"],
            "what_i_notice": insight["what_i_notice"],
            "why_this_is_risky": insight["why_this_is_risky"],
            "what_to_do_now": insight["what_to_do_now"],
            "what_not_to_do": insight["what_not_to_do"],
            "plan_anchor": insight.get("plan_anchor"),
        }
        response = self._behavioral_intelligence_message(insight)
        return {
            "response": response,
            "intent": "behavioral_intelligence",
            "flow": "behavioral_intelligence",
            "draft": None,
            "missing_fields": [],
            "invalid_fields": [],
            "next_question": None,
            "can_confirm": False,
            "actions": [],
            "state": {
                "current_flow": "behavioral_intelligence",
                "analysis": insight,
                "advice_only": True,
            },
        }

    async def build_weekly_reflection_response(
        self,
        user_id: int,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        activity_feed = await self._get_recent_finn_activity(user_id, limit=100)
        day_log = self._mission_day_log(activity_feed)
        behavioral = self._build_behavioral_insight_from_activity(activity_feed, day_log)
        reflection = self._build_weekly_reflection_from_behavioral(behavioral, activity_feed)
        response = self._weekly_reflection_message(reflection)
        return {
            "response": response,
            "intent": "weekly_reflection",
            "flow": "weekly_reflection",
            "draft": None,
            "missing_fields": [],
            "invalid_fields": [],
            "next_question": None,
            "can_confirm": False,
            "actions": [],
            "state": {
                "current_flow": "weekly_reflection",
                "analysis": reflection,
                "behavioral_insight": behavioral,
                "agent_learning": reflection.get("agent_learning"),
                "agent_rhythm": reflection.get("agent_rhythm"),
                "operating_rules": reflection.get("operating_rules"),
                "advice_only": True,
            },
            "suggested_actions": [
                "Open Mission Control",
                "Vraag: hoe is mijn trading discipline vandaag?",
                "Vraag: wat zijn mijn prioriteiten vandaag?",
            ],
        }

    async def build_behavioral_memory_response(
        self,
        user_id: int,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        activity_feed = await self._get_recent_finn_activity(user_id, limit=180)
        day_log = self._mission_day_log(activity_feed)
        behavioral = self._build_behavioral_insight_from_activity(activity_feed, day_log)
        memory = self._build_behavioral_memory_report(activity_feed, behavioral)
        governance_events = await self._fetch_recent_governance_events(
            user_id,
            event_types=[
                "finn_decision_review",
                "finn_plan_adherence_review",
                "finn_outcome_tracking_summary",
                "finn_portfolio_intelligence",
            ],
            limit=80,
        )
        memory_v2 = self._build_memory_v2_summary(activity_feed, governance_events)
        outcome_memory = self._build_outcome_memory_summary(governance_events, activity_feed)
        personal_performance = self._build_personal_performance_summary(activity_feed, governance_events, behavioral)
        trade_journal_intelligence = self._build_trade_journal_intelligence_summary(activity_feed, governance_events)
        memory = {
            **memory,
            **memory_v2,
            "memory_v2": memory_v2,
            "outcome_memory": outcome_memory,
            "personal_performance": personal_performance,
            "trade_journal_intelligence": trade_journal_intelligence,
        }
        await self._record_governance_event(
            user_id,
            event_type="finn_memory_v2_summary",
            symbol=context.get("symbol") if isinstance(context, dict) else None,
            title="Finn bouwde een Memory V2 samenvatting",
            description=memory_v2.get("behavioral_cost") or memory_v2.get("recommended_rule"),
            severity="info",
            payload={
                "phase": "memory_summary_engine",
                "query": query,
                "memory_pattern": memory_v2.get("memory_pattern"),
                "supporting_evidence_count": memory_v2.get("supporting_evidence_count"),
                "time_window": memory_v2.get("time_window"),
                "behavioral_cost": memory_v2.get("behavioral_cost"),
                "recommended_rule": memory_v2.get("recommended_rule"),
                "confidence_level": memory_v2.get("confidence_level"),
            },
            cooldown_hours=6,
        )
        response = self._behavioral_memory_message(memory)
        return {
            "response": response,
            "intent": "behavioral_memory",
            "flow": "behavioral_memory",
            "draft": None,
            "missing_fields": [],
            "invalid_fields": [],
            "next_question": None,
            "can_confirm": False,
            "actions": [],
            "state": {
                "current_flow": "behavioral_memory",
                "analysis": memory,
                "behavioral_insight": behavioral,
                "outcome_memory": outcome_memory,
                "personal_performance": personal_performance,
                "trade_journal_intelligence": trade_journal_intelligence,
                "advice_only": True,
            },
            "analysis": memory,
            "suggested_actions": [
                "Vraag: geef mijn weekreflectie",
                "Vraag: open Mission Control",
                "Vraag: waar wijk ik vaak af van mijn plan?",
            ],
        }

    def _build_outcome_memory_summary(
        self,
        governance_events: List[Dict[str, Any]],
        activity_feed: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        patterns = {
            "fomo_outcomes": {
                "score": 0,
                "evidence": [],
                "cost": "FOMO-uitkomsten trekken je naar entries die vaker kapitaal lekken dan kwaliteit toevoegen.",
                "rule": "Geen entry op basis van haast of gemiste move zonder nieuwe objectieve trigger.",
                "trigger": "druk om niet achter te blijven op de markt",
            },
            "plan_override_outcomes": {
                "score": 0,
                "evidence": [],
                "cost": "Plan-overrides maken goede reviews minder waard en verlagen je disciplinekwaliteit.",
                "rule": "Geen override zonder expliciete hercheck van trigger, sizing en exposure.",
                "trigger": "de neiging om bestaande regels tijdelijk opzij te schuiven",
            },
            "overtrading_outcomes": {
                "score": 0,
                "evidence": [],
                "cost": "Te vaak opnieuw handelen verhoogt frictie, verlaagt selectiviteit en stapelt slechte follow-through.",
                "rule": "Na een trade of block volgt eerst cooldown en review voordat je opnieuw actie zoekt.",
                "trigger": "de drang om snel weer iets te doen",
            },
            "concentration_outcomes": {
                "score": 0,
                "evidence": [],
                "cost": "Concentratie-uitkomsten stapelen risico in plaats van kwaliteit, ook als losse beslissingen verdedigbaar lijken.",
                "rule": "Voeg geen extra risico toe als dezelfde asset al dominant is in je allocatie.",
                "trigger": "het blijven toevoegen aan dezelfde dominante exposure",
            },
            "recovery_outcomes": {
                "score": 0,
                "evidence": [],
                "cost": "Je beste herstel komt uit vertragen en opnieuw prioriteren, niet uit forceren.",
                "rule": "Gebruik skip, snooze of review als eerste herstelactie zodra druk oploopt.",
                "trigger": "druk na verlies, blokkade of onrust",
            },
        }

        latest_summary = None
        for event in governance_events or []:
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            event_type = str(event.get("type") or "")
            if event_type == "finn_outcome_tracking_summary":
                behavior_pattern = str(payload.get("behavior_pattern") or "")
                net_effect = str(payload.get("net_effect") or "")
                history = str(payload.get("historical_result_summary") or "")
                sample_size = int(payload.get("sample_size") or 0)
                if not latest_summary and history:
                    latest_summary = history
                if behavior_pattern == "fomo_outcomes":
                    patterns["fomo_outcomes"]["score"] += 3 if sample_size >= 3 else 1
                    patterns["fomo_outcomes"]["evidence"].append(history or net_effect or event.get("description"))
                elif behavior_pattern in {"plan_override_outcomes", "plan_adherence_outcomes"}:
                    patterns["plan_override_outcomes"]["score"] += 3 if sample_size >= 2 else 1
                    patterns["plan_override_outcomes"]["evidence"].append(history or net_effect or event.get("description"))
                elif behavior_pattern == "overtrading_outcomes":
                    patterns["overtrading_outcomes"]["score"] += 3 if sample_size >= 2 else 1
                    patterns["overtrading_outcomes"]["evidence"].append(history or net_effect or event.get("description"))
                if any(term in net_effect.lower() for term in ["negatief", "vaker slecht", "kapitaal lekt"]):
                    if behavior_pattern == "fomo_outcomes":
                        patterns["fomo_outcomes"]["score"] += 2
                    elif behavior_pattern in {"plan_override_outcomes", "plan_adherence_outcomes"}:
                        patterns["plan_override_outcomes"]["score"] += 2
                    elif behavior_pattern == "overtrading_outcomes":
                        patterns["overtrading_outcomes"]["score"] += 2
            elif event_type == "finn_plan_adherence_review":
                adherence = str(payload.get("adherence_status") or "")
                if adherence in {"forced_override", "outside_plan"}:
                    patterns["plan_override_outcomes"]["score"] += 2
                    patterns["plan_override_outcomes"]["evidence"].append(
                        payload.get("threatened_rule") or event.get("description")
                    )
            elif event_type == "finn_portfolio_intelligence":
                portfolio_status = str(payload.get("portfolio_status") or "")
                if portfolio_status in {"concentrated", "high_attention"}:
                    patterns["concentration_outcomes"]["score"] += 2
                    patterns["concentration_outcomes"]["evidence"].append(
                        payload.get("concentration_warning")
                        or payload.get("stacked_risk_warning")
                        or event.get("description")
                    )

        skipped = len([item for item in activity_feed or [] if str(item.get("resolve_state") or "") == "skipped"])
        snoozed = len([item for item in activity_feed or [] if str(item.get("resolve_state") or "") == "snoozed"])
        if skipped + snoozed >= 3:
            patterns["recovery_outcomes"]["score"] += 2
            patterns["recovery_outcomes"]["evidence"].append(
                f"{skipped} skips en {snoozed} snoozes laten zien dat vertragen je vaak beter beschermt dan doorzetten."
            )

        primary_pattern, primary_data = max(
            patterns.items(),
            key=lambda item: (item[1]["score"], len(item[1]["evidence"])),
        )
        evidence = [str(item) for item in (primary_data.get("evidence") or []) if item]
        evidence = list(dict.fromkeys(evidence))[:4]
        evidence_count = len(evidence)
        if primary_data.get("score", 0) >= 6 and evidence_count >= 2:
            confidence = "high"
        elif primary_data.get("score", 0) >= 3 and evidence_count >= 1:
            confidence = "medium"
        else:
            confidence = "low"

        if confidence == "low":
            primary_pattern = "insufficient_outcome_memory"
            behavioral_cost = "Ik zie nog losse uitkomstsignalen, maar nog niet genoeg om een vaste uitkomstregel te onthouden."
            recommended_rule = "Blijf reviews, adherence-checks en uitkomstvragen via Finn laten lopen zodat deze memory-laag rijker wordt."
            repeat_trigger = "nog niet sterk genoeg af te leiden"
        else:
            behavioral_cost = str(primary_data.get("cost") or "")
            recommended_rule = str(primary_data.get("rule") or "")
            repeat_trigger = str(primary_data.get("trigger") or "")

        operator_next_step = (
            "Gebruik dit patroon als pre-trade rem: herken de trigger eerder en laat Finn eerst reviewen voordat je iets toevoegt."
            if confidence in {"medium", "high"} else
            "Verzamel eerst meer echte review-, adherence- en uitkomstsignalen voordat Finn hier een hardere regel van maakt."
        )
        return {
            "memory_pattern": primary_pattern,
            "supporting_evidence_count": evidence_count,
            "time_window": "last_90_days",
            "behavioral_cost": behavioral_cost,
            "repeat_trigger": repeat_trigger,
            "recommended_rule": recommended_rule,
            "confidence_level": confidence,
            "supporting_evidence": evidence,
            "latest_outcome_summary": latest_summary,
            "operator_next_step": operator_next_step,
        }

    async def build_outcome_memory_response(
        self,
        user_id: int,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = context or {}
        activity_feed = await self._get_recent_finn_activity(user_id, limit=180)
        governance_events = await self._fetch_recent_governance_events(
            user_id,
            event_types=[
                "finn_outcome_tracking_summary",
                "finn_plan_adherence_review",
                "finn_portfolio_intelligence",
            ],
            limit=80,
        )
        analysis = self._build_outcome_memory_summary(activity_feed=activity_feed, governance_events=governance_events)
        analysis["headline"] = "Ik kijk nu welk uitkomstpatroon Finn echt van je gedrag mag onthouden."
        await self._record_governance_event(
            user_id,
            event_type="finn_outcome_memory_summary",
            symbol=context.get("symbol") if isinstance(context, dict) else None,
            title="Finn bouwde een Outcome Memory samenvatting",
            description=analysis.get("behavioral_cost") or analysis.get("recommended_rule"),
            severity="info",
            payload={
                "phase": "outcome_memory_engine",
                "query": query,
                "memory_pattern": analysis.get("memory_pattern"),
                "supporting_evidence_count": analysis.get("supporting_evidence_count"),
                "time_window": analysis.get("time_window"),
                "behavioral_cost": analysis.get("behavioral_cost"),
                "repeat_trigger": analysis.get("repeat_trigger"),
                "recommended_rule": analysis.get("recommended_rule"),
                "confidence_level": analysis.get("confidence_level"),
            },
            cooldown_hours=6,
        )
        return {
            "response": self._outcome_memory_message(analysis),
            "intent": "outcome_memory",
            "flow": "outcome_memory",
            "draft": None,
            "missing_fields": [],
            "invalid_fields": [],
            "next_question": None,
            "can_confirm": False,
            "actions": [],
            "state": {
                "current_flow": "outcome_memory",
                "analysis": analysis,
                "advice_only": True,
            },
            "analysis": analysis,
            "suggested_actions": [
                "Vraag: welk gedrag kost me de laatste maand het meeste?",
                "Vraag: wat onthoudt Finn van mijn laatste fouten?",
                "Vraag: open Mission Control",
            ],
        }

    def _build_personal_performance_summary(
        self,
        activity_feed: List[Dict[str, Any]],
        governance_events: List[Dict[str, Any]],
        behavioral: Dict[str, Any],
    ) -> Dict[str, Any]:
        weekly = self._build_weekly_reflection_from_behavioral(behavioral, activity_feed)
        memory = self._build_behavioral_memory_report(activity_feed, behavioral)
        outcome_memory = self._build_outcome_memory_summary(governance_events, activity_feed)

        decision_events = [event for event in governance_events if str(event.get("type") or "") == "finn_decision_review"]
        adherence_events = [event for event in governance_events if str(event.get("type") or "") == "finn_plan_adherence_review"]
        outcome_events = [event for event in governance_events if str(event.get("type") or "") == "finn_outcome_tracking_summary"]
        portfolio_events = [event for event in governance_events if str(event.get("type") or "") == "finn_portfolio_intelligence"]

        insufficient_decisions = 0
        blocked_or_modify = 0
        for event in decision_events:
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            status = str(payload.get("decision_status") or "")
            if status == "insufficient_context":
                insufficient_decisions += 1
            if status in {"block", "modify"}:
                blocked_or_modify += 1

        override_events = 0
        outside_plan_events = 0
        for event in adherence_events:
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            status = str(payload.get("adherence_status") or "")
            if status == "forced_override":
                override_events += 1
            if status in {"outside_plan", "forced_override"}:
                outside_plan_events += 1

        negative_outcomes = 0
        strong_outcomes = 0
        for event in outcome_events:
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            net_effect = str(payload.get("net_effect") or "").lower()
            if any(term in net_effect for term in ["negatief", "lekt", "vaker slecht", "verlies"]):
                negative_outcomes += 1
            if int(payload.get("sample_size") or 0) >= 3:
                strong_outcomes += 1

        concentrated_portfolio = 0
        for event in portfolio_events:
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            if str(payload.get("portfolio_status") or "") in {"concentrated", "high_attention"}:
                concentrated_portfolio += 1

        metrics_7d = weekly.get("metrics") or {}
        metrics_30d = memory.get("metrics") or {}
        skipped = int(metrics_30d.get("skipped_30d") or 0)
        snoozed = int(metrics_30d.get("snoozed_30d") or 0)
        monitored = int(metrics_30d.get("monitor_30d") or 0)
        review_actions = int(metrics_30d.get("review_actions_30d") or 0)
        churn_30d = int(metrics_30d.get("decision_churn_events_30d") or 0)

        discipline_base = weekly.get("discipline_score")
        discipline_quality = discipline_base if discipline_base is not None else 70
        discipline_quality -= override_events * 8
        discipline_quality -= max(0, outside_plan_events - override_events) * 5
        discipline_quality = max(35, min(95, discipline_quality))

        decision_quality = 72 + min(8, len(decision_events) * 2)
        decision_quality -= insufficient_decisions * 7
        decision_quality -= concentrated_portfolio * 4
        decision_quality += min(6, blocked_or_modify * 2)
        decision_quality = max(40, min(94, decision_quality))

        follow_through_quality = 64
        if review_actions >= 3:
            follow_through_quality += 10
        follow_through_quality += min(8, skipped + snoozed + monitored)
        if churn_30d:
            follow_through_quality -= churn_30d * 4
        follow_through_quality = max(38, min(92, follow_through_quality))

        recovery_quality = 62
        if outcome_memory.get("memory_pattern") == "recovery_outcomes":
            recovery_quality += 14
        if skipped + snoozed >= 2:
            recovery_quality += 8
        if negative_outcomes >= 2 and skipped + snoozed == 0:
            recovery_quality -= 8
        recovery_quality = max(35, min(92, recovery_quality))

        selectivity_quality = 66
        selectivity_quality -= churn_30d * 5
        selectivity_quality -= concentrated_portfolio * 6
        if blocked_or_modify >= 2:
            selectivity_quality += 6
        selectivity_quality = max(35, min(90, selectivity_quality))

        score_breakdown = [
            {
                "key": "decision_quality",
                "label": "Decision quality",
                "score": int(round(decision_quality)),
                "summary": "Hoe scherp je review, risico en context samenkomen voordat je iets doet.",
            },
            {
                "key": "discipline_quality",
                "label": "Discipline quality",
                "score": int(round(discipline_quality)),
                "summary": "Hoe vaak je plan, guardrails en wachtdiscipline overeind blijven onder druk.",
            },
            {
                "key": "follow_through_quality",
                "label": "Follow-through quality",
                "score": int(round(follow_through_quality)),
                "summary": "Of je open reviews echt afrondt, bewaakt of bewust parkeert.",
            },
            {
                "key": "recovery_quality",
                "label": "Recovery quality",
                "score": int(round(recovery_quality)),
                "summary": "Hoe goed je na druk, twijfel of verlies terugschakelt naar veilig gedrag.",
            },
            {
                "key": "selectivity_quality",
                "label": "Selectivity quality",
                "score": int(round(selectivity_quality)),
                "summary": "Of je kwaliteit boven activiteit zet en niet te veel tegelijk wilt forceren.",
            },
        ]
        performance_score = int(round(sum(item["score"] for item in score_breakdown) / len(score_breakdown)))

        drivers: List[Dict[str, Any]] = []
        if skipped + snoozed + monitored >= 2:
            drivers.append({
                "type": "positive",
                "label": "Bewust vertragen helpt je",
                "summary": f"{skipped} skips, {snoozed} snoozes en {monitored} monitor-acties laten zien dat je niet alles hoeft te forceren.",
            })
        if strong_outcomes >= 2:
            drivers.append({
                "type": "positive",
                "label": "Outcome-bewijs wordt bruikbaar",
                "summary": f"{strong_outcomes} uitkomstsignalen geven Finn genoeg bewijs om gedrag echt aan resultaat te koppelen.",
            })
        if override_events:
            drivers.append({
                "type": "negative",
                "label": "Plan-overrides drukken je score",
                "summary": f"{override_events} override-signaal/signalen laten zien dat discipline onder druk nog kwetsbaar is.",
            })
        if churn_30d:
            drivers.append({
                "type": "negative",
                "label": "Decision-churn verlaagt je selectiviteit",
                "summary": f"{churn_30d} churn-event(s) suggereren dat je soms te snel een volgende beslissing zoekt.",
            })
        if concentrated_portfolio:
            drivers.append({
                "type": "negative",
                "label": "Concentratierisico trekt aan je kwaliteit",
                "summary": f"{concentrated_portfolio} portfolio-waarschuwing(en) laten zien dat goede losse ideeën samen te veel risico kunnen stapelen.",
            })

        risk_flags = [
            driver["summary"]
            for driver in drivers
            if driver.get("type") == "negative"
        ][:4]

        week_summary = ((weekly.get("week_over_week") or {}).get("summary") or "").strip()
        if week_summary and "nog geen" not in week_summary.lower():
            discipline_delta = {
                "direction": "mixed" if "evenveel" in week_summary else "up" if "minder" in week_summary else "down",
                "summary": week_summary,
            }
        else:
            discipline_delta = {
                "direction": "flat",
                "summary": "Nog te weinig vergelijkingshistorie om je disciplineontwikkeling hard te scoren.",
            }

        if recovery_quality >= 78:
            recovery_status = "stable_recovery"
        elif negative_outcomes >= 2 and skipped + snoozed == 0:
            recovery_status = "under_pressure_without_brake"
        else:
            recovery_status = "mixed_recovery"

        weakest = min(score_breakdown, key=lambda item: item["score"])
        growth_targets = {
            "decision_quality": "Laat Finn vaker eerst reviewen met expliciete setup-, sizing- en exposuredata voordat je een trade verdedigt.",
            "discipline_quality": "Maak van planbreuk een harde pauzeknop: eerst hercheck, dan pas actie.",
            "follow_through_quality": "Rond open reviews bewuster af zodat je minder halve beslissingen laat hangen.",
            "recovery_quality": "Gebruik na druk of verlies eerst skip, snooze of review als herstelactie in plaats van snelheid.",
            "selectivity_quality": "Verlaag de drang om steeds opnieuw actie te zoeken; kwaliteit moet zwaarder wegen dan activiteit.",
        }
        next_growth_target = growth_targets.get(weakest["key"])
        operator_next_step = (
            "Gebruik deze performance-laag als weekanker: pak eerst het zwakste component aan voordat je meer volume of complexiteit toevoegt."
        )

        return {
            "performance_score": performance_score,
            "score_breakdown": score_breakdown,
            "performance_drivers": drivers[:5],
            "discipline_delta": discipline_delta,
            "recovery_status": recovery_status,
            "performance_risk_flags": risk_flags,
            "next_growth_target": next_growth_target,
            "operator_next_step": operator_next_step,
            "headline": "Ik kijk nu niet alleen naar uitkomsten, maar naar de kwaliteit van hoe je trade, wacht en herstelt.",
            "time_window": "last_30_days",
            "source": {
                "decision_reviews": len(decision_events),
                "adherence_events": len(adherence_events),
                "outcome_events": len(outcome_events),
                "portfolio_events": len(portfolio_events),
            },
        }

    async def build_personal_performance_response(
        self,
        user_id: int,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = context or {}
        lightweight_prompt = self._is_lightweight_personal_performance_prompt(query)
        activity_limit = 90 if lightweight_prompt else 180
        governance_limit = 60 if lightweight_prompt else 90
        activity_feed = await self._get_recent_finn_activity(user_id, limit=activity_limit)
        day_log = self._mission_day_log(activity_feed)
        behavioral = self._build_behavioral_insight_from_activity(activity_feed, day_log)
        governance_events = await self._fetch_recent_governance_events(
            user_id,
            event_types=[
                "finn_decision_review",
                "finn_plan_adherence_review",
                "finn_outcome_tracking_summary",
                "finn_outcome_memory_summary",
                "finn_portfolio_intelligence",
            ],
            limit=governance_limit,
        )
        analysis = self._build_personal_performance_summary(activity_feed, governance_events, behavioral)
        await self._record_governance_event(
            user_id,
            event_type="finn_personal_performance_summary",
            symbol=context.get("symbol") if isinstance(context, dict) else None,
            title="Finn bouwde een Personal Performance samenvatting",
            description=analysis.get("next_growth_target") or analysis.get("operator_next_step"),
            severity="info",
            payload={
                "phase": "personal_performance_layer",
                "query": query,
                "performance_score": analysis.get("performance_score"),
                "score_breakdown": analysis.get("score_breakdown"),
                "recovery_status": analysis.get("recovery_status"),
                "next_growth_target": analysis.get("next_growth_target"),
                "performance_risk_flags": analysis.get("performance_risk_flags"),
            },
            cooldown_hours=6,
        )
        return {
            "response": self._personal_performance_message(analysis),
            "intent": "personal_performance",
            "flow": "personal_performance",
            "draft": None,
            "missing_fields": [],
            "invalid_fields": [],
            "next_question": None,
            "can_confirm": False,
            "actions": [],
            "state": {
                "current_flow": "personal_performance",
                "analysis": analysis,
                "behavioral_insight": behavioral,
                "advice_only": True,
            },
            "analysis": analysis,
            "suggested_actions": [
                "Vraag: welk gedrag kost me de laatste maand het meeste?",
                "Vraag: geef mijn weekreflectie",
                "Vraag: open Mission Control",
            ],
        }

    def _build_trade_journal_intelligence_summary(
        self,
        activity_feed: List[Dict[str, Any]],
        governance_events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        evidence_lines: List[str] = []
        raw_queries: List[str] = []
        for event in governance_events or []:
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            query = str(payload.get("query") or "").strip()
            if query:
                raw_queries.append(query)
                evidence_lines.append(query)
            description = str(event.get("description") or "").strip()
            if description:
                evidence_lines.append(description)

        journal_entries = self._build_report_activity_journal(activity_feed).get("entries") or []
        for item in journal_entries[:6]:
            label = str(item.get("label") or "").strip()
            asset = str(item.get("asset") or "").strip()
            if label:
                evidence_lines.append(f"{label}{f' ({asset})' if asset else ''}")

        evidence_lines = list(dict.fromkeys([item for item in evidence_lines if item]))[:8]
        evidence_blob = " ".join(evidence_lines).lower()
        query_blob = " ".join(raw_queries).lower()

        objective_terms = ["setup", "strategie", "strategy", "risico", "risk", "exposure", "trigger", "sizing", "stop-loss", "allocatie", "portfolio"]
        emotion_terms = ["fomo", "twijfel", "bang", "frustratie", "baal", "terugpakken", "haast", "stress", "paniek", "impuls", "emotioneel"]
        rule_break_terms = ["override", "toch", "plan zegt wachten", "stop-loss verwijderen", "grotere positie", "buiten mijn plan", "afwijken"]
        patience_terms = ["wachten", "skip", "snooze", "monitor", "later"]

        objective_hits = sum(1 for term in objective_terms if term in evidence_blob)
        emotion_hits = sum(1 for term in emotion_terms if term in evidence_blob)
        rule_break_hits = sum(1 for term in rule_break_terms if term in evidence_blob)
        patience_hits = sum(1 for term in patience_terms if term in evidence_blob)

        tags: List[str] = []
        if objective_hits:
            tags.append("structured_review")
        if emotion_hits:
            tags.append("emotion_pressure")
        if rule_break_hits:
            tags.append("rule_conflict")
        if patience_hits:
            tags.append("patience_signal")
        if "btc" in evidence_blob:
            tags.append("btc_focus")
        if "eth" in evidence_blob:
            tags.append("eth_focus")

        if len(evidence_lines) < 3 and not raw_queries:
            journal_pattern = "insufficient_journal_signal"
            thesis_quality = "thin_evidence"
            emotion_signal = "unknown"
            decision_gap = "Ik zie nog te weinig expliciete journal- of note-signalen om een beslisgat hard te benoemen."
            post_trade_lesson = "Laat Finn meer post-trade reflectievragen en reviewtaal vastleggen; dan wordt deze laag bruikbaarder."
            coaching_note = "Gebruik na een trade of block 1 korte reflectieregel: waarom deed je dit, wat voelde je, wat negeerde je?"
        else:
            if emotion_hits >= max(2, objective_hits):
                journal_pattern = "emotion_led_entries"
            elif rule_break_hits:
                journal_pattern = "rule_conflict_entries"
            elif objective_hits >= 2:
                journal_pattern = "structured_review_entries"
            else:
                journal_pattern = "mixed_operator_entries"

            if objective_hits >= 3 and emotion_hits <= 1:
                thesis_quality = "strong"
            elif objective_hits >= 1:
                thesis_quality = "mixed"
            else:
                thesis_quality = "thin_evidence"

            if emotion_hits >= 2:
                emotion_signal = "elevated"
            elif patience_hits >= 2 and emotion_hits == 0:
                emotion_signal = "calm"
            else:
                emotion_signal = "mixed"

            if rule_break_hits:
                decision_gap = "Je benoemt de druk of wens om toch te handelen sneller dan de objectieve reden waarom de trade nog geldig zou zijn."
            elif objective_hits and emotion_hits:
                decision_gap = "Je reviewtaal mengt objectieve checks met emotionele druk; dat maakt overtuiging kwetsbaar."
            elif objective_hits:
                decision_gap = "Je basisreview oogt redelijk gestructureerd, maar Finn ziet nog weinig expliciete post-trade lesformulering."
            else:
                decision_gap = "Je journal-signalen zijn nog te impliciet; Finn mist nog duidelijk verwoorde trigger, risico en les."

            if "fomo" in query_blob or "verlies" in evidence_blob:
                post_trade_lesson = "Gebruik verlies- of FOMO-notities als harde rem: beschrijf niet alleen wat je voelde, maar welke regel je de volgende keer vooraf activeert."
            elif rule_break_hits:
                post_trade_lesson = "Maak planbreuk expliciet in je notities: welke regel werd bedreigd en waarom vond je dat toch aantrekkelijk?"
            else:
                post_trade_lesson = "Sluit trades of reviews af met één verdedigbare les, zodat Finn patroon en uitkomst later beter kan verbinden."

            coaching_note = (
                "Schrijf journal-notities in vier stukken: trigger, risico, emotie, les. Dan kan Finn veel rijkere persoonlijke feedback geven."
            )

        operator_next_step = "Laat na je volgende trade of blokkade 1 expliciete reflectieregel vastleggen, zodat deze journal-laag minder hoeft te raden."
        return {
            "journal_pattern": journal_pattern,
            "journal_tags": tags,
            "thesis_quality": thesis_quality,
            "emotion_signal": emotion_signal,
            "decision_gap": decision_gap,
            "post_trade_lesson": post_trade_lesson,
            "journal_coaching_note": coaching_note,
            "supporting_evidence_count": len(evidence_lines),
            "supporting_evidence": evidence_lines,
            "headline": "Ik lees je journal-intelligence nu uit de reviewtaal, reflecties en Finn-auditsporen die je al achterlaat.",
            "operator_next_step": operator_next_step,
            "time_window": "last_30_days",
        }

    async def build_trade_journal_intelligence_response(
        self,
        user_id: int,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = context or {}
        activity_feed = await self._get_recent_finn_activity(user_id, limit=180)
        governance_events = await self._fetch_recent_governance_events(
            user_id,
            event_types=[
                "finn_decision_review",
                "finn_plan_adherence_review",
                "finn_outcome_tracking_summary",
                "finn_outcome_memory_summary",
                "finn_portfolio_intelligence",
            ],
            limit=90,
        )
        analysis = self._build_trade_journal_intelligence_summary(activity_feed, governance_events)
        await self._record_governance_event(
            user_id,
            event_type="finn_trade_journal_intelligence_summary",
            symbol=context.get("symbol") if isinstance(context, dict) else None,
            title="Finn bouwde een Trade Journal Intelligence samenvatting",
            description=analysis.get("post_trade_lesson") or analysis.get("decision_gap"),
            severity="info",
            payload={
                "phase": "trade_journal_intelligence",
                "query": query,
                "journal_pattern": analysis.get("journal_pattern"),
                "journal_tags": analysis.get("journal_tags"),
                "thesis_quality": analysis.get("thesis_quality"),
                "emotion_signal": analysis.get("emotion_signal"),
                "decision_gap": analysis.get("decision_gap"),
                "post_trade_lesson": analysis.get("post_trade_lesson"),
            },
            cooldown_hours=6,
        )
        return {
            "response": self._trade_journal_intelligence_message(analysis),
            "intent": "trade_journal_intelligence",
            "flow": "trade_journal_intelligence",
            "draft": None,
            "missing_fields": [],
            "invalid_fields": [],
            "next_question": None,
            "can_confirm": False,
            "actions": [],
            "state": {
                "current_flow": "trade_journal_intelligence",
                "analysis": analysis,
                "advice_only": True,
            },
            "analysis": analysis,
            "suggested_actions": [
                "Vraag: wat leert mijn trade journal?",
                "Vraag: wat onthoudt Finn van mijn uitkomsten?",
                "Vraag: geef mijn Finn rapport",
            ],
        }

    def _build_personal_coach_summary(
        self,
        *,
        query: str,
        outcome_memory: Dict[str, Any],
        personal_performance: Dict[str, Any],
        trade_journal_intelligence: Dict[str, Any],
        portfolio_operating_system: Dict[str, Any],
    ) -> Dict[str, Any]:
        q = self._normalized_query(query)
        posture = str(portfolio_operating_system.get("operating_posture") or "")
        performance_score = personal_performance.get("performance_score")
        recovery_status = str(personal_performance.get("recovery_status") or "")
        journal_pattern = str(trade_journal_intelligence.get("journal_pattern") or "")
        memory_pattern = str(outcome_memory.get("memory_pattern") or "")

        if any(term in q for term in ["coach me op basis van mijn laatste fouten", "wat is mijn grootste persoonlijke performance lek", "wat moet ik nu in mezelf onderbreken", "welk patroon moet ik nu doorbreken"]):
            coach_mode = "interruptive"
        elif any(term in q for term in ["word ik beter of slechter", "ben ik beter of slechter", "aan het worden", "volgende beste coachregel"]):
            coach_mode = "reflective"
        elif any(term in q for term in ["wat moet ik nu", "moet ik deze trade", "nu instappen", "nu kopen", "nu doen"]):
            coach_mode = "pre_trade"
        elif any(term in q for term in ["laatste fouten", "achteraf", "post trade", "post-trade", "wat leer"]):
            coach_mode = "post_trade"
        elif recovery_status == "under_pressure_without_brake" or memory_pattern == "recovery_outcomes":
            coach_mode = "recovery"
        elif posture in {"risk_first", "performance_rebuild"} or any(term in q for term in ["onderbreken", "doorbreken", "meest discipline", "performance lek"]):
            coach_mode = "interruptive"
        else:
            coach_mode = "reflective"

        if coach_mode == "interruptive":
            current_pattern = (
                trade_journal_intelligence.get("decision_gap")
                or personal_performance.get("next_growth_target")
                or outcome_memory.get("repeat_trigger")
                or "Je zoekt te snel een volgende actie terwijl je echte rempunt nog niet is opgelost."
            )
            what_it_costs = (
                (personal_performance.get("performance_risk_flags") or [None])[0]
                or outcome_memory.get("behavioral_cost")
                or "Dit kost je vooral disciplinekwaliteit en maakt goede reviews minder waard."
            )
            what_to_interrupt_now = (
                portfolio_operating_system.get("portfolio_pressure", {}).get("source")
                or trade_journal_intelligence.get("decision_gap")
                or "De drang om nu iets te doen zonder dat je beste reden al objectief klopt."
            )
        elif coach_mode == "recovery":
            current_pattern = outcome_memory.get("repeat_trigger") or "Je beste herstel komt niet uit snelheid maar uit vertragen en opnieuw prioriteren."
            what_it_costs = outcome_memory.get("behavioral_cost") or "Als je herstel overslaat, ga je sneller van onrust naar een slechtere volgende beslissing."
            what_to_interrupt_now = "De neiging om na druk, verlies of frustratie meteen een volgende actie te zoeken."
        elif coach_mode == "pre_trade":
            current_pattern = trade_journal_intelligence.get("decision_gap") or "Je pre-trade overtuiging wordt nu sneller door druk dan door kwaliteit gestuurd."
            what_it_costs = (
                outcome_memory.get("behavioral_cost")
                or (personal_performance.get("performance_risk_flags") or [None])[0]
                or "Dit kost je vooral selectiviteit en verhoogt de kans op een trade die je achteraf niet goed kunt verdedigen."
            )
            what_to_interrupt_now = "De stap van review naar uitvoering zolang trigger, sizing en exposure nog niet hard genoeg staan."
        elif coach_mode == "post_trade":
            current_pattern = journal_pattern if journal_pattern and journal_pattern != "insufficient_journal_signal" else "Je noteert of herinnert de les nog niet scherp genoeg."
            what_it_costs = (
                trade_journal_intelligence.get("post_trade_lesson")
                or "Zonder expliciete les herhaal je sneller hetzelfde gedrag met een nieuw excuus."
            )
            what_to_interrupt_now = "De reflex om te rationaliseren in plaats van één bruikbare regel terug te schrijven."
        else:
            current_pattern = (
                outcome_memory.get("memory_pattern")
                or trade_journal_intelligence.get("journal_pattern")
                or "Ik zie nog geen enkel patroon dat alle andere overstemt."
            )
            what_it_costs = (
                outcome_memory.get("behavioral_cost")
                or "De grootste kost zit nu niet in één trade, maar in herhaling van kleine kwaliteitslekken."
            )
            what_to_interrupt_now = (
                trade_journal_intelligence.get("decision_gap")
                or portfolio_operating_system.get("portfolio_pressure", {}).get("source")
                or "De gewoonte om te reageren voordat je eerst je beste regel activeert."
            )

        next_best_rule = (
            outcome_memory.get("recommended_rule")
            or personal_performance.get("next_growth_target")
            or trade_journal_intelligence.get("journal_coaching_note")
            or "Gebruik eerst review, regel en context; snelheid komt pas daarna."
        )
        do_now = portfolio_operating_system.get("do_now") or []
        coach_follow_up = (
            (do_now[0] if do_now else None)
            or personal_performance.get("operator_next_step")
            or trade_journal_intelligence.get("operator_next_step")
            or "Laat Finn eerst je volgende review of reflectieregel vastleggen."
        )
        supporting_signals = [
            item for item in [
                outcome_memory.get("latest_outcome_summary"),
                (personal_performance.get("performance_drivers") or [{}])[0].get("summary") if personal_performance.get("performance_drivers") else None,
                trade_journal_intelligence.get("decision_gap"),
                portfolio_operating_system.get("portfolio_pressure", {}).get("source"),
            ] if item
        ]
        return {
            "coach_mode": coach_mode,
            "current_pattern": current_pattern,
            "what_it_costs": what_it_costs,
            "what_to_interrupt_now": what_to_interrupt_now,
            "next_best_rule": next_best_rule,
            "coach_follow_up": coach_follow_up,
            "supporting_signals": supporting_signals[:4],
            "headline": "Ik combineer nu je uitkomstgeheugen, performance, journal-signalen en portfolio-posture tot één persoonlijke coachlaag.",
            "source_layers": {
                "outcome_memory": outcome_memory.get("memory_pattern"),
                "performance_score": performance_score,
                "journal_pattern": journal_pattern,
                "operating_posture": posture,
            },
        }

    async def build_personal_coach_response(
        self,
        user_id: int,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = context or {}
        lightweight_prompt = self._is_lightweight_personal_coach_prompt(query)
        activity_limit = 90 if lightweight_prompt else 180
        governance_limit = 60 if lightweight_prompt else 90
        activity_feed = await self._get_recent_finn_activity(user_id, limit=activity_limit)
        day_log = self._mission_day_log(activity_feed)
        behavioral = self._build_behavioral_insight_from_activity(activity_feed, day_log)
        governance_events = await self._fetch_recent_governance_events(
            user_id,
            event_types=[
                "finn_decision_review",
                "finn_plan_adherence_review",
                "finn_outcome_tracking_summary",
                "finn_outcome_memory_summary",
                "finn_personal_performance_summary",
                "finn_personal_coach_summary",
                "finn_trade_journal_intelligence_summary",
                "finn_portfolio_intelligence",
                "finn_priority_engine_summary",
                "finn_memory_v2_summary",
                "finn_portfolio_operating_system_summary",
            ],
            limit=governance_limit,
        )
        outcome_memory = self._build_outcome_memory_summary(governance_events, activity_feed)
        personal_performance = self._build_personal_performance_summary(activity_feed, governance_events, behavioral)
        trade_journal_intelligence = self._build_trade_journal_intelligence_summary(activity_feed, governance_events)

        mission_context = {}
        if not lightweight_prompt:
            try:
                mission_context = await self.build_mission_control_response(user_id, {"page": "mission_control"})
            except Exception:
                mission_context = {}
        portfolio_operating_system = (
            (mission_context.get("analysis") or {}).get("portfolio_operating_system")
            or mission_context.get("portfolio_operating_system")
            or {}
        )
        if not portfolio_operating_system:
            portfolio_operating_system = self._portfolio_operating_system_contract(
                daily_analysis={},
                mission={"summary": {}, "plan_health": [], "portfolio_risk": {}, "workqueue": []},
                priority_engine={},
                memory={},
                personal_performance=personal_performance,
                trade_journal_intelligence=trade_journal_intelligence,
                governance_events=governance_events,
            )

        analysis = self._build_personal_coach_summary(
            query=query,
            outcome_memory=outcome_memory,
            personal_performance=personal_performance,
            trade_journal_intelligence=trade_journal_intelligence,
            portfolio_operating_system=portfolio_operating_system,
        )
        await self._record_governance_event(
            user_id,
            event_type="finn_personal_coach_summary",
            symbol=context.get("symbol") if isinstance(context, dict) else None,
            title="Finn bouwde een Personal Coach samenvatting",
            description=analysis.get("what_to_interrupt_now") or analysis.get("next_best_rule"),
            severity="info",
            payload={
                "phase": "personal_coach_engine",
                "query": query,
                "coach_mode": analysis.get("coach_mode"),
                "current_pattern": analysis.get("current_pattern"),
                "what_it_costs": analysis.get("what_it_costs"),
                "what_to_interrupt_now": analysis.get("what_to_interrupt_now"),
                "next_best_rule": analysis.get("next_best_rule"),
                "coach_follow_up": analysis.get("coach_follow_up"),
            },
            cooldown_hours=4,
        )
        return {
            "response": self._personal_coach_message(analysis),
            "intent": "personal_coach",
            "flow": "personal_coach",
            "draft": None,
            "missing_fields": [],
            "invalid_fields": [],
            "next_question": None,
            "can_confirm": False,
            "actions": [],
            "state": {
                "current_flow": "personal_coach",
                "analysis": analysis,
                "outcome_memory": outcome_memory,
                "personal_performance": personal_performance,
                "trade_journal_intelligence": trade_journal_intelligence,
                "portfolio_operating_system": portfolio_operating_system,
                "advice_only": True,
            },
            "analysis": analysis,
            "suggested_actions": [
                "Vraag: wat is mijn grootste persoonlijke performance lek?",
                "Vraag: wat leert mijn trade journal?",
                "Vraag: open Mission Control",
            ],
        }

    def _build_memory_v2_summary(
        self,
        activity_feed: List[Dict[str, Any]],
        governance_events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        pattern_scores = {
            "plan_break_pattern": {"score": 0, "evidence": [], "cost": "Planbreuken kosten je discipline en maken goede reviews minder bruikbaar.", "rule": "Geen override zonder expliciete hercheck van trigger, sizing en exposure."},
            "emotional_pattern": {"score": 0, "evidence": [], "cost": "Emotionele druk duwt je sneller naar actie dan je plan kan dragen.", "rule": "Geen nieuwe trade zolang frustratie, FOMO of haast nog de hoofdreden is."},
            "exposure_pattern": {"score": 0, "evidence": [], "cost": "Goede losse beslissingen kunnen samen alsnog te veel concentratierisico geven.", "rule": "Voeg geen exposure toe als dezelfde asset al dominant is in je portfolio."},
            "recovery_pattern": {"score": 0, "evidence": [], "cost": "Je sterkste herstel komt juist uit vertragen, skippen en opnieuw prioriteren.", "rule": "Gebruik review, skip of snooze als eerste herstelactie zodra druk oploopt."},
            "hesitation_pattern": {"score": 0, "evidence": [], "cost": "Te veel review zonder besluit kan je focus en uitvoerkwaliteit uithollen.", "rule": "Na herhaalde review kies je bewust: uitvoeren, blokkeren of parkeren."},
        }

        for event in governance_events or []:
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            event_type = str(event.get("type") or "")
            query = self._normalized_query(str(payload.get("query") or ""))
            if event_type == "finn_plan_adherence_review":
                adherence = str(payload.get("adherence_status") or "")
                if adherence in {"forced_override", "outside_plan"}:
                    pattern_scores["plan_break_pattern"]["score"] += 3
                    pattern_scores["plan_break_pattern"]["evidence"].append(payload.get("threatened_rule") or event.get("description"))
                elif adherence == "insufficiently_justified":
                    pattern_scores["hesitation_pattern"]["score"] += 1
                    pattern_scores["hesitation_pattern"]["evidence"].append(event.get("description"))
            elif event_type == "finn_decision_review":
                status = str(payload.get("decision_status") or "")
                if any(term in query for term in ["fomo", "gefrustreerd", "emotionele", "terugpakken", "haast", "nu handelen"]):
                    pattern_scores["emotional_pattern"]["score"] += 3 if status in {"block", "modify"} else 2
                    pattern_scores["emotional_pattern"]["evidence"].append((payload.get("top_blockers") or [None])[0] or event.get("description"))
                if status in {"modify", "block"} and any("allocatie" in str(item).lower() or "exposure" in str(item).lower() for item in (payload.get("top_blockers") or [])):
                    pattern_scores["exposure_pattern"]["score"] += 2
                    pattern_scores["exposure_pattern"]["evidence"].append((payload.get("top_blockers") or [None])[0] or event.get("description"))
            elif event_type == "finn_portfolio_intelligence":
                portfolio_status = str(payload.get("portfolio_status") or "")
                if portfolio_status in {"high_attention", "concentrated"}:
                    pattern_scores["exposure_pattern"]["score"] += 3
                    pattern_scores["exposure_pattern"]["evidence"].append(
                        payload.get("concentration_warning") or payload.get("stacked_risk_warning") or event.get("description")
                    )
            elif event_type == "finn_outcome_tracking_summary":
                sample_size = int(payload.get("sample_size") or 0)
                net_effect = str(payload.get("net_effect") or "")
                if sample_size >= 3 and any(term in net_effect.lower() for term in ["remmen", "niet-doen", "blocks", "skips"]):
                    pattern_scores["recovery_pattern"]["score"] += 2
                    pattern_scores["recovery_pattern"]["evidence"].append(net_effect)

        skipped = len([item for item in activity_feed or [] if str(item.get("resolve_state") or "") == "skipped"])
        snoozed = len([item for item in activity_feed or [] if str(item.get("resolve_state") or "") == "snoozed"])
        monitored = len([item for item in activity_feed or [] if str(item.get("resolve_state") or "") == "monitor_today"])
        reviewed = len([item for item in activity_feed or [] if str(item.get("type") or "") in {"live_preflight_bot_decision", "live_manual_order_preflight"}])
        executed = len([item for item in activity_feed or [] if str(item.get("type") or "") in {"paper_execute_bot_decision", "live_manual_order_confirmed", "manual_order"}])
        if skipped + snoozed + monitored >= 3:
            pattern_scores["recovery_pattern"]["score"] += 2
            pattern_scores["recovery_pattern"]["evidence"].append(
                f"{skipped} skips, {snoozed} snoozes en {monitored} monitor-acties laten herstelgedrag zien."
            )
        if reviewed >= max(3, executed + 2):
            pattern_scores["hesitation_pattern"]["score"] += 2
            pattern_scores["hesitation_pattern"]["evidence"].append(
                f"{reviewed} review/preflight-momenten tegenover {executed} execution-acties."
            )

        primary_pattern, primary_data = max(
            pattern_scores.items(),
            key=lambda item: (item[1]["score"], len(item[1]["evidence"])),
        )
        evidence = [item for item in primary_data.get("evidence") or [] if item]
        evidence = list(dict.fromkeys(str(item) for item in evidence))[:4]
        evidence_count = len(evidence)
        if primary_data.get("score", 0) >= 6 and evidence_count >= 2:
            confidence = "high"
        elif primary_data.get("score", 0) >= 3 and evidence_count >= 1:
            confidence = "medium"
        else:
            confidence = "low"
        if confidence == "low":
            primary_pattern = "insufficient_memory_signal"
            cost = "Ik zie nog losse signalen, maar nog geen sterk genoeg patroon om als vaste gedragsregel te onthouden."
            rule = "Blijf reviews, overrides, skips en execution-keuzes via Finn laten lopen zodat dit patroon scherper wordt."
        else:
            cost = primary_data.get("cost")
            rule = primary_data.get("rule")
        return {
            "memory_pattern": primary_pattern,
            "supporting_evidence_count": evidence_count,
            "time_window": "last_90_days",
            "behavioral_cost": cost,
            "recommended_rule": rule,
            "confidence_level": confidence,
            "supporting_evidence": evidence,
        }

    async def build_finn_report_response(
        self,
        user_id: int,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        activity_feed = await self._get_recent_finn_activity(user_id, limit=200)
        day_log = self._mission_day_log(activity_feed)
        behavioral = self._build_behavioral_insight_from_activity(activity_feed, day_log)
        report = self._build_finn_reflection_report(activity_feed, behavioral, query)
        governance_events = await self._fetch_recent_governance_events(
            user_id,
            event_types=[
                "finn_decision_review",
                "finn_plan_adherence_review",
                "finn_outcome_tracking_summary",
                "finn_outcome_memory_summary",
                "finn_personal_performance_summary",
                "finn_trade_journal_intelligence_summary",
                "finn_portfolio_intelligence",
                "finn_priority_engine_summary",
                "finn_memory_v2_summary",
                "finn_portfolio_operating_system_summary",
            ],
            limit=80,
        )
        mission_analysis = report.get("mission_control_analysis") or {}
        mission = self._build_mission_control_from_daily_analysis(mission_analysis)
        priority_engine = self._priority_engine_payload(
            mission,
            mission_analysis,
            self._priority_engine_governance_signals(governance_events),
        )
        memory_v2 = self._build_memory_v2_summary(activity_feed, governance_events)
        outcome_memory = self._build_outcome_memory_summary(governance_events, activity_feed)
        personal_performance = self._build_personal_performance_summary(activity_feed, governance_events, behavioral)
        trade_journal_intelligence = self._build_trade_journal_intelligence_summary(activity_feed, governance_events)
        portfolio_operating_system = self._portfolio_operating_system_contract(
            daily_analysis=mission_analysis,
            mission=mission,
            priority_engine=priority_engine,
            memory={**behavioral, **memory_v2},
            personal_performance=personal_performance,
            trade_journal_intelligence=trade_journal_intelligence,
            governance_events=governance_events,
        )
        personal_coach = self._build_personal_coach_summary(
            query=query,
            outcome_memory=outcome_memory,
            personal_performance=personal_performance,
            trade_journal_intelligence=trade_journal_intelligence,
            portfolio_operating_system=portfolio_operating_system,
        )
        governance_events_summary = {
            "decision_review_count": len([event for event in governance_events if str(event.get("type") or "") == "finn_decision_review"]),
            "plan_adherence_count": len([event for event in governance_events if str(event.get("type") or "") == "finn_plan_adherence_review"]),
            "outcome_tracking_count": len([event for event in governance_events if str(event.get("type") or "") == "finn_outcome_tracking_summary"]),
            "outcome_memory_count": len([event for event in governance_events if str(event.get("type") or "") == "finn_outcome_memory_summary"]),
            "personal_performance_count": len([event for event in governance_events if str(event.get("type") or "") == "finn_personal_performance_summary"]),
            "personal_coach_count": len([event for event in governance_events if str(event.get("type") or "") == "finn_personal_coach_summary"]),
            "trade_journal_intelligence_count": len([event for event in governance_events if str(event.get("type") or "") == "finn_trade_journal_intelligence_summary"]),
            "portfolio_intelligence_count": len([event for event in governance_events if str(event.get("type") or "") == "finn_portfolio_intelligence"]),
            "priority_engine_count": len([event for event in governance_events if str(event.get("type") or "") == "finn_priority_engine_summary"]),
            "memory_v2_count": len([event for event in governance_events if str(event.get("type") or "") == "finn_memory_v2_summary"]),
            "portfolio_operating_system_count": len([event for event in governance_events if str(event.get("type") or "") == "finn_portfolio_operating_system_summary"]),
        }
        report = {
            **report,
            "priority_engine": priority_engine,
            "memory_v2": memory_v2,
            "outcome_memory": outcome_memory,
            "personal_performance": personal_performance,
            "personal_coach": personal_coach,
            "trade_journal_intelligence": trade_journal_intelligence,
            "portfolio_operating_system": portfolio_operating_system,
            "governance_events_summary": governance_events_summary,
        }
        response = self._finn_reflection_report_message(report)
        return {
            "response": response,
            "intent": "finn_report",
            "flow": "finn_report",
            "draft": None,
            "missing_fields": [],
            "invalid_fields": [],
            "next_question": None,
            "can_confirm": False,
            "actions": [],
            "state": {
                "current_flow": "finn_report",
                "analysis": report,
                "report_type": report.get("report_type"),
                "report_family": report.get("report_family"),
                "source": report.get("source"),
                "agent_controller": report.get("agent_controller"),
                "behavioral_insight": behavioral,
                "agent_learning": report.get("agent_learning"),
                "agent_rhythm": report.get("agent_rhythm"),
                "operating_rules": report.get("operating_rules"),
                "priority_engine": priority_engine,
                "memory_v2": memory_v2,
                "outcome_memory": outcome_memory,
                "personal_performance": personal_performance,
                "personal_coach": personal_coach,
                "trade_journal_intelligence": trade_journal_intelligence,
                "portfolio_operating_system": portfolio_operating_system,
                "governance_events_summary": governance_events_summary,
                "advice_only": True,
                "separate_from": report.get("separate_from"),
            },
            "analysis": report,
            "suggested_actions": [
                "Vraag: geef mijn weekreflectie",
                "Vraag: geef mijn gedragsrapport van de laatste 30 dagen",
                "Vraag: open Mission Control",
            ],
        }

    def _build_weekly_reflection_from_behavioral(
        self,
        behavioral: Dict[str, Any],
        activity_feed: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        metrics = behavioral.get("metrics") or {}
        signals = behavioral.get("signals") or []
        patterns = behavioral.get("patterns") or []
        week_over_week = self._behavioral_week_over_week(metrics)
        behavioral_profile = self._behavioral_profile_from_metrics(metrics, patterns)
        risk_flags = self._behavioral_risk_flags(metrics, patterns)
        habit_cards = self._behavioral_habit_cards(metrics, patterns)
        agent_learning = self._agent_performance_light(activity_feed)
        agent_rhythm = self._agent_rhythm_from_learning(agent_learning)
        operating_rules = self._personal_operating_rules(agent_rhythm, metrics)
        enough_data = metrics.get("actions_7d", 0) >= 3 or bool(patterns and patterns != ["discipline_neutral"])

        strengths = []
        watchouts = []
        if "disciplined_waiting" in patterns:
            strengths.append("Je hebt deze week bewust afgeremd via skip, monitor of later-opnieuw-bekijken.")
        if metrics.get("skipped_7d", 0) > 0:
            strengths.append(f"Je hebt {metrics.get('skipped_7d')} keer bewust niet doorgezet. Dat is discipline, geen passiviteit.")
        if metrics.get("snoozed_7d", 0) > 0:
            strengths.append(f"Je hebt {metrics.get('snoozed_7d')} item(s) uitgesteld in plaats van direct te reageren.")
        if metrics.get("executed_7d", 0) > 0 and metrics.get("possible_overrides_7d", 0) == 0:
            strengths.append("Ik zie geen geregistreerde plan-afwijking events in je recente Finn-activiteit.")
        if "decision_churn" in patterns:
            if metrics.get("decision_churn_events_7d", 0) > 0:
                watchouts.append("Je vroeg meerdere keren nieuwe decisions aan terwijl er nog open review stond.")
            else:
                watchouts.append("Veel bot-decisions of execution-intentie kan wijzen op decision churn.")
        if "configuration_churn" in patterns:
            parts = []
            if metrics.get("plan_creates_7d", 0):
                parts.append(f"{metrics.get('plan_creates_7d')} nieuwe plannen")
            if metrics.get("strategy_changes_7d", 0):
                parts.append(f"{metrics.get('strategy_changes_7d')} strategy-wijzigingen")
            if metrics.get("bot_changes_7d", 0):
                parts.append(f"{metrics.get('bot_changes_7d')} bot-wijzigingen")
            if metrics.get("indicator_changes_7d", 0):
                parts.append(f"{metrics.get('indicator_changes_7d')} indicator-wijzigingen")
            detail = ", ".join(parts) if parts else f"{metrics.get('configuration_changes_7d', 0)} configuratiewijzigingen"
            watchouts.append(f"Veel configuratiebeweging ({detail}) kan betekenen dat je plan nog niet stabiel genoeg is.")
        if "execution_friction" in patterns or metrics.get("possible_overrides_7d", 0) > 0:
            watchouts.append("Er zijn signalen van execution pressure of mogelijke plan-afwijking.")
        if "possible_fomo" in patterns:
            watchouts.append("Mogelijke FOMO-druk: meerdere decisions plus execution-intentie op dezelfde dag.")

        if not strengths and enough_data:
            strengths.append("Je gebruikt Finn aantoonbaar als beslislaag in plaats van direct te handelen.")
        if not watchouts and enough_data:
            watchouts.append("Geen duidelijke gedragswaarschuwing gevonden; blijf wel via Mission Control werken.")

        if not enough_data:
            status = "not_enough_data"
            headline = "Ik heb nog te weinig weekdata om een stevige gedragsreflectie te geven."
            score = None
        elif any(signal.get("severity") == "medium" for signal in signals):
            status = "attention"
            headline = "Deze week vraagt om extra discipline: er zijn patronen die op onrust of execution-druk kunnen wijzen."
            score = 55
        else:
            status = "steady"
            headline = "Je weekgedrag oogt beheerst op basis van de recente Finn-activiteit."
            score = 78

        return {
            "status": status,
            "period": "last_7_days",
            "advice_only": True,
            "headline": headline,
            "discipline_score": score,
            "behavioral_balance_score": self._behavioral_balance_score(metrics, patterns),
            "patterns": patterns,
            "behavioral_profile": behavioral_profile,
            "week_over_week": week_over_week,
            "trend": week_over_week,
            "risk_flags": risk_flags,
            "habit_cards": habit_cards,
            "agent_learning": agent_learning,
            "agent_rhythm": agent_rhythm,
            "operating_rules": operating_rules,
            "strengths": strengths,
            "watchouts": watchouts,
            "metrics": {
                "actions_7d": metrics.get("actions_7d", 0),
                "executed_7d": metrics.get("executed_7d", 0),
                "bot_decisions_generated_7d": metrics.get("bot_decisions_generated_7d", 0),
                "paper_executions_7d": metrics.get("paper_executions_7d", 0),
                "live_preflights_7d": metrics.get("live_preflights_7d", 0),
                "plan_creates_7d": metrics.get("plan_creates_7d", 0),
                "strategy_changes_7d": metrics.get("strategy_changes_7d", 0),
                "bot_changes_7d": metrics.get("bot_changes_7d", 0),
                "indicator_changes_7d": metrics.get("indicator_changes_7d", 0),
                "configuration_changes_7d": metrics.get("configuration_changes_7d", 0),
                "skipped_7d": metrics.get("skipped_7d", 0),
                "snoozed_7d": metrics.get("snoozed_7d", 0),
                "monitor_7d": metrics.get("monitor_7d", 0),
                "possible_overrides_7d": metrics.get("possible_overrides_7d", 0),
                "plan_deviation_events_7d": metrics.get("plan_deviation_events_7d", 0),
                "decision_churn_events_7d": metrics.get("decision_churn_events_7d", 0),
                "execution_pressure_events_7d": metrics.get("execution_pressure_events_7d", 0),
                "previous_actions_7d": metrics.get("previous_actions_7d", 0),
                "previous_bot_decisions_generated_7d": metrics.get("previous_bot_decisions_generated_7d", 0),
                "previous_configuration_changes_7d": metrics.get("previous_configuration_changes_7d", 0),
                "previous_skipped_7d": metrics.get("previous_skipped_7d", 0),
                "previous_snoozed_7d": metrics.get("previous_snoozed_7d", 0),
                "previous_monitor_7d": metrics.get("previous_monitor_7d", 0),
            },
            "evidence": self._weekly_reflection_evidence(activity_feed),
            "safe_next_step": (
                agent_rhythm["tomorrow_focus"][0]
                if agent_rhythm.get("status") == "ready" and agent_rhythm.get("tomorrow_focus") else
                "Gebruik volgende week Mission Control als werkqueue: eerst reviewen, dan pas nieuwe decisions maken."
                if status != "not_enough_data"
                else "Laat Finn deze week je actions, skips en reviews vastleggen; daarna wordt de reflectie rijker."
            ),
        }

    def _weekly_reflection_evidence(self, activity_feed: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        evidence = []
        for item in activity_feed[:8]:
            evidence.append({
                "type": item.get("type"),
                "resolve_state": item.get("resolve_state"),
                "asset": item.get("asset"),
                "created_at": item.get("created_at"),
                "outcome": item.get("outcome"),
                "behavioral_event": item.get("behavioral_event"),
            })
        return evidence

    def _build_behavioral_memory_report(
        self,
        activity_feed: List[Dict[str, Any]],
        behavioral: Dict[str, Any],
    ) -> Dict[str, Any]:
        now = _utc_now()
        items_30d = []
        previous_30d = []
        for item in activity_feed or []:
            created_at = self._parse_mission_timestamp(item.get("created_at"))
            if not created_at:
                continue
            if created_at >= now - timedelta(days=30):
                items_30d.append(item)
            elif created_at >= now - timedelta(days=60):
                previous_30d.append(item)

        def count_type(items: List[Dict[str, Any]], action_type: str) -> int:
            return len([item for item in items if item.get("type") == action_type])

        def count_resolution(items: List[Dict[str, Any]], resolution: str) -> int:
            return len([item for item in items if item.get("resolve_state") == resolution])

        behavioral_events = [
            item.get("behavioral_event") for item in items_30d
            if isinstance(item.get("behavioral_event"), dict)
        ]
        event_counts: Dict[str, int] = {}
        for event in behavioral_events:
            event_type = str(event.get("type") or "unknown")
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

        plan_creates = count_type(items_30d, "create_plan")
        strategy_changes = count_type(items_30d, "create_strategy")
        bot_changes = count_type(items_30d, "create_bot") + count_type(items_30d, "bot_config_update")
        indicator_changes = count_type(items_30d, "configure_indicator")
        configuration_changes = plan_creates + strategy_changes + bot_changes + indicator_changes
        review_actions = (
            count_type(items_30d, "skip_bot_decision")
            + count_type(items_30d, "resolve_mission_item")
            + count_type(items_30d, "snooze_mission_item")
        )
        first_seen = min(
            [self._parse_mission_timestamp(item.get("created_at")) for item in items_30d if self._parse_mission_timestamp(item.get("created_at"))],
            default=None,
        )
        days_observed = max(1, (now.date() - first_seen.date()).days + 1) if first_seen else 0

        metrics = {
            "actions_30d": len(items_30d),
            "previous_actions_30d": len(previous_30d),
            "executed_30d": len([item for item in items_30d if item.get("status") == "executed"]),
            "bot_decisions_generated_30d": count_type(items_30d, "generate_bot_decision"),
            "paper_executions_30d": count_type(items_30d, "paper_execute_bot_decision"),
            "live_preflights_30d": count_type(items_30d, "live_preflight_bot_decision"),
            "skipped_30d": count_resolution(items_30d, "skipped"),
            "snoozed_30d": count_resolution(items_30d, "snoozed"),
            "monitor_30d": count_resolution(items_30d, "monitor_today"),
            "plan_creates_30d": plan_creates,
            "strategy_changes_30d": strategy_changes,
            "bot_changes_30d": bot_changes,
            "indicator_changes_30d": indicator_changes,
            "configuration_changes_30d": configuration_changes,
            "review_actions_30d": review_actions,
            "behavioral_events_30d": len(behavioral_events),
            "decision_churn_events_30d": event_counts.get("decision_churn", 0),
            "execution_pressure_events_30d": event_counts.get("execution_pressure", 0),
            "plan_deviation_events_30d": event_counts.get("plan_deviation_attempt", 0) + event_counts.get("strategy_change_pressure", 0),
            "days_observed": days_observed,
        }

        memory_cards = []
        if metrics["decision_churn_events_30d"] > 0 or metrics["bot_decisions_generated_30d"] >= 5:
            memory_cards.append({
                "type": "decision_churn",
                "label": "Decision-churn aandachtspunt",
                "confidence": "medium" if metrics["decision_churn_events_30d"] else "low",
                "summary": "Finn moet extra remmen als je opnieuw bot-decisions aanvraagt terwijl review nog openstaat.",
                "evidence": [
                    f"{metrics['bot_decisions_generated_30d']} bot-decisions in 30 dagen",
                    f"{metrics['decision_churn_events_30d']} expliciete decision-churn events",
                ],
            })
        if metrics["plan_deviation_events_30d"] > 0 or metrics["execution_pressure_events_30d"] > 0:
            memory_cards.append({
                "type": "execution_pressure",
                "label": "Risk-officer frictie blijft nodig",
                "confidence": "medium",
                "summary": "Er zijn plan-afwijking of live/manual execution pressure events gevonden.",
                "evidence": [
                    f"{metrics['plan_deviation_events_30d']} plan-afwijking events",
                    f"{metrics['execution_pressure_events_30d']} execution-pressure events",
                ],
            })
        if metrics["configuration_changes_30d"] >= 6:
            memory_cards.append({
                "type": "configuration_churn",
                "label": "Veel configuratiebeweging",
                "confidence": "medium",
                "summary": "Je past relatief vaak setups, strategies, bots of indicatoren aan. Finn moet vaker vragen of dit verbetering of richtingwissel is.",
                "evidence": [
                    f"{metrics['configuration_changes_30d']} configuratiewijzigingen in 30 dagen",
                    f"{metrics['plan_creates_30d']} plannen, {metrics['strategy_changes_30d']} strategies, {metrics['bot_changes_30d']} bots, {metrics['indicator_changes_30d']} indicators",
                ],
            })
        if metrics["skipped_30d"] + metrics["snoozed_30d"] + metrics["monitor_30d"] >= 2:
            memory_cards.append({
                "type": "disciplined_waiting",
                "label": "Bewust wachten",
                "confidence": "medium",
                "summary": "Je gebruikt skip, monitor of later-opnieuw-bekijken als frictie in plaats van direct door te drukken.",
                "evidence": [
                    f"{metrics['skipped_30d']} skips",
                    f"{metrics['snoozed_30d']} snoozes",
                    f"{metrics['monitor_30d']} monitor-acties",
                ],
            })

        status = "not_enough_data"
        if metrics["actions_30d"] >= 8 and days_observed >= 3:
            status = "memory_ready"
        elif metrics["actions_30d"] >= 3:
            status = "early_memory"

        if not memory_cards and status != "not_enough_data":
            memory_cards.append({
                "type": "steady_operator",
                "label": "Voorzichtig stabiel gedrag",
                "confidence": "low",
                "summary": "Ik zie nog geen zwaar gedragsrisico in je recente Finn-activiteit, maar de historie is nog beperkt.",
                "evidence": [f"{metrics['actions_30d']} acties in {days_observed} dag(en)"],
            })

        merged_metrics = {**(behavioral.get("metrics") or {}), **metrics}
        merged_patterns = list(dict.fromkeys((behavioral.get("patterns") or []) + [card["type"] for card in memory_cards]))
        previous_delta = metrics["actions_30d"] - metrics["previous_actions_30d"]
        risk_flags = self._behavioral_risk_flags(merged_metrics, merged_patterns)
        habit_cards = self._behavioral_habit_cards(merged_metrics, merged_patterns)
        trend = self._behavioral_month_over_month(metrics)
        return {
            "status": status,
            "period": "last_30_days",
            "advice_only": True,
            "metrics": metrics,
            "memory_cards": memory_cards,
            "behavioral_profile": self._behavioral_profile_from_metrics(merged_metrics, merged_patterns),
            "trend": trend,
            "risk_flags": risk_flags,
            "habit_cards": habit_cards,
            "behavioral_balance_score": self._behavioral_balance_score(merged_metrics, merged_patterns),
            "month_over_month": {
                "current_actions": metrics["actions_30d"],
                "previous_actions": metrics["previous_actions_30d"],
                "delta": previous_delta,
                "summary": (
                    "nog geen vorige 30-dagen baseline."
                    if metrics["previous_actions_30d"] == 0 else
                    f"{abs(previous_delta)} acties {'meer' if previous_delta > 0 else 'minder' if previous_delta < 0 else 'evenveel'} dan de vorige 30 dagen."
                ),
            },
            "memory_policy": {
                "source": "ai_pending_actions",
                "stores_new_memory": False,
                "rule": "Finn mag alleen patronen noemen die door audit-events worden ondersteund.",
                "not_enough_for": [
                    "performance-koppeling zonder PnL/result-data",
                    "revenge-trading zonder verliescontext",
                    "persoonlijkheidslabels zonder langere historie",
                ],
            },
            "evidence": self._weekly_reflection_evidence(items_30d[:10]),
            "safe_next_step": (
                "Blijf Mission Control gebruiken en laat Finn overrides, skips en reviews vastleggen; daarna kan dit profiel sterker worden."
                if status != "memory_ready" else
                "Gebruik dit memory-profiel als frictielaag: bij vergelijkbare signalen moet Finn vertragen, niet versnellen."
            ),
        }

    def _behavioral_memory_message(self, memory: Dict[str, Any]) -> str:
        metrics = memory.get("metrics") or {}
        lines = [
            "Gedragsrapport op basis van je echte Finn-activiteit van de laatste 30 dagen.",
            (
                "Status: nog te weinig bewijs voor lange-termijn conclusies."
                if memory.get("status") == "not_enough_data" else
                "Status: eerste behavioral memory-profiel beschikbaar."
                if memory.get("status") == "early_memory" else
                "Status: behavioral memory is bruikbaar als risk-officer context."
            ),
            (
                "30-dagen metrics: "
                f"{metrics.get('actions_30d', 0)} acties, "
                f"{metrics.get('bot_decisions_generated_30d', 0)} bot-decisions, "
                f"{metrics.get('configuration_changes_30d', 0)} configuratiewijzigingen, "
                f"{metrics.get('plan_deviation_events_30d', 0)} plan-afwijking events, "
                f"{metrics.get('decision_churn_events_30d', 0)} decision-churn events."
            ),
        ]
        mom = memory.get("month_over_month") or {}
        if mom.get("summary"):
            lines.append(f"Vergeleken met vorige periode: {mom.get('summary')}")
        profile = memory.get("behavioral_profile") or {}
        if profile.get("label"):
            lines.append(f"Profiel: {profile.get('label')} - {profile.get('summary')}")
        trend = memory.get("trend") or {}
        if trend.get("summary"):
            lines.append(f"Trend over meerdere weken: {trend.get('summary')}")
        cards = memory.get("memory_cards") or []
        if cards:
            lines.append("Wat Finn voorzichtig mag onthouden:")
            for card in cards[:4]:
                lines.append(f"- {card.get('label')}: {card.get('summary')} ({card.get('confidence')} confidence)")
        risk_flags = memory.get("risk_flags") or []
        if risk_flags:
            lines.append("Waar Finn extra frictie moet houden:")
            for flag in risk_flags[:3]:
                lines.append(f"- {flag.get('label')}: {flag.get('summary')}")
        habit_cards = memory.get("habit_cards") or []
        if habit_cards:
            lines.append("Wat Finn al als werkstijl ziet:")
            for card in habit_cards[:3]:
                lines.append(f"- {card.get('label')}: {card.get('summary')}")
        if memory.get("memory_pattern"):
            lines.append(
                "Memory V2 patroon: "
                f"{memory.get('memory_pattern')} "
                f"({memory.get('confidence_level')} confidence, {memory.get('supporting_evidence_count', 0)} signalen, {memory.get('time_window')})."
            )
        if memory.get("behavioral_cost"):
            lines.append(f"Geschatte gedragskost: {memory.get('behavioral_cost')}")
        if memory.get("recommended_rule"):
            lines.append(f"Aanbevolen regel: {memory.get('recommended_rule')}")
        evidence = memory.get("supporting_evidence") or []
        if evidence:
            lines.append("Waarom Finn dit onthoudt:")
            for item in evidence[:3]:
                lines.append(f"- {item}")
        policy = memory.get("memory_policy") or {}
        not_enough = policy.get("not_enough_for") or []
        if not_enough:
            lines.append("Wat Finn nog niet mag concluderen:")
            lines.extend([f"- {item}" for item in not_enough[:3]])
        lines.append(f"Veilige volgende stap: {memory.get('safe_next_step')}")
        return "\n".join([line for line in lines if line])

    def _behavioral_balance_score(self, metrics: Dict[str, Any], patterns: List[str]) -> Optional[int]:
        meaningful_patterns = [pattern for pattern in (patterns or []) if pattern != "discipline_neutral"]
        enough = (
            (metrics.get("actions_7d", 0) >= 3)
            or (metrics.get("actions_30d", 0) >= 8)
            or bool(meaningful_patterns)
            or (int(metrics.get("skipped_7d", 0) or 0) + int(metrics.get("snoozed_7d", 0) or 0) + int(metrics.get("monitor_7d", 0) or 0) >= 2)
        )
        if not enough:
            return None

        score = 74
        score -= min(18, int(metrics.get("decision_churn_events_7d", 0) or 0) * 8)
        score -= min(16, int(metrics.get("execution_pressure_events_7d", 0) or 0) * 7)
        score -= min(12, int(metrics.get("possible_overrides_7d", 0) or 0) * 5)
        score -= 8 if "possible_fomo" in patterns else 0
        score -= 6 if "configuration_churn" in patterns else 0
        score += min(10, int(metrics.get("skipped_7d", 0) or 0) * 3)
        score += min(8, int(metrics.get("snoozed_7d", 0) or 0) * 2)
        score += 4 if "disciplined_waiting" in patterns else 0
        score += 3 if int(metrics.get("monitor_7d", 0) or 0) > 0 else 0
        return max(35, min(92, score))

    def _behavioral_risk_flags(self, metrics: Dict[str, Any], patterns: List[str]) -> List[Dict[str, Any]]:
        flags: List[Dict[str, Any]] = []
        decisions_7d = int(metrics.get("bot_decisions_generated_7d") or 0)
        paper_7d = int(metrics.get("paper_executions_7d") or 0)
        live_preflights_7d = int(metrics.get("live_preflights_7d") or 0)
        overrides_7d = int(metrics.get("possible_overrides_7d") or 0)
        decision_churn_7d = int(metrics.get("decision_churn_events_7d") or 0)
        execution_pressure_7d = int(metrics.get("execution_pressure_events_7d") or 0)
        configuration_7d = int(metrics.get("configuration_changes_7d") or 0)
        configuration_30d = int(metrics.get("configuration_changes_30d") or 0)
        pending_today = int(metrics.get("pending_today") or 0)
        blocked_context_7d = int(metrics.get("blocked_context_events_7d") or 0)

        if decisions_7d >= 6 or (decision_churn_7d >= 1 and paper_7d + live_preflights_7d >= 2):
            flags.append({
                "id": "overtrading_pressure",
                "label": "Overtrading-druk",
                "severity": "high" if decisions_7d >= 8 else "medium",
                "summary": "Je zoekt relatief vaak nieuwe decisions of execution-routes in korte tijd. Finn moet hier meer vertragen dan versnellen.",
                "safe_counter_move": "Rond eerst open review of monitor-items af voordat je nieuwe decision-requests doet.",
                "evidence": [
                    f"{decisions_7d} bot-decisions in 7 dagen",
                    f"{paper_7d + live_preflights_7d} execution-intentie events in 7 dagen",
                ],
            })
        if "possible_fomo" in patterns:
            flags.append({
                "id": "fomo_pressure",
                "label": "FOMO-druk",
                "severity": "medium",
                "summary": "Er zijn signalen van beslisdruk op dezelfde dag als execution-intentie. Finn moet hier extra context en wachttijd afdwingen.",
                "safe_counter_move": "Gebruik eerst portfolio review of Mission Control voordat je opnieuw op dezelfde dag execution zoekt.",
                "evidence": [
                    f"{int(metrics.get('bot_decisions_generated') or 0)} bot-decisions vandaag",
                    f"{int(metrics.get('paper_executions') or 0) + int(metrics.get('live_preflights') or 0)} execution-intentie events vandaag",
                ],
            })
        if overrides_7d > 0 or execution_pressure_7d > 0:
            flags.append({
                "id": "execution_pressure",
                "label": "Execution pressure",
                "severity": "high" if overrides_7d >= 2 or execution_pressure_7d >= 2 else "medium",
                "summary": "Er is recente guardrail-frictie rond execution. Finn hoort hier risk-officer te blijven, niet versnellen.",
                "safe_counter_move": "Pak eerst de reden van de guardrail op en laat execution pas terugkomen als het blok echt weg is.",
                "evidence": [
                    f"{overrides_7d} override-/druksignalen in 7 dagen",
                    f"{execution_pressure_7d} execution-pressure events in 7 dagen",
                ],
            })
        if configuration_7d >= 6 or configuration_30d >= 10:
            flags.append({
                "id": "configuration_drift",
                "label": "Configuratie-drift",
                "severity": "medium",
                "summary": "Je systeem beweegt veel. Finn moet vaker vragen of dit verfijning is of een richtingwissel onder druk.",
                "safe_counter_move": "Werk in kleine iteraties en laat één wijzigingsronde landen voordat je weer execution of nieuwe bots zoekt.",
                "evidence": [
                    f"{configuration_7d} configuratiewijzigingen in 7 dagen",
                    f"{configuration_30d} configuratiewijzigingen in 30 dagen",
                ],
            })
        if blocked_context_7d > 0 and execution_pressure_7d > 0:
            flags.append({
                "id": "frustration_pressure",
                "label": "Frustratie na blokkade",
                "severity": "medium",
                "summary": "Ik zie execution-druk terwijl setup of data blokkeerde. Dat is een nuttige guardrail-situatie, geen groen licht.",
                "safe_counter_move": "Los eerst de blokkade op; Finn mag hier geen revenge-achtig gedrag suggereren zonder resultaatdata.",
                "evidence": [
                    f"{blocked_context_7d} event(s) met blokkerende setup/data-context",
                    f"{execution_pressure_7d} execution-pressure events in 7 dagen",
                ],
            })
        if pending_today >= 3:
            flags.append({
                "id": "review_backlog",
                "label": "Review-backlog",
                "severity": "low",
                "summary": "Er staan meerdere open acties tegelijk. Finn moet de cockpit eerst schoonhouden voordat er nieuwe beslisdruk bijkomt.",
                "safe_counter_move": "Werk eerst de bovenste open acties af of snooze bewust wat niet voor vandaag is.",
                "evidence": [f"{pending_today} open Finn-acties vandaag"],
            })

        return flags[:4]

    def _behavioral_habit_cards(self, metrics: Dict[str, Any], patterns: List[str]) -> List[Dict[str, Any]]:
        cards: List[Dict[str, Any]] = []
        waiting_total_7d = int(metrics.get("skipped_7d") or 0) + int(metrics.get("snoozed_7d") or 0) + int(metrics.get("monitor_7d") or 0)
        review_actions_30d = int(metrics.get("review_actions_30d") or 0)
        overrides_7d = int(metrics.get("possible_overrides_7d") or 0)
        decisions_7d = int(metrics.get("bot_decisions_generated_7d") or 0)
        config_30d = int(metrics.get("configuration_changes_30d") or 0)
        pending_today = int(metrics.get("pending_today") or 0)

        if waiting_total_7d >= 2 or "disciplined_waiting" in patterns:
            cards.append({
                "id": "disciplined_waiting",
                "label": "Bewust wachten",
                "status": "strength",
                "summary": "Je gebruikt skip, snooze of monitor als echte frictie in plaats van direct door te drukken.",
            })
        if review_actions_30d >= 4 or waiting_total_7d >= 3:
            cards.append({
                "id": "review_anchored",
                "label": "Review-gedreven operator",
                "status": "strength",
                "summary": "Je laat Finn relatief vaak review- en resolve-werk vastleggen voordat je verder gaat.",
            })
        if config_30d >= 6 and overrides_7d == 0:
            cards.append({
                "id": "measured_iteration",
                "label": "Meetbare iteratie",
                "status": "neutral",
                "summary": "Je verandert best veel aan je systeem, maar zonder veel override-druk. Dat wijst eerder op zoeken naar fit dan op puur impulsief gedrag.",
            })
        if decisions_7d >= 6 and waiting_total_7d <= 1:
            cards.append({
                "id": "momentum_bias",
                "label": "Momentum-bias",
                "status": "watch",
                "summary": "Je ritme helt richting opnieuw beslissen in plaats van eerst reviewen. Finn moet daar frictie blijven toevoegen.",
            })
        if pending_today >= 3:
            cards.append({
                "id": "cockpit_overload",
                "label": "Cockpit wordt vol",
                "status": "watch",
                "summary": "Open acties stapelen zich op. Een volle cockpit verhoogt de kans op reactief gedrag.",
            })

        return cards[:4]

    def _behavioral_month_over_month(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        current = int(metrics.get("actions_30d") or 0)
        previous = int(metrics.get("previous_actions_30d") or 0)
        delta = current - previous
        if previous == 0:
            status = "early_baseline"
            summary = "Nog geen sterke vorige 30-dagen baseline; Finn bouwt hier nu pas langere geheugencontext op."
        elif delta > 6:
            status = "ramping_up"
            summary = f"Je Finn-activiteit ligt {delta} acties hoger dan de vorige 30 dagen. Kijk of dat gecontroleerde groei is of extra druk."
        elif delta < -6:
            status = "cooling_down"
            summary = f"Je Finn-activiteit ligt {abs(delta)} acties lager dan de vorige 30 dagen. Dat kan rustiger gedrag zijn, of simpelweg minder handelsdruk."
        else:
            status = "steady"
            summary = "Je 30-dagenritme ligt dicht bij de vorige periode. Geen grote gedragsverschuiving zichtbaar."
        return {
            "period": "last_30_days_vs_previous_30_days",
            "status": status,
            "current": current,
            "previous": previous,
            "delta": delta,
            "summary": summary,
        }

    def _finn_report_period_from_query(self, query: str) -> Dict[str, Any]:
        q = (query or "").lower()
        if any(term in q for term in [
            "dagafsluiting", "dag afsluiting", "einde dag", "sluit mijn dag af",
            "close mijn dag", "day close", "dag sluiten", "wat staat morgen",
        ]):
            return {"key": "day_close", "days": 1, "label": "dagafsluiting vandaag", "mode": "day_close"}
        if any(term in q for term in ["30 dagen", "maand", "monthly", "maandrapport"]):
            return {"key": "last_30_days", "days": 30, "label": "laatste 30 dagen", "mode": "reflection"}
        if any(term in q for term in ["week", "weekly", "7 dagen"]):
            return {"key": "last_7_days", "days": 7, "label": "laatste 7 dagen", "mode": "reflection"}
        return {"key": "today", "days": 1, "label": "vandaag", "mode": "reflection"}

    def _humanize_finn_activity_type(self, action_type: str) -> str:
        labels = {
            "create_plan": "Plan of setup gemaakt",
            "create_strategy": "Strategy aangepast",
            "create_bot": "Bot aangemaakt",
            "bot_config_update": "Bot bijgewerkt",
            "configure_indicator": "Indicator aangepast",
            "generate_bot_decision": "Bot-decision gegenereerd",
            "skip_bot_decision": "Bot-decision overgeslagen",
            "paper_execute_bot_decision": "Paper execution uitgevoerd",
            "live_preflight_bot_decision": "Live decision preflight gedaan",
            "live_manual_order_preflight": "Live order preflight gedaan",
            "live_manual_order_confirmed": "Live manual order bevestigd",
            "live_manual_order_blocked": "Live manual order geblokkeerd",
            "live_setup_block_acknowledged": "Geblokkeerde setup bewust bevestigd",
            "resolve_mission_item": "Mission Control item afgehandeld",
            "snooze_mission_item": "Mission Control item later gezet",
            "agent_controller_handoff": "Controller-handoff gevolgd",
        }
        if action_type in labels:
            return labels[action_type]
        return str(action_type or "Finn-actie").replace("_", " ").strip().capitalize()

    def _build_report_activity_journal(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        relevant = []
        for item in items:
            action_type = str(item.get("type") or "")
            if action_type in {
                "create_plan",
                "create_strategy",
                "create_bot",
                "bot_config_update",
                "configure_indicator",
                "generate_bot_decision",
                "skip_bot_decision",
                "paper_execute_bot_decision",
                "live_preflight_bot_decision",
                "live_manual_order_preflight",
                "live_manual_order_confirmed",
                "resolve_mission_item",
                "snooze_mission_item",
                "agent_controller_handoff",
            }:
                relevant.append(
                    {
                        "type": action_type,
                        "label": item.get("label") or self._humanize_finn_activity_type(action_type),
                        "asset": item.get("asset"),
                        "status": item.get("status"),
                        "resolve_state": item.get("resolve_state"),
                        "created_at": item.get("created_at"),
                    }
                )
        return {
            "title": "Wat heb ik gedaan?",
            "summary": (
                f"{len(relevant)} bewuste Finn-actie(s) vastgelegd."
                if relevant else
                "Nog weinig expliciete Finn-acties vastgelegd in deze periode."
            ),
            "entries": relevant[:8],
        }

    def _build_report_blocked_summary(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        blocked_entries = []
        for item in items:
            action_type = str(item.get("type") or "")
            behavioral_event = item.get("behavioral_event") if isinstance(item.get("behavioral_event"), dict) else {}
            if action_type in {
                "live_manual_order_blocked",
                "live_setup_block_acknowledged",
                "blocked_plan",
                "blocker_explanation",
            } or behavioral_event.get("type") in {
                "plan_deviation_attempt",
                "strategy_change_pressure",
                "decision_churn",
                "execution_pressure",
            }:
                blocked_entries.append(
                    {
                        "type": action_type or behavioral_event.get("type"),
                        "label": item.get("label") or self._humanize_finn_activity_type(action_type or behavioral_event.get("type")),
                        "asset": item.get("asset"),
                        "outcome": item.get("outcome") or behavioral_event.get("message") or behavioral_event.get("type"),
                        "severity": behavioral_event.get("severity") or item.get("severity") or "medium",
                        "created_at": item.get("created_at"),
                    }
                )
        return {
            "title": "Wat heeft Finn geblokkeerd?",
            "summary": (
                f"Finn heeft {len(blocked_entries)} keer actief afgeremd, geblokkeerd of extra frictie toegevoegd."
                if blocked_entries else
                "In deze periode hoefde Finn niets hard af te remmen."
            ),
            "entries": blocked_entries[:8],
        }

    def _build_report_plan_adherence(self, items: List[Dict[str, Any]], metrics: Dict[str, Any]) -> Dict[str, Any]:
        deviations = []
        for item in items:
            behavioral_event = item.get("behavioral_event") if isinstance(item.get("behavioral_event"), dict) else None
            if not behavioral_event:
                continue
            event_type = behavioral_event.get("type")
            if event_type not in {"plan_deviation_attempt", "strategy_change_pressure", "decision_churn", "execution_pressure"}:
                continue
            deviations.append(
                {
                    "type": event_type,
                    "label": item.get("label") or self._humanize_finn_activity_type(item.get("type") or event_type),
                    "asset": item.get("asset"),
                    "message": behavioral_event.get("message") or behavioral_event.get("type"),
                    "severity": behavioral_event.get("severity") or "medium",
                    "created_at": item.get("created_at"),
                }
            )

        if deviations:
            status = "attention"
            summary = f"Ik zag {len(deviations)} moment(en) waarop je van plan, reviewvolgorde of execution-discipline wilde afwijken."
        elif metrics.get("skipped", 0) or metrics.get("monitor_today", 0):
            status = "disciplined"
            summary = "Je week af zonder te forceren: Finn logde vooral bewust wachten, monitoren of overslaan."
        else:
            status = "steady"
            summary = "Ik zie geen duidelijke plan-afwijkingen in deze periode."

        return {
            "title": "Waar week ik af?",
            "status": status,
            "summary": summary,
            "entries": deviations[:6],
            "skipped": metrics.get("skipped", 0),
            "monitor_today": metrics.get("monitor_today", 0),
            "snoozed": metrics.get("snoozed", 0),
        }

    def _build_finn_day_close(
        self,
        items: List[Dict[str, Any]],
        metrics: Dict[str, Any],
        interventions: List[Dict[str, Any]],
        agent_rhythm: Optional[Dict[str, Any]] = None,
        operating_rules: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        handled_count = (
            metrics.get("resolved", 0)
            + metrics.get("skipped", 0)
            + metrics.get("snoozed", 0)
            + metrics.get("monitor_today", 0)
        )
        carryover_count = metrics.get("pending", 0) + metrics.get("waiting_for_data", 0)
        if metrics.get("failed", 0) > 0 or metrics.get("live_order_blocks", 0) > 0:
            closeout_status = "review_before_tomorrow"
        elif carryover_count > 0:
            closeout_status = "carryover"
        elif metrics.get("actions", 0) == 0:
            closeout_status = "quiet_day"
        else:
            closeout_status = "closed"

        completed = []
        if metrics.get("plans_created", 0):
            completed.append(f"{metrics.get('plans_created')} plan/setup flow(s) uitgevoerd")
        if metrics.get("strategies_changed", 0):
            completed.append(f"{metrics.get('strategies_changed')} strategy-wijziging(en)")
        if metrics.get("bots_changed", 0):
            completed.append(f"{metrics.get('bots_changed')} bot-wijziging(en)")
        if metrics.get("indicators_changed", 0):
            completed.append(f"{metrics.get('indicators_changed')} indicator-wijziging(en)")
        if metrics.get("bot_decisions_generated", 0):
            completed.append(f"{metrics.get('bot_decisions_generated')} bot-decision(s) gegenereerd")
        if metrics.get("live_order_preflights", 0):
            completed.append(f"{metrics.get('live_order_preflights')} live order preflight(s)")
        if not completed and metrics.get("actions", 0):
            completed.append(f"{metrics.get('actions')} Finn-actie(s) vastgelegd")

        consciously_handled = []
        if metrics.get("resolved", 0):
            consciously_handled.append(f"{metrics.get('resolved')} item(s) gemarkeerd als klaar")
        if metrics.get("skipped", 0):
            consciously_handled.append(f"{metrics.get('skipped')} item(s) bewust overgeslagen")
        if metrics.get("snoozed", 0):
            consciously_handled.append(f"{metrics.get('snoozed')} item(s) later opnieuw bekijken")
        if metrics.get("monitor_today", 0):
            consciously_handled.append(f"{metrics.get('monitor_today')} item(s) vandaag gemonitord")

        blocked = [
            {
                "type": item.get("type"),
                "label": item.get("label"),
                "asset": item.get("asset"),
                "outcome": item.get("outcome"),
                "created_at": item.get("created_at"),
            }
            for item in items
            if item.get("type") in {
                "live_manual_order_blocked",
                "live_setup_block_acknowledged",
            } or isinstance(item.get("behavioral_event"), dict)
        ][:8]

        tomorrow_focus = []
        if metrics.get("pending", 0):
            tomorrow_focus.append("Rond pending Finn-acties of bot-reviews eerst af.")
        if metrics.get("waiting_for_data", 0):
            tomorrow_focus.append("Ververs ontbrekende data voordat je nieuwe execution beoordeelt.")
        if metrics.get("live_order_blocks", 0):
            tomorrow_focus.append("Review waarom live orders geblokkeerd werden voordat je opnieuw preflight doet.")
        if metrics.get("plan_deviation_events", 0):
            tomorrow_focus.append("Controleer of de bewuste plan-afwijking nog steeds bij je setup past.")
        if metrics.get("decision_churn_events", 0):
            tomorrow_focus.append("Voorkom morgen nieuwe decisions voordat open reviews zijn afgehandeld.")
        if agent_rhythm and agent_rhythm.get("status") == "ready":
            tomorrow_focus.extend(agent_rhythm.get("tomorrow_focus") or [])
        if not tomorrow_focus:
            tomorrow_focus.append("Start morgen met Mission Control en werk de queue van boven naar beneden af.")

        activity_journal = self._build_report_activity_journal(items)
        blocked_summary = self._build_report_blocked_summary(items)
        adherence = self._build_report_plan_adherence(items, metrics)

        return {
            "status": closeout_status,
            "handled_count": handled_count,
            "carryover_count": carryover_count,
            "completed": completed,
            "consciously_handled": consciously_handled,
            "blocked_or_slowed": blocked,
            "risk_officer_interventions": interventions,
            "agent_rhythm": agent_rhythm or {},
            "operating_rules": operating_rules or {},
            "what_i_did_today": activity_journal,
            "what_finn_blocked": blocked_summary,
            "where_i_deviated": adherence,
            "tomorrow_focus": tomorrow_focus,
            "closing_line": (
                "Niet meer forceren vandaag; begin morgen met review van de open punten."
                if closeout_status in {"review_before_tomorrow", "carryover"} else
                "Dag netjes afgesloten; morgen opnieuw starten vanuit Mission Control."
                if closeout_status == "closed" else
                "Rustige dag: er is nog weinig Finn-activiteit om af te sluiten."
            ),
        }

    def _build_finn_reflection_report(
        self,
        activity_feed: List[Dict[str, Any]],
        behavioral: Dict[str, Any],
        query: str,
    ) -> Dict[str, Any]:
        period = self._finn_report_period_from_query(query)
        now = _utc_now()
        cutoff = now - timedelta(days=period["days"])
        items = []
        for item in activity_feed or []:
            created_at = self._parse_mission_timestamp(item.get("created_at"))
            if not created_at:
                continue
            if period["key"] in {"today", "day_close"}:
                if created_at.date() == now.date():
                    items.append(item)
            elif created_at >= cutoff:
                items.append(item)

        def count_type(action_type: str) -> int:
            return len([item for item in items if item.get("type") == action_type])

        def count_resolution(resolve_state: str) -> int:
            return len([item for item in items if item.get("resolve_state") == resolve_state])

        behavioral_events = [
            item.get("behavioral_event") for item in items
            if isinstance(item.get("behavioral_event"), dict)
        ]
        agent_accountability_events = [
            item.get("agent_accountability") for item in items
            if isinstance(item.get("agent_accountability"), dict)
        ]
        event_counts: Dict[str, int] = {}
        for event in behavioral_events:
            event_type = str(event.get("type") or "unknown")
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

        metrics = {
            "actions": len(items),
            "executed": len([item for item in items if item.get("status") == "executed"]),
            "pending": len([item for item in items if item.get("status") == "pending"]),
            "failed": len([item for item in items if item.get("status") == "failed"]),
            "resolved": count_resolution("resolved"),
            "skipped": count_resolution("skipped"),
            "snoozed": count_resolution("snoozed"),
            "monitor_today": count_resolution("monitor_today"),
            "waiting_for_data": count_resolution("waiting_for_data"),
            "plans_created": count_type("create_plan"),
            "strategies_changed": count_type("create_strategy"),
            "bots_changed": count_type("create_bot") + count_type("bot_config_update"),
            "indicators_changed": count_type("configure_indicator"),
            "bot_decisions_generated": count_type("generate_bot_decision"),
            "bot_decisions_skipped": count_type("skip_bot_decision"),
            "paper_executions": count_type("paper_execute_bot_decision"),
            "live_preflights": count_type("live_preflight_bot_decision"),
            "live_order_preflights": count_type("live_manual_order_preflight"),
            "live_order_blocks": count_type("live_manual_order_blocked"),
            "live_orders_confirmed": count_type("live_manual_order_confirmed"),
            "live_setup_block_acks": count_type("live_setup_block_acknowledged"),
            "agent_controller_handoffs": count_type("agent_controller_handoff"),
            "mission_items_resolved": count_type("resolve_mission_item"),
            "mission_items_snoozed": count_type("snooze_mission_item"),
            "behavioral_events": len(behavioral_events),
            "agent_accountability_events": len(agent_accountability_events),
            "agent_accountability_by_agent": self._agent_accountability_counts(agent_accountability_events),
            "agent_performance_light": self._agent_performance_light(items),
            "plan_deviation_events": event_counts.get("plan_deviation_attempt", 0) + event_counts.get("strategy_change_pressure", 0),
            "decision_churn_events": event_counts.get("decision_churn", 0),
            "execution_pressure_events": event_counts.get("execution_pressure", 0),
        }
        agent_rhythm = self._agent_rhythm_from_learning(metrics["agent_performance_light"])
        if period["key"] in {"today", "day_close"}:
            metrics.update({
                "actions_today": metrics["actions"],
                "executed_today": metrics["executed"],
                "pending_today": metrics["pending"],
                "skipped_today": metrics["skipped"],
                "snoozed_today": metrics["snoozed"],
                "monitor_today_count": metrics["monitor_today"],
                "plan_deviation_events_today": metrics["plan_deviation_events"],
                "decision_churn_events_today": metrics["decision_churn_events"],
                "execution_pressure_events_today": metrics["execution_pressure_events"],
                "live_order_blocks_today": metrics["live_order_blocks"],
            })

        interventions = []
        if metrics["plan_deviation_events"] > 0:
            interventions.append({
                "type": "plan_deviation",
                "label": "Plan-afwijking afgeremd",
                "count": metrics["plan_deviation_events"],
                "meaning": "Finn heeft je laten bevestigen dat je bewust van je plan wilde afwijken.",
            })
        if metrics["decision_churn_events"] > 0:
            interventions.append({
                "type": "decision_churn",
                "label": "Decision-churn afgeremd",
                "count": metrics["decision_churn_events"],
                "meaning": "Finn zag herhaald nieuwe bot-decisions aanvragen terwijl review nog open stond.",
            })
        if metrics["execution_pressure_events"] > 0:
            interventions.append({
                "type": "execution_pressure",
                "label": "Execution pressure afgeremd",
                "count": metrics["execution_pressure_events"],
                "meaning": "Finn zag execution-druk of live/manual risico en voegde frictie toe.",
            })
        if metrics["live_order_blocks"] > 0:
            interventions.append({
                "type": "live_order_blocked",
                "label": "Live order geblokkeerd",
                "count": metrics["live_order_blocks"],
                "meaning": "De live execution guardrails hebben een manual order tegengehouden.",
            })
        if metrics["live_setup_block_acks"] > 0:
            interventions.append({
                "type": "setup_block_ack",
                "label": "Geblokkeerde setup bewust bevestigd",
                "count": metrics["live_setup_block_acks"],
                "meaning": "Je hebt expliciet bevestigd dat je een live order bij een geblokkeerde setup wilde blijven beoordelen.",
            })
        if metrics["agent_controller_handoffs"] > 0:
            interventions.append({
                "type": "agent_controller_handoff",
                "label": "Agent-handoff gevolgd",
                "count": metrics["agent_controller_handoffs"],
                "meaning": "Je hebt een door Finn Controller gekozen primaire agent-actie gevolgd.",
            })
        if metrics["skipped"] + metrics["snoozed"] + metrics["monitor_today"] > 0:
            interventions.append({
                "type": "disciplined_waiting",
                "label": "Bewust wachten vastgelegd",
                "count": metrics["skipped"] + metrics["snoozed"] + metrics["monitor_today"],
                "meaning": "Je hebt items bewust overgeslagen, gemonitord of later gezet.",
            })
        operating_rules = self._personal_operating_rules(agent_rhythm, metrics, interventions)

        configuration_total = (
            metrics["plans_created"]
            + metrics["strategies_changed"]
            + metrics["bots_changed"]
            + metrics["indicators_changed"]
        )
        sections = {
            "operator_summary": {
                "title": "Operator samenvatting",
                "items": [
                    f"{metrics['actions']} Finn-acties in {period['label']}",
                    f"{metrics['executed']} uitgevoerd, {metrics['pending']} nog pending, {metrics['failed']} mislukt",
                    f"{metrics['resolved']} resolved, {metrics['skipped']} skipped, {metrics['snoozed']} later gezet",
                ],
            },
            "configuration": {
                "title": "Systeemwijzigingen",
                "items": [
                    f"{metrics['plans_created']} plannen",
                    f"{metrics['strategies_changed']} strategy-wijzigingen",
                    f"{metrics['bots_changed']} bot-wijzigingen",
                    f"{metrics['indicators_changed']} indicator-wijzigingen",
                ],
                "total": configuration_total,
            },
            "decision_review": {
                "title": "Decision & review",
                "items": [
                    f"{metrics['bot_decisions_generated']} bot-decisions gegenereerd",
                    f"{metrics['bot_decisions_skipped']} bot-decisions overgeslagen",
                    f"{metrics['paper_executions']} paper executions",
                    f"{metrics['live_preflights']} live decision preflights",
                    f"{metrics['live_order_preflights']} live order preflights",
                    f"{metrics['live_order_blocks']} live order blokkades",
                    f"{metrics['live_orders_confirmed']} live manual orders",
                ],
            },
            "guardrails": {
                "title": "Finn guardrails",
                "items": interventions,
            },
            "agent_accountability": {
                "title": "Agent accountability",
                "items": [
                    f"{metrics['agent_controller_handoffs']} controller-handoff(s) gevolgd",
                    f"{metrics['agent_accountability_events']} agent-accountability event(s)",
                ],
                "by_agent": metrics.get("agent_accountability_by_agent") or {},
                "performance_light": metrics.get("agent_performance_light") or {},
                "agent_rhythm": agent_rhythm,
                "operating_rules": operating_rules,
            },
            "activity_journal": self._build_report_activity_journal(items),
            "blocked_summary": self._build_report_blocked_summary(items),
            "plan_adherence": self._build_report_plan_adherence(items, metrics),
        }

        if not items:
            status = "empty"
            headline = "Ik heb voor deze periode nog geen Finn-activiteit om te rapporteren."
            safe_next_step = "Gebruik Mission Control vandaag; daarna kan Finn een echt operatorrapport maken."
        elif interventions:
            status = "attention"
            headline = "Finn heeft deze periode echte frictie- en disciplinepunten vastgelegd."
            safe_next_step = "Review eerst de open queue en rond pending bot-decisions af voordat je nieuwe decisions maakt."
        elif configuration_total >= 4:
            status = "configuration_heavy"
            headline = "Je hebt vooral aan je systeem gebouwd of aangepast."
            safe_next_step = "Laat Finn controleren of deze wijzigingen nog bij je oorspronkelijke plan passen."
        else:
            status = "steady"
            headline = "Je Finn-activiteit oogt beheerst; ik zie geen zware guardrail-events in deze periode."
            safe_next_step = "Blijf Mission Control gebruiken als vaste review-queue."

        day_close = None
        if period.get("mode") == "day_close":
            day_close = self._build_finn_day_close(items, metrics, interventions, agent_rhythm, operating_rules)
            if day_close["status"] == "review_before_tomorrow":
                status = "day_close_attention"
                headline = "Dagafsluiting: er zijn risk-officer punten die je morgen eerst moet reviewen."
                safe_next_step = day_close["tomorrow_focus"][0]
            elif day_close["status"] == "carryover":
                status = "day_close_carryover"
                headline = "Dagafsluiting: er staan nog punten open voor morgen."
                safe_next_step = day_close["tomorrow_focus"][0]
            elif day_close["status"] == "closed":
                status = "day_close_closed"
                headline = "Dagafsluiting: je Finn-operatorlog is netjes afgerond voor vandaag."
                safe_next_step = day_close["tomorrow_focus"][0]

        agent_verdicts = self._build_report_agent_verdicts(metrics, interventions, behavioral)
        agent_controller = self._build_agent_controller(agent_verdicts, context="finn_report")
        agent_controller["primary_action"] = self._agent_controller_primary_action(
            agent_controller,
            [{
                "type": "chat_prompt",
                "label": "Open Mission Control",
                "prompt": "Open Mission Control",
                "handoff": "mission_control",
                "requires_confirmation": False,
            }],
        )

        return {
            "report_type": "finn_reflection_report",
            "report_family": "finn_reports",
            "separate_from": "daily_trading_report",
            "period": period,
            "report_mode": period.get("mode") or "reflection",
            "status": status,
            "headline": headline,
            "advice_only": True,
            "metrics": metrics,
            "sections": sections,
            "day_close": day_close,
            "agent_verdicts": agent_verdicts,
            "agent_controller": agent_controller,
            "agent_accountability": sections["agent_accountability"],
            "agent_learning": sections["agent_accountability"].get("performance_light") or {},
            "agent_rhythm": agent_rhythm,
            "operating_rules": operating_rules,
            "behavioral_profile": behavioral.get("metrics") and self._behavioral_profile_from_metrics(
                behavioral.get("metrics") or {},
                behavioral.get("patterns") or [],
            ),
            "risk_officer_interventions": interventions,
            "evidence": self._weekly_reflection_evidence(items[:12]),
            "source": {
                "primary": "ai_pending_actions",
                "derived_from": ["Mission Control activity", "behavioral events", "resolve states"],
                "stores_new_report": False,
                "does_not_use": "daily_reports market/trading narrative",
            },
            "safe_next_step": safe_next_step,
        }

    def _agent_accountability_counts(self, events: List[Dict[str, Any]]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for event in events or []:
            agent = str(event.get("dominant_agent") or "unknown")
            counts[agent] = counts.get(agent, 0) + 1
        return counts

    def _build_report_agent_verdicts(
        self,
        metrics: Dict[str, Any],
        interventions: List[Dict[str, Any]],
        behavioral: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        intervention_types = {item.get("type") for item in interventions}
        return [
            {
                "agent": "risk_agent",
                "label": "Risk Agent",
                "status": "intervened" if interventions else "quiet",
                "priority": "high" if interventions else "low",
                "reason": f"{len(interventions)} risk-officer interventie(s) in dit rapport." if interventions else "Geen zware guardrail-interventie in deze periode.",
                "evidence": {"intervention_types": sorted([item for item in intervention_types if item])},
                "next_action": "Review guardrail-events voordat je opnieuw uitvoert." if interventions else "Geen risk-review nodig.",
            },
            {
                "agent": "execution_agent",
                "label": "Execution Agent",
                "status": "blocked_activity" if metrics.get("live_order_blocks", 0) else "quiet",
                "priority": "high" if metrics.get("live_order_blocks", 0) else "low",
                "reason": f"{metrics.get('live_order_blocks', 0)} live order blokkade(s)." if metrics.get("live_order_blocks", 0) else "Geen live order blokkades.",
                "evidence": {
                    "live_order_preflights": metrics.get("live_order_preflights", 0),
                    "live_order_blocks": metrics.get("live_order_blocks", 0),
                    "live_orders_confirmed": metrics.get("live_orders_confirmed", 0),
                },
                "next_action": "Los execution blockers op voor nieuwe preflight." if metrics.get("live_order_blocks", 0) else "Blijf preflight verplicht gebruiken.",
            },
            {
                "agent": "memory_agent",
                "label": "Memory Agent",
                "status": behavioral.get("status") or "unknown",
                "priority": "medium" if behavioral.get("status") == "attention" else "low",
                "reason": "Behavioral patterns zijn meegenomen in dit Finn report.",
                "evidence": {
                    "patterns": behavioral.get("patterns") or [],
                    "behavioral_events": metrics.get("behavioral_events", 0),
                },
                "next_action": "Gebruik weekreflectie voor patroonduiding.",
            },
        ]

    def _finn_reflection_report_message(self, report: Dict[str, Any]) -> str:
        metrics = report.get("metrics") or {}
        period = report.get("period") or {}
        lines = [
            f"Finn rapport ({period.get('label', 'periode')}).",
            "Dit is een Finn operator-/disciplinerapport, los van je dagelijkse trading report.",
            report.get("headline") or "Ik heb nog geen stevige conclusie.",
            (
                "Operator-log: "
                f"{metrics.get('actions', 0)} acties, "
                f"{metrics.get('executed', 0)} uitgevoerd, "
                f"{metrics.get('pending', 0)} pending, "
                f"{metrics.get('skipped', 0)} skips, "
                f"{metrics.get('snoozed', 0)} later gezet."
            ),
            (
                "Systeemwijzigingen: "
                f"{metrics.get('plans_created', 0)} plannen, "
                f"{metrics.get('strategies_changed', 0)} strategies, "
                f"{metrics.get('bots_changed', 0)} bots, "
                f"{metrics.get('indicators_changed', 0)} indicators."
            ),
            (
                "Risk-officer events: "
                f"{metrics.get('plan_deviation_events', 0)} plan-afwijkingen, "
                f"{metrics.get('decision_churn_events', 0)} decision-churn, "
                f"{metrics.get('execution_pressure_events', 0)} execution-pressure."
            ),
        ]
        interventions = report.get("risk_officer_interventions") or []
        if interventions:
            lines.append("Wat Finn heeft afgeremd of vastgelegd:")
            for item in interventions[:4]:
                lines.append(f"- {item.get('label')}: {item.get('meaning')} ({item.get('count')}x)")
        else:
            lines.append("Finn heeft in deze periode geen zware guardrail-interventie gevonden.")
        personal_performance = report.get("personal_performance") or {}
        if personal_performance.get("performance_score") is not None:
            lines.append(
                "Personal performance: "
                f"{personal_performance.get('performance_score')}/100. "
                f"Groeidoel: {personal_performance.get('next_growth_target')}"
            )
        journal = report.get("trade_journal_intelligence") or {}
        if journal.get("journal_pattern"):
            lines.append(
                "Journal intelligence: "
                f"{journal.get('journal_pattern')} - {journal.get('decision_gap')}"
            )
        verdicts = report.get("agent_verdicts") or []
        if verdicts:
            lines.append("Agent-verdicts:")
            for verdict in verdicts[:4]:
                lines.append(f"- {verdict.get('label')}: {verdict.get('status')} - {verdict.get('reason')}")
        controller = report.get("agent_controller") or {}
        if controller.get("dominant_label"):
            lines.append(
                f"Finn Controller: eerst {controller.get('dominant_label')} volgen - {controller.get('reason')}"
            )
        accountability = report.get("agent_accountability") or {}
        if accountability.get("items"):
            lines.append("Agent accountability:")
            for item in accountability.get("items")[:3]:
                lines.append(f"- {item}")
            performance = accountability.get("performance_light") or {}
            if performance.get("summary"):
                lines.append(f"- Learning light: {performance.get('summary')}")
            rhythm = accountability.get("agent_rhythm") or report.get("agent_rhythm") or {}
            if rhythm.get("summary"):
                lines.append(f"- Agent-ritme: {rhythm.get('summary')}")
            rules = (accountability.get("operating_rules") or report.get("operating_rules") or {}).get("rules") or []
            if rules:
                lines.append("- Personal operating rules:")
                for rule in rules[:3]:
                    lines.append(f"  - {rule.get('title')}: {rule.get('rule')}")
        sections = report.get("sections") or {}
        if not report.get("day_close"):
            journal = sections.get("activity_journal") or {}
            if journal.get("summary"):
                lines.append(f"Wat heb ik gedaan? {journal.get('summary')}")
            blocked_summary = sections.get("blocked_summary") or {}
            if blocked_summary.get("summary"):
                lines.append(f"Wat heeft Finn geblokkeerd? {blocked_summary.get('summary')}")
            adherence = sections.get("plan_adherence") or {}
            if adherence.get("summary"):
                lines.append(f"Waar week ik af? {adherence.get('summary')}")
        day_close = report.get("day_close") or {}
        if day_close:
            lines.append("Dagafsluiting:")
            what_i_did = day_close.get("what_i_did_today") or {}
            if what_i_did.get("summary"):
                lines.append(f"Wat ik vandaag deed: {what_i_did.get('summary')}")
            completed = day_close.get("completed") or []
            if completed:
                lines.append("Vandaag afgerond:")
                lines.extend([f"- {item}" for item in completed[:5]])
            journal_entries = what_i_did.get("entries") or []
            if journal_entries:
                lines.append("Wat heb ik vandaag gedaan?")
                for item in journal_entries[:4]:
                    asset = f" ({item.get('asset')})" if item.get("asset") else ""
                    lines.append(f"- {item.get('label')}{asset}")
            handled = day_close.get("consciously_handled") or []
            if handled:
                lines.append("Bewust afgehandeld:")
                lines.extend([f"- {item}" for item in handled[:4]])
            blocked = day_close.get("blocked_or_slowed") or []
            if blocked:
                lines.append("Afgeremd of geblokkeerd:")
                for item in blocked[:4]:
                    asset = f" {item.get('asset')}" if item.get("asset") else ""
                    lines.append(f"- {item.get('label') or item.get('type')}{asset}: {item.get('outcome')}")
            blocked_summary = day_close.get("what_finn_blocked") or {}
            blocked_entries = blocked_summary.get("entries") or []
            if blocked_entries:
                lines.append("Wat heeft Finn geblokkeerd?")
                for item in blocked_entries[:4]:
                    asset = f" ({item.get('asset')})" if item.get("asset") else ""
                    detail = item.get("outcome") or item.get("label") or item.get("type")
                    lines.append(f"- {item.get('label') or item.get('type')}{asset}: {detail}")
            adherence = day_close.get("where_i_deviated") or {}
            if adherence.get("summary"):
                lines.append(f"Waar week ik af? {adherence.get('summary')}")
            adherence_entries = adherence.get("entries") or []
            if adherence_entries:
                for item in adherence_entries[:3]:
                    asset = f" ({item.get('asset')})" if item.get("asset") else ""
                    lines.append(f"- {item.get('label') or item.get('type')}{asset}: {item.get('message')}")
            rhythm = day_close.get("agent_rhythm") or {}
            if rhythm.get("summary"):
                lines.append("Agent-ritme voor morgen:")
                lines.append(f"- {rhythm.get('summary')}")
            tomorrow = day_close.get("tomorrow_focus") or []
            if tomorrow:
                lines.append("Meenemen naar morgen:")
                lines.extend([f"- {item}" for item in tomorrow[:4]])
            lines.append(day_close.get("closing_line"))
        lines.append(f"Veilige volgende stap: {report.get('safe_next_step')}")
        return "\n".join([line for line in lines if line])

    def _behavioral_profile_from_metrics(self, metrics: Dict[str, Any], patterns: List[str]) -> Dict[str, Any]:
        actions_7d = int(metrics.get("actions_7d") or 0)
        actions_30d = int(metrics.get("actions_30d") or 0)
        decision_churn_7d = int(metrics.get("decision_churn_events_7d") or 0)
        overrides_7d = int(metrics.get("possible_overrides_7d") or 0)
        live_preflights_7d = int(metrics.get("live_preflights_7d") or 0)
        paper_7d = int(metrics.get("paper_executions_7d") or 0)
        review_brakes_7d = int(metrics.get("skipped_7d") or 0) + int(metrics.get("snoozed_7d") or 0) + int(metrics.get("monitor_7d") or 0)
        configuration_7d = int(metrics.get("configuration_changes_7d") or 0)
        configuration_30d = int(metrics.get("configuration_changes_30d") or 0)

        if actions_7d < 3 and actions_30d < 8:
            return {
                "type": "insufficient_history",
                "label": "Nog te weinig historie",
                "summary": "Finn heeft meer review-, skip- en decision-data nodig voordat dit profiel stevig is.",
                "confidence": "low",
            }
        if overrides_7d >= 2 and decision_churn_7d >= 1 and (live_preflights_7d + paper_7d) >= 2:
            return {
                "type": "pressure_spiker",
                "label": "Drukpieken onder guardrails",
                "summary": "Je gedrag laat korte pieken zien waarin execution-druk, nieuwe decisions en guardrail-frictie samenkomen.",
                "confidence": "medium",
                "watch_for": "Laat Finn in piekmomenten eerst review of monitor afdwingen.",
            }
        if actions_7d >= 6 and decision_churn_7d >= 1 and review_brakes_7d <= 1:
            return {
                "type": "overtrading_risk",
                "label": "Overtrading-risico",
                "summary": "Je ritme helt richting opnieuw beslissen en execution zoeken zonder genoeg tegenwicht van review-frictie.",
                "confidence": "medium",
                "watch_for": "Meer beslissen is niet automatisch beter; bewaak review- en wachtritme.",
            }
        if overrides_7d > 0 or "execution_friction" in patterns:
            return {
                "type": "execution_pressure",
                "label": "Execution pressure",
                "summary": "Je week bevat signalen waarbij extra frictie rond execution verstandig blijft.",
                "confidence": "medium",
                "watch_for": "Finn moet hier risk-officer blijven, niet alleen facilitator.",
            }
        if configuration_30d >= 8 and overrides_7d == 0:
            return {
                "type": "exploratory_optimizer",
                "label": "Zoekt via iteratie",
                "summary": "Je leert zichtbaar via setup-, strategy- en bot-iteraties. Dat kan sterk zijn, zolang execution niet gaat rennen voor het plan uit.",
                "confidence": "medium",
                "watch_for": "Rond iteraties af voordat je nieuwe live frictie opzoekt.",
            }
        if review_brakes_7d >= 2 and overrides_7d == 0:
            return {
                "type": "review_anchored",
                "label": "Review-gedreven operator",
                "summary": "Je laat Finn relatief vaak review of vertraging toevoegen voordat je verder gaat. Dat is een gezonde operatorstijl.",
                "confidence": "medium",
            }
        if "decision_churn" in patterns:
            return {
                "type": "decision_heavy",
                "label": "Decision-heavy",
                "summary": "Je gebruikt Finn intensief voor decisions; bewaak dat dit geen herhaald zoeken naar bevestiging wordt.",
                "confidence": "medium",
            }
        if "configuration_churn" in patterns or configuration_7d >= 5:
            return {
                "type": "configuration_heavy",
                "label": "Veel configuratiebeweging",
                "summary": "Je bent je systeem veel aan het aanpassen; rond wijzigingen bewust af voordat je execution zoekt.",
                "confidence": "medium",
            }
        if "disciplined_waiting" in patterns:
            return {
                "type": "disciplined_waiting",
                "label": "Gedisciplineerd wachten",
                "summary": "Je laat Finn je helpen om niet elke open actie direct door te drukken.",
                "confidence": "medium",
            }
        return {
            "type": "steady_operator",
            "label": "Stabiele operator",
            "summary": "Geen duidelijke onrustsignalen in de recente Finn-activiteit.",
            "confidence": "low",
        }

    def _behavioral_week_over_week(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        comparisons = []
        for key, label in [
            ("actions_7d", "acties"),
            ("bot_decisions_generated_7d", "bot-decisions"),
            ("configuration_changes_7d", "configuratiewijzigingen"),
            ("skipped_7d", "skips"),
            ("snoozed_7d", "later gezet"),
            ("decision_churn_events_7d", "decision-churn events"),
            ("execution_pressure_events_7d", "execution-pressure events"),
        ]:
            previous_key = f"previous_{key}"
            current = int(metrics.get(key) or 0)
            previous = int(metrics.get(previous_key) or 0)
            delta = current - previous
            comparisons.append({
                "metric": key,
                "label": label,
                "current": current,
                "previous": previous,
                "delta": delta,
                "direction": "up" if delta > 0 else ("down" if delta < 0 else "flat"),
            })
        meaningful = [item for item in comparisons if item["delta"] != 0]
        decision_delta = int(metrics.get("decision_churn_events_7d") or 0) - int(metrics.get("previous_decision_churn_events_7d") or 0)
        pressure_delta = int(metrics.get("execution_pressure_events_7d") or 0) - int(metrics.get("previous_execution_pressure_events_7d") or 0)
        review_brakes_delta = (
            (int(metrics.get("skipped_7d") or 0) + int(metrics.get("snoozed_7d") or 0) + int(metrics.get("monitor_7d") or 0))
            - (int(metrics.get("previous_skipped_7d") or 0) + int(metrics.get("previous_snoozed_7d") or 0) + int(metrics.get("previous_monitor_7d") or 0))
        )
        if not meaningful:
            status = "steady"
            momentum = "flat"
            summary = "Nog geen duidelijke verandering of te weinig vorige-weekdata."
        elif decision_delta > 0 or pressure_delta > 0:
            status = "heating_up"
            momentum = "rising_pressure"
            summary = "Je gedragsdruk loopt op vergeleken met vorige week: meer churn of execution-frictie vraagt om extra rem."
        elif review_brakes_delta > 0 and decision_delta <= 0 and pressure_delta <= 0:
            status = "stabilising"
            momentum = "cooling"
            summary = "Je gebruikt meer review-frictie dan vorige week. Dat oogt als stabieler of bewuster gedrag."
        else:
            status = "mixed"
            momentum = "mixed"
            lead = max(meaningful, key=lambda item: abs(item["delta"]))
            direction = "meer" if lead["delta"] > 0 else "minder"
            summary = f"{abs(lead['delta'])} {lead['label']} {direction} dan vorige week."
        return {
            "period": "last_7_days_vs_previous_7_days",
            "status": status,
            "momentum": momentum,
            "summary": summary,
            "comparisons": comparisons,
        }

    def _weekly_reflection_message(self, reflection: Dict[str, Any]) -> str:
        metrics = reflection.get("metrics") or {}
        lines = [
            "Weekreflectie op basis van je echte Finn-activiteit van de laatste 7 dagen.",
            reflection.get("headline") or "Ik heb nog geen harde weekconclusie.",
            (
                f"Discipline-score: {reflection.get('discipline_score')}/100."
                if reflection.get("discipline_score") is not None else
                "Discipline-score: nog niet betrouwbaar genoeg."
            ),
            (
                "Kernmetrics: "
                f"{metrics.get('actions_7d', 0)} acties, "
                f"{metrics.get('bot_decisions_generated_7d', 0)} bot-decisions, "
                f"{metrics.get('configuration_changes_7d', 0)} configuratiewijzigingen, "
                f"{metrics.get('possible_overrides_7d', 0)} mogelijke plan-afwijkingen, "
                f"{metrics.get('decision_churn_events_7d', 0)} decision-churn events."
            ),
            (
                "Configuratie: "
                f"{metrics.get('plan_creates_7d', 0)} nieuwe plannen, "
                f"{metrics.get('strategy_changes_7d', 0)} strategy-wijzigingen, "
                f"{metrics.get('bot_changes_7d', 0)} bot-wijzigingen, "
                f"{metrics.get('indicator_changes_7d', 0)} indicator-wijzigingen."
            ),
        ]
        profile = reflection.get("behavioral_profile") or {}
        if profile:
            lines.append(f"Profiel deze week: {profile.get('label')} - {profile.get('summary')}")
        wow = reflection.get("week_over_week") or {}
        if wow.get("summary"):
            lines.append(f"Vergeleken met vorige week: {wow.get('summary')}")
        risk_flags = reflection.get("risk_flags") or []
        if risk_flags:
            lines.append("Waar Finn nu extra op moet letten:")
            for flag in risk_flags[:3]:
                lines.append(f"- {flag.get('label')}: {flag.get('summary')}")
        habit_cards = reflection.get("habit_cards") or []
        if habit_cards:
            lines.append("Werkstijl die Finn nu ziet:")
            for card in habit_cards[:3]:
                lines.append(f"- {card.get('label')}: {card.get('summary')}")
        agent_rhythm = reflection.get("agent_rhythm") or {}
        if agent_rhythm.get("summary"):
            lines.append(f"Agent-ritme: {agent_rhythm.get('summary')}")
            followed = agent_rhythm.get("followed_patterns") or []
            friction = agent_rhythm.get("friction_patterns") or []
            if followed:
                lines.extend([f"- {item}" for item in followed[:2]])
            if friction:
                lines.extend([f"- Let op: {item}" for item in friction[:2]])
        operating_rules = reflection.get("operating_rules") or {}
        rules = operating_rules.get("rules") or []
        if rules:
            lines.append("Personal operating rules:")
            for rule in rules[:3]:
                lines.append(f"- {rule.get('title')}: {rule.get('rule')}")
        strengths = reflection.get("strengths") or []
        if strengths:
            lines.append("Sterk deze week:")
            lines.extend([f"- {item}" for item in strengths[:3]])
        watchouts = reflection.get("watchouts") or []
        if watchouts:
            lines.append("Let volgende week op:")
            lines.extend([f"- {item}" for item in watchouts[:3]])
        lines.append(f"Veilige volgende stap: {reflection.get('safe_next_step')}")
        return "\n".join([line for line in lines if line])

    def _build_behavioral_insight_from_activity(
        self,
        activity_feed: List[Dict[str, Any]],
        day_log: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        activity_feed = activity_feed or []
        day_log = day_log or self._mission_day_log(activity_feed)
        executed = [item for item in activity_feed if item.get("status") == "executed"]
        pending = [item for item in activity_feed if item.get("status") == "pending"]
        today = _utc_now().date()

        today_items = []
        seven_day_items = []
        previous_seven_day_items = []
        now = _utc_now()
        for item in activity_feed:
            created_at = self._parse_mission_timestamp(item.get("created_at"))
            if created_at and created_at.date() == today:
                today_items.append(item)
            if created_at and created_at >= now - timedelta(days=7):
                seven_day_items.append(item)
            elif created_at and created_at >= now - timedelta(days=14):
                previous_seven_day_items.append(item)

        def count_type(items: List[Dict[str, Any]], action_type: str) -> int:
            return len([item for item in items if item.get("type") == action_type])

        def count_resolution(items: List[Dict[str, Any]], resolution: str) -> int:
            return len([item for item in items if item.get("resolve_state") == resolution])

        plan_creates_7d = count_type(seven_day_items, "create_plan")
        strategy_changes_7d = count_type(seven_day_items, "create_strategy")
        bot_changes_7d = count_type(seven_day_items, "create_bot") + count_type(seven_day_items, "bot_config_update")
        indicator_changes_7d = count_type(seven_day_items, "configure_indicator")
        previous_configuration_changes_7d = (
            count_type(previous_seven_day_items, "create_plan")
            + count_type(previous_seven_day_items, "create_strategy")
            + count_type(previous_seven_day_items, "create_bot")
            + count_type(previous_seven_day_items, "configure_indicator")
        )

        behavioral_events = [
            item.get("behavioral_event") for item in seven_day_items
            if isinstance(item.get("behavioral_event"), dict)
        ]
        previous_behavioral_events = [
            item.get("behavioral_event") for item in previous_seven_day_items
            if isinstance(item.get("behavioral_event"), dict)
        ]
        possible_overrides = [
            event for event in behavioral_events
            if event.get("type") in {"plan_deviation_attempt", "execution_pressure", "strategy_change_pressure"}
        ]
        plan_deviation_events = [
            event for event in behavioral_events
            if event.get("type") in {"plan_deviation_attempt", "strategy_change_pressure"}
        ]
        decision_churn_events = [
            event for event in behavioral_events
            if event.get("type") == "decision_churn"
        ]
        execution_pressure_events = [
            event for event in behavioral_events
            if event.get("type") == "execution_pressure"
        ]
        previous_decision_churn_events = [
            event for event in previous_behavioral_events
            if event.get("type") == "decision_churn"
        ]
        previous_execution_pressure_events = [
            event for event in previous_behavioral_events
            if event.get("type") == "execution_pressure"
        ]
        previous_plan_deviation_events = [
            event for event in previous_behavioral_events
            if event.get("type") in {"plan_deviation_attempt", "strategy_change_pressure"}
        ]
        blocked_context_events = [
            event for event in possible_overrides
            if (event.get("context") or {}).get("status") in {"blocked", "data_missing"}
        ]

        items_30d = []
        previous_30d = []
        for item in activity_feed:
            created_at = self._parse_mission_timestamp(item.get("created_at"))
            if not created_at:
                continue
            if created_at >= now - timedelta(days=30):
                items_30d.append(item)
            elif created_at >= now - timedelta(days=60):
                previous_30d.append(item)

        metrics = {
            "actions_today": len(today_items),
            "executed_today": len([item for item in today_items if item.get("status") == "executed"]),
            "pending_today": len([item for item in today_items if item.get("status") == "pending"]),
            "resolved_today": day_log.get("resolved_count", 0),
            "skipped_today": day_log.get("skipped_count", 0),
            "snoozed_today": day_log.get("snoozed_count", 0),
            "monitor_today": day_log.get("monitor_count", 0),
            "bot_decisions_generated": count_type(today_items, "generate_bot_decision"),
            "bot_decisions_skipped": count_type(today_items, "skip_bot_decision"),
            "paper_executions": count_type(today_items, "paper_execute_bot_decision"),
            "live_preflights": count_type(today_items, "live_preflight_bot_decision"),
            "plan_creates": count_type(today_items, "create_plan"),
            "strategy_changes": count_type(today_items, "create_strategy"),
            "bot_changes": count_type(today_items, "create_bot"),
            "indicator_changes": count_type(today_items, "configure_indicator"),
            "actions_7d": len(seven_day_items),
            "executed_7d": len([item for item in seven_day_items if item.get("status") == "executed"]),
            "skipped_7d": count_resolution(seven_day_items, "skipped"),
            "snoozed_7d": count_resolution(seven_day_items, "snoozed"),
            "monitor_7d": count_resolution(seven_day_items, "monitor_today"),
            "bot_decisions_generated_7d": count_type(seven_day_items, "generate_bot_decision"),
            "paper_executions_7d": count_type(seven_day_items, "paper_execute_bot_decision"),
            "live_preflights_7d": count_type(seven_day_items, "live_preflight_bot_decision"),
            "plan_creates_7d": plan_creates_7d,
            "strategy_changes_7d": strategy_changes_7d,
            "bot_changes_7d": bot_changes_7d,
            "indicator_changes_7d": indicator_changes_7d,
            "configuration_changes_7d": plan_creates_7d + strategy_changes_7d + bot_changes_7d + indicator_changes_7d,
            "previous_actions_7d": len(previous_seven_day_items),
            "previous_bot_decisions_generated_7d": count_type(previous_seven_day_items, "generate_bot_decision"),
            "previous_configuration_changes_7d": previous_configuration_changes_7d,
            "previous_skipped_7d": count_resolution(previous_seven_day_items, "skipped"),
            "previous_snoozed_7d": count_resolution(previous_seven_day_items, "snoozed"),
            "previous_monitor_7d": count_resolution(previous_seven_day_items, "monitor_today"),
            "behavioral_events_7d": len(behavioral_events),
            "previous_behavioral_events_7d": len(previous_behavioral_events),
            "possible_overrides_7d": len(possible_overrides),
            "plan_deviation_events_7d": len(plan_deviation_events),
            "decision_churn_events_7d": len(decision_churn_events),
            "execution_pressure_events_7d": len(execution_pressure_events),
            "previous_decision_churn_events_7d": len(previous_decision_churn_events),
            "previous_execution_pressure_events_7d": len(previous_execution_pressure_events),
            "previous_plan_deviation_events_7d": len(previous_plan_deviation_events),
            "blocked_context_events_7d": len(blocked_context_events),
            "actions_30d": len(items_30d),
            "previous_actions_30d": len(previous_30d),
            "configuration_changes_30d": (
                count_type(items_30d, "create_plan")
                + count_type(items_30d, "create_strategy")
                + count_type(items_30d, "create_bot")
                + count_type(items_30d, "bot_config_update")
                + count_type(items_30d, "configure_indicator")
            ),
            "plan_deviation_events_30d": len([
                item for item in items_30d
                if isinstance(item.get("behavioral_event"), dict)
                and item.get("behavioral_event", {}).get("type") in {"plan_deviation_attempt", "strategy_change_pressure"}
            ]),
        }

        signals: List[Dict[str, Any]] = []
        if not activity_feed:
            status = "not_enough_data"
            primary = "Ik heb nog te weinig Finn-activiteit om je handelsgedrag betrouwbaar te spiegelen."
            safe_next_step = "Gebruik Mission Control vandaag bewust: review, skip of stel acties uit in plaats van impulsief te handelen."
        else:
            if decision_churn_events or metrics["bot_decisions_generated"] >= 3 or metrics["paper_executions"] >= 2 or metrics["bot_decisions_generated_7d"] >= 5:
                signals.append({
                    "type": "decision_churn",
                    "severity": "medium",
                    "message": (
                        "Je vroeg opnieuw bot-decisions aan terwijl er nog open review stond."
                        if decision_churn_events else
                        "Er is relatief veel decision/execution-activiteit. Dat kan op onrust of overtrading-druk wijzen."
                    ),
                    "evidence": [
                        f"{metrics['bot_decisions_generated']} bot-decisions vandaag",
                        f"{metrics['bot_decisions_generated_7d']} bot-decisions in 7 dagen",
                        f"{metrics['paper_executions_7d']} paper executions in 7 dagen",
                        f"{metrics['decision_churn_events_7d']} explicit decision-churn events",
                    ],
                })
            if metrics["live_preflights"] > 0 or metrics["live_preflights_7d"] >= 2 or possible_overrides:
                evidence = [
                    f"{metrics['live_preflights_7d']} live preflight checks in 7 dagen",
                    f"{metrics['possible_overrides_7d']} mogelijke plan-afwijking events",
                ]
                if blocked_context_events:
                    evidence.append(f"{len(blocked_context_events)} event(s) terwijl setup/data blokkeerde")
                signals.append({
                    "type": "execution_friction",
                    "severity": "medium",
                    "message": "Ik zie execution-druk of guardrail-frictie. Finn moet hier extra remmend blijven.",
                    "evidence": evidence,
                })
            if metrics["skipped_today"] > 0 or metrics["snoozed_today"] > 0 or metrics["monitor_today"] > 0 or metrics["skipped_7d"] + metrics["snoozed_7d"] + metrics["monitor_7d"] >= 2:
                signals.append({
                    "type": "disciplined_waiting",
                    "severity": "low",
                    "message": "Je hebt bewust afgeremd of items afgehandeld. Dat is positief disciplinegedrag.",
                    "evidence": [
                        f"{metrics['skipped_7d']} overgeslagen in 7 dagen",
                        f"{metrics['snoozed_7d']} later gezet in 7 dagen",
                        f"{metrics['monitor_7d']} gemonitord in 7 dagen",
                    ],
                })
            if metrics["plan_creates"] + metrics["strategy_changes"] + metrics["bot_changes"] >= 4 or metrics["configuration_changes_7d"] >= 6:
                signals.append({
                    "type": "configuration_churn",
                    "severity": "medium",
                    "message": "Er zijn relatief veel configuratiewijzigingen. Check of je je plan verbetert of steeds van richting verandert.",
                    "evidence": [
                        f"{metrics['configuration_changes_7d']} configuratiewijzigingen in 7 dagen",
                        f"{metrics['plan_creates_7d']} plannen, {metrics['strategy_changes_7d']} strategies, {metrics['bot_changes_7d']} bots, {metrics['indicator_changes_7d']} indicators",
                    ],
                })
            if metrics["bot_decisions_generated"] >= 3 and (metrics["paper_executions"] > 0 or metrics["live_preflights"] > 0):
                signals.append({
                    "type": "possible_fomo",
                    "severity": "medium",
                    "message": "Mogelijke FOMO-druk: meerdere decisions en execution-intentie op dezelfde dag.",
                    "evidence": [
                        f"{metrics['bot_decisions_generated']} bot-decisions vandaag",
                        f"{metrics['paper_executions']} paper executions vandaag",
                        f"{metrics['live_preflights']} live preflights vandaag",
                    ],
                })
            if pending:
                signals.append({
                    "type": "review_hygiene",
                    "severity": "low",
                    "message": "Er staan nog bevestigbare acties open. Rond die bewust af of annuleer ze, zodat je cockpit schoon blijft.",
                    "evidence": [f"{len(pending)} pending Finn-acties"],
                })

            if not signals:
                signals.append({
                    "type": "discipline_neutral",
                    "severity": "low",
                    "message": "Ik zie geen hard bewijs voor impulsief gedrag in je recente Finn-activiteit.",
                    "evidence": [f"{len(executed)} uitgevoerde Finn-acties in recente historie"],
                })

            status = "attention" if any(signal["severity"] in {"medium", "high"} for signal in signals) else "early_signal"
            primary = signals[0]["message"]
            safe_next_step = (
                "Werk eerst de bovenste Mission Control-actie af en maak pas daarna een nieuwe trade- of botbeslissing."
                if status == "attention"
                else "Blijf deze acties bewust via review, confirm of skip afhandelen."
            )

        do_not_do = "Gebruik dit niet als koop- of verkoopadvies; dit is alleen gedragscoaching op basis van je eigen Finn-activiteit."
        patterns = [signal["type"] for signal in signals]
        behavioral_profile = self._behavioral_profile_from_metrics(metrics, patterns)
        trend = self._behavioral_week_over_week(metrics)
        risk_flags = self._behavioral_risk_flags(metrics, patterns)
        habit_cards = self._behavioral_habit_cards(metrics, patterns)
        return {
                "status": status,
                "period": "today_and_7d",
                "advice_only": True,
                "signals": signals,
                "patterns": patterns,
                "behavioral_events": behavioral_events[:5],
                "metrics": metrics,
                "behavioral_profile": behavioral_profile,
                "trend": trend,
                "risk_flags": risk_flags,
                "habit_cards": habit_cards,
                "coaching": {
                    "primary_reflection": primary,
                    "safe_next_step": safe_next_step,
                    "focus_now": risk_flags[0]["safe_counter_move"] if risk_flags else None,
                    "do_not_do": do_not_do,
                },
            "evidence_source": "ai_pending_actions",
        }

    def _behavioral_intelligence_message(self, insight: Dict[str, Any]) -> str:
        coaching = insight.get("coaching") or {}
        metrics = insight.get("metrics") or {}
        signals = insight.get("signals") or []
        if insight.get("variant") == "plan_adherence_coach":
            lines = [
                "Stop hier even en laat je plan weer leiden.",
                "Je dreigt nu een planregel te breken; check die eerst opnieuw.",
                insight.get("what_i_notice") or "Ik zie dat je buiten je strategie wilt bewegen.",
                f"Waarom dit risicovol is: {insight.get('why_this_is_risky')}",
                f"Wat nu doen: {insight.get('what_to_do_now')}",
                f"Niet doen: {insight.get('what_not_to_do')}",
            ]
            if insight.get("plan_anchor"):
                lines.append(f"Plananker: {insight.get('plan_anchor')}")
            return "\n".join([line for line in lines if line])
        if insight.get("variant") == "direct_coach":
            lines = [
                "Stop even en vertraag direct.",
                "Doe nu niets nieuws tot je plan weer leidend is.",
                insight.get("what_i_notice") or coaching.get("primary_reflection") or "Ik zie emotionele of impulsieve druk.",
                f"Waarom dit risicovol is: {insight.get('why_this_is_risky')}",
                f"Wat nu doen: {insight.get('what_to_do_now')}",
                f"Niet doen: {insight.get('what_not_to_do')}",
            ]
            if insight.get("plan_anchor"):
                lines.append(f"Plananker: {insight.get('plan_anchor')}")
            return "\n".join([line for line in lines if line])
        lines = [
            "Ik kijk hier alleen naar je recente Finn-gedrag, niet naar marktvoorspellingen.",
            coaching.get("primary_reflection") or "Ik heb nog geen harde gedragsconclusie.",
        ]
        profile = insight.get("behavioral_profile") or {}
        if profile.get("label"):
            lines.append(f"Profiel: {profile.get('label')} - {profile.get('summary')}")
        if signals:
            lines.append("Signalen:")
            for signal in signals[:3]:
                lines.append(f"- {signal.get('message')}")
        trend = insight.get("trend") or {}
        if trend.get("summary"):
            lines.append(f"Trend: {trend.get('summary')}")
        risk_flags = insight.get("risk_flags") or []
        if risk_flags:
            lines.append("Gedragsrisico's die Finn nu ziet:")
            for flag in risk_flags[:3]:
                lines.append(f"- {flag.get('label')}: {flag.get('summary')}")
        habit_cards = insight.get("habit_cards") or []
        if habit_cards:
            lines.append("Werkstijl die Finn herkent:")
            for card in habit_cards[:2]:
                lines.append(f"- {card.get('label')}: {card.get('summary')}")
        lines.append(
            "Vandaag: "
            f"{metrics.get('actions_today', 0)} acties, "
            f"{metrics.get('skipped_today', 0)} skips, "
            f"{metrics.get('snoozed_today', 0)} later gezet, "
            f"{metrics.get('bot_decisions_generated', 0)} bot-decisions."
        )
        lines.append(
            "Laatste 7 dagen: "
            f"{metrics.get('actions_7d', 0)} acties, "
            f"{metrics.get('bot_decisions_generated_7d', 0)} bot-decisions, "
            f"{metrics.get('configuration_changes_7d', 0)} configuratiewijzigingen, "
            f"{metrics.get('possible_overrides_7d', 0)} mogelijke override-/druksignalen, "
            f"{metrics.get('plan_deviation_events_7d', 0)} plan-afwijking events, "
            f"{metrics.get('decision_churn_events_7d', 0)} decision-churn events."
        )
        if coaching.get("focus_now"):
            lines.append(f"Focus nu: {coaching.get('focus_now')}")
        lines.append(f"Veilige volgende stap: {coaching.get('safe_next_step')}")
        return "\n".join([line for line in lines if line])

    def _build_mission_control_from_daily_analysis(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        assets = analysis.get("assets") or []
        open_actions: List[Dict[str, Any]] = []
        plan_health: List[Dict[str, Any]] = []
        bot_review_queue: List[Dict[str, Any]] = []
        workqueue: List[Dict[str, Any]] = []

        for item in assets:
            plan = self._mission_plan_health_entry(item)
            asset = plan["asset"]
            setup = plan.get("setup") or {}
            status = plan.get("status")
            data_readiness = plan.get("data_readiness") or {}
            bot_today = item.get("bot_today") or {}
            plan_health.append(plan)

            for action in item.get("follow_up_actions") or []:
                open_actions.append(self._mission_action(action, asset, status, setup))

            for decision in (bot_today.get("decisions") or [])[:3]:
                review_item = self._mission_bot_review_item(decision, item)
                if review_item.get("review_status") == "needs_review":
                    bot_review_queue.append(review_item)
                    workqueue.append(self._mission_workqueue_from_bot_review(review_item))

            plan_item = self._mission_workqueue_from_plan(plan)
            if plan_item:
                workqueue.append(plan_item)

        if len(assets) > 1 or not assets:
            for action in analysis.get("follow_up_actions") or []:
                open_actions.append(self._mission_action(action, action.get("asset"), "portfolio", {}))

        portfolio_risk = analysis.get("portfolio_risk") or {}
        for stack in (portfolio_risk.get("risk_stacks") or [])[:3]:
            workqueue.append(self._mission_workqueue_from_portfolio_risk_stack(stack))
        for hotspot in (portfolio_risk.get("live_bot_hotspots") or [])[:2]:
            workqueue.append(self._mission_workqueue_from_live_bot_hotspot(hotspot))

        open_actions = self._dedupe_mission_actions(open_actions)[:8]
        for action in open_actions:
            workqueue.append(self._mission_workqueue_from_action(action))
        workqueue = self._dedupe_workqueue(workqueue)[:10]
        workqueue_groups = self._mission_workqueue_groups(workqueue)
        workqueue = self._flatten_mission_workqueue_groups(workqueue_groups)
        active_count = len([item for item in plan_health if item["status"] == "active"])
        blocked_count = len([item for item in plan_health if item["status"] == "blocked"])
        data_missing_count = len([item for item in plan_health if item["status"] == "data_missing"])

        return {
            "summary": {
                "asset_count": len(plan_health),
                "active_count": active_count,
                "blocked_count": blocked_count,
                "data_missing_count": data_missing_count,
                "open_action_count": len(open_actions),
                "bot_review_count": len(bot_review_queue),
                "workqueue_count": len(workqueue),
                "portfolio_risk_status": portfolio_risk.get("status"),
                "portfolio_risk_top_asset": portfolio_risk.get("top_asset"),
                "portfolio_ignore_today_count": len(portfolio_risk.get("ignore_today_assets") or []),
                "portfolio_live_hotspot_count": len(portfolio_risk.get("live_bot_hotspots") or []),
                "posture": "action_required" if open_actions or blocked_count or data_missing_count else "stable",
            },
            "workqueue": workqueue,
            "workqueue_groups": workqueue_groups,
            "workqueue_labels": self._mission_workqueue_labels(),
            "open_actions": open_actions,
            "plan_health": plan_health,
            "bot_review_queue": bot_review_queue[:8],
            "portfolio_risk": portfolio_risk,
        }

    def _mission_coaching_lane(self, item: Dict[str, Any]) -> str:
        state = str(item.get("resolve_state") or item.get("status") or "").lower()
        freshness = str((item.get("freshness") or {}).get("status") or "").lower()
        item_type = str(item.get("type") or "").lower()
        if state == "needs_user_confirmation" or freshness == "stale":
            return "act_now"
        if item_type in {"bot_decision", "data_gap", "score_refresh", "indicator_gap"}:
            return "act_now"
        if state in {"waiting_for_data", "monitor_today"}:
            return "review_then_act"
        if item_type in {"blocked_plan", "blocker_explanation", "portfolio_risk_stack", "portfolio_live_hotspot"}:
            return "review_then_act"
        return "monitor_only"

    def _mission_coaching_priority_entry(self, item: Dict[str, Any]) -> Dict[str, Any]:
        lane = self._mission_coaching_lane(item)
        action = item.get("next_best_action") or item.get("resolve_action")
        freshness = item.get("freshness") or {}
        signals = []
        if item.get("asset"):
            signals.append(item.get("asset"))
        if item.get("dominant_agent"):
            signals.append(f"{item.get('dominant_agent')} eerst")
        if freshness.get("label"):
            signals.append(freshness.get("label"))
        elif freshness.get("status"):
            signals.append(freshness.get("status"))
        if item.get("health_grade"):
            signals.append(item.get("health_grade"))
        if item.get("risk_score") is not None:
            signals.append(f"risk {int(self._to_float(item.get('risk_score')) or 0)}")
        why_now = (
            "Nu uitvoeren voorkomt extra drift of gemiste review."
            if lane == "act_now"
            else "Eerst begrijpen of monitoren voordat je iets forceert."
            if lane == "review_then_act"
            else "Niet escaleren; alleen volgen zolang het signaal niet verslechtert."
        )
        return {
            "id": item.get("id"),
            "asset": item.get("asset"),
            "title": item.get("title"),
            "reason": item.get("reason"),
            "priority": item.get("priority"),
            "priority_rank": item.get("priority_rank"),
            "lane": lane,
            "status": item.get("resolve_state") or item.get("status"),
            "why_now": why_now,
            "supporting_signals": signals[:4],
            "action": action if isinstance(action, dict) else None,
        }

    def _mission_coaching_suppressions(
        self,
        mission: Dict[str, Any],
        portfolio_risk: Dict[str, Any],
        behavioral_insight: Dict[str, Any],
        priority_assets: set,
    ) -> List[Dict[str, Any]]:
        suppressed: List[Dict[str, Any]] = []
        for item in (portfolio_risk.get("ignore_today_assets") or [])[:3]:
            asset = item.get("asset")
            prompt_asset = asset or "deze asset"
            suppressed.append({
                "id": f"ignore_today:{asset or len(suppressed)}",
                "asset": asset,
                "title": f"{prompt_asset} vandaag laten liggen",
                "reason": item.get("reason") or "Vandaag niet forceren zolang dit signaal actief is.",
                "why_not_now": item.get("unblock_condition") or "Pas opnieuw oppakken zodra het blokkerende signaal weg is.",
                "source": "portfolio_risk",
                "action": {
                    "type": "chat_prompt",
                    "label": f"{prompt_asset} ignore-uitleg",
                    "prompt": f"Welke assets moet ik vandaag negeren?",
                    "handoff": "daily_coach",
                    "requires_confirmation": False,
                },
            })

        for plan in mission.get("plan_health") or []:
            asset = plan.get("asset")
            if (
                plan.get("status") == "active"
                and asset
                and asset not in priority_assets
                and len(suppressed) < 5
            ):
                suppressed.append({
                    "id": f"steady_plan:{asset}",
                    "asset": asset,
                    "title": f"{asset} niet extra forceren",
                    "reason": plan.get("reason") or "Plan staat stabiel genoeg om niet extra aan te zitten.",
                    "why_not_now": "Geen extra actie nodig zolang je plan actief en gezond blijft.",
                    "source": "plan_health",
                    "action": None,
                })

        coaching = behavioral_insight.get("coaching") or {}
        if coaching.get("do_not_do"):
            suppressed.append({
                "id": "behavioral_do_not_do",
                "asset": None,
                "title": "Geen extra impuls of override-jacht",
                "reason": coaching.get("do_not_do"),
                "why_not_now": coaching.get("safe_next_step") or "Hou je aandacht bij de prioriteiten hierboven.",
                "source": "behavioral",
                "action": None,
            })
        return suppressed[:5]

    def _mission_coaching_handoffs(
        self,
        priorities: List[Dict[str, Any]],
        controller: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        actions = []
        controller_action = controller.get("primary_action") if isinstance(controller, dict) else None
        if isinstance(controller_action, dict) and controller_action.get("prompt"):
            actions.append({
                "label": controller_action.get("label") or controller_action.get("prompt"),
                "prompt": controller_action.get("prompt"),
                "handoff": controller_action.get("handoff") or "chat",
                "asset": controller_action.get("asset"),
                "requires_confirmation": bool(controller_action.get("requires_confirmation")),
            })
        for item in priorities:
            action = item.get("action") or {}
            if action.get("prompt"):
                actions.append({
                    "label": action.get("label") or action.get("prompt"),
                    "prompt": action.get("prompt"),
                    "handoff": action.get("handoff") or "chat",
                    "asset": item.get("asset") or action.get("asset"),
                    "requires_confirmation": bool(action.get("requires_confirmation")),
                })
        return self._dedupe_mission_actions(actions)[:4]

    def _build_mission_coaching_loop(
        self,
        mission: Dict[str, Any],
        analysis: Dict[str, Any],
        behavioral_insight: Dict[str, Any],
    ) -> Dict[str, Any]:
        workqueue = mission.get("workqueue") or []
        priorities = [self._mission_coaching_priority_entry(item) for item in workqueue[:6]]
        act_now = [item for item in priorities if item.get("lane") == "act_now"][:3]
        review_then_act = [item for item in priorities if item.get("lane") == "review_then_act"][:3]
        monitor_only = [item for item in priorities if item.get("lane") == "monitor_only"][:3]
        priority_stack = (act_now + review_then_act + monitor_only)[:3]
        priority_assets = {item.get("asset") for item in priority_stack if item.get("asset")}
        portfolio_risk = mission.get("portfolio_risk") or analysis.get("portfolio_risk") or {}
        controller = mission.get("agent_controller") or {}
        suppressions = self._mission_coaching_suppressions(
            mission,
            portfolio_risk,
            behavioral_insight,
            priority_assets,
        )
        handoffs = self._mission_coaching_handoffs(priority_stack, controller)
        focus_now = ((behavioral_insight.get("coaching") or {}).get("focus_now")
                     or (priority_stack[0].get("why_now") if priority_stack else None))
        headline = (
            f"Pak eerst {priority_stack[0].get('title')} op."
            if priority_stack
            else "Vandaag geen harde interventie nodig; blijf alleen monitoren."
        )
        status = (
            "action_required"
            if act_now
            else "watchful"
            if review_then_act
            else "stable"
        )
        return {
            "status": status,
            "headline": headline,
            "today_focus": focus_now,
            "do_not_do": (behavioral_insight.get("coaching") or {}).get("do_not_do"),
            "daily_priority_stack": priority_stack,
            "act_now": act_now,
            "review_then_act": review_then_act,
            "monitor_only": monitor_only,
            "suppressed_items": suppressions,
            "operator_handoffs": handoffs,
        }

    def _mission_workqueue_from_portfolio_risk_stack(self, stack: Dict[str, Any]) -> Dict[str, Any]:
        asset = stack.get("asset") or "portfolio"
        item_id = f"portfolio_risk_stack:{asset}"
        priority = "high" if stack.get("severity") == "high" else "medium"
        priority_rank = 7 if priority == "high" else 18
        next_action = {
            "type": "chat_prompt",
            "label": f"{asset} risk stack uitleg",
            "prompt": f"Welke bots en plannen stapelen risico voor {asset}?",
            "handoff": "daily_coach",
            "requires_confirmation": False,
        }
        freshness = self._mission_freshness(None, fallback_status="unknown")
        return {
            "id": item_id,
            "type": "portfolio_risk_stack",
            "priority": priority,
            "priority_rank": priority_rank,
            "sort_rank": priority_rank,
            "status": "stacked_risk",
            "resolve_state": self._mission_resolve_state("portfolio_risk_stack", "stacked_risk", next_action, freshness=freshness),
            "asset": asset,
            "title": f"{asset} risico stapelt",
            "reason": stack.get("reason"),
            "next_best_action": next_action,
            "resolve_action": self._mission_resolve_action(
                item_id,
                "monitor_today",
                asset=asset,
                label="Vandaag monitoren",
                reason=stack.get("reason"),
                source_ids={"asset": asset},
            ),
            "resolve_actions": self._mission_resolve_actions(
                item_id,
                asset=asset,
                reason=stack.get("reason"),
                source_ids={"asset": asset},
            ),
            "freshness": freshness,
            "source_ids": {"asset": asset},
            "risk_score": stack.get("risk_score"),
            "risk_factors": stack.get("factors") or [],
        }

    def _mission_workqueue_from_live_bot_hotspot(self, hotspot: Dict[str, Any]) -> Dict[str, Any]:
        asset = hotspot.get("asset") or "portfolio"
        item_id = f"portfolio_live_hotspot:{asset}"
        risk_score = self._to_float(hotspot.get("risk_score")) or 0.0
        priority = "high" if risk_score >= 75 else "medium"
        priority_rank = 6 if priority == "high" else 16
        next_action = {
            "type": "chat_prompt",
            "label": f"{asset} live bots review",
            "prompt": f"Welke live bots vragen vandaag review voor {asset}?",
            "handoff": "daily_coach",
            "requires_confirmation": False,
        }
        freshness = self._mission_freshness(None, fallback_status="unknown")
        return {
            "id": item_id,
            "type": "portfolio_live_hotspot",
            "priority": priority,
            "priority_rank": priority_rank,
            "sort_rank": priority_rank,
            "status": "live_hotspot",
            "resolve_state": self._mission_resolve_state("portfolio_live_hotspot", "live_hotspot", next_action, freshness=freshness),
            "asset": asset,
            "title": f"{asset} live bots vragen review",
            "reason": hotspot.get("summary") or hotspot.get("reason"),
            "next_best_action": next_action,
            "resolve_action": self._mission_resolve_action(
                item_id,
                "monitor_today",
                asset=asset,
                label="Vandaag monitoren",
                reason=hotspot.get("summary") or hotspot.get("reason"),
                source_ids={"asset": asset},
            ),
            "resolve_actions": self._mission_resolve_actions(
                item_id,
                asset=asset,
                reason=hotspot.get("summary") or hotspot.get("reason"),
                source_ids={"asset": asset},
            ),
            "freshness": freshness,
            "source_ids": {"asset": asset},
            "risk_score": hotspot.get("risk_score"),
            "live_bot_count": hotspot.get("live_bot_count"),
        }

    def _mission_workqueue_labels(self) -> Dict[str, str]:
        return {
            "first": "Eerst dit",
            "review": "Daarna reviewen",
            "later": "Kan wachten",
        }

    def _mission_workqueue_group_key(self, item: Dict[str, Any]) -> str:
        state = item.get("resolve_state") or item.get("status")
        if item.get("controller_rank_boost"):
            return "first"
        if state in {"needs_user_confirmation", "waiting_for_data"} or (item.get("freshness") or {}).get("status") == "stale":
            return "first"
        if state == "monitor_today" or item.get("type") in {"blocked_plan", "blocker_explanation", "portfolio_risk_stack", "portfolio_live_hotspot"}:
            return "review"
        return "later"

    def _mission_workqueue_groups(self, workqueue: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        labels = self._mission_workqueue_labels()
        groups = {
            "first": [],
            "review": [],
            "later": [],
        }
        for item in workqueue:
            groups[self._mission_workqueue_group_key(item)].append(item)

        return [
            {
                "key": key,
                "label": labels[key],
                "count": len(items),
                "items": items,
            }
            for key, items in groups.items()
            if items
        ]

    def _flatten_mission_workqueue_groups(self, groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            item
            for group in groups
            for item in (group.get("items") or [])
        ]

    def _filter_resolved_mission_items(self, mission: Dict[str, Any], resolved_item_ids: set) -> Dict[str, Any]:
        workqueue = [
            item for item in mission.get("workqueue", [])
            if item.get("id") not in resolved_item_ids
        ]
        workqueue_groups = self._mission_workqueue_groups(workqueue)
        mission = {**mission, "workqueue": self._flatten_mission_workqueue_groups(workqueue_groups)}
        mission["workqueue_groups"] = workqueue_groups
        mission["summary"] = {
            **(mission.get("summary") or {}),
            "workqueue_count": len(workqueue),
        }
        return mission

    def _mission_day_log(self, activity_feed: List[Dict[str, Any]]) -> Dict[str, Any]:
        handled = [
            item for item in activity_feed
            if item.get("resolve_state") in {"resolved", "skipped", "monitor_today", "waiting_for_data", "snoozed"}
        ]
        return {
            "date": _utc_now().date().isoformat(),
            "handled_count": len(handled),
            "resolved_count": len([item for item in handled if item.get("resolve_state") == "resolved"]),
            "skipped_count": len([item for item in handled if item.get("resolve_state") == "skipped"]),
            "monitor_count": len([item for item in handled if item.get("resolve_state") == "monitor_today"]),
            "waiting_for_data_count": len([item for item in handled if item.get("resolve_state") == "waiting_for_data"]),
            "snoozed_count": len([item for item in handled if item.get("resolve_state") == "snoozed"]),
            "items": handled[:6],
        }

    async def _get_today_resolved_mission_item_ids(self, user_id: int) -> set:
        if not self.session:
            return set()
        day_key = _utc_now().date().isoformat()
        rows = await self.session.execute(text("""
            SELECT payload
            FROM ai_pending_actions
            WHERE user_id = :user_id
              AND status = 'executed'
              AND payload->'action'->>'type' IN ('resolve_mission_item', 'snooze_mission_item')
              AND payload->'result'->>'day_key' = :day_key
        """), {"user_id": user_id, "day_key": day_key})
        item_ids = set()
        for row in rows.fetchall():
            payload = row._mapping.get("payload") or {}
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = {}
            result = payload.get("result") if isinstance(payload, dict) else {}
            source_item_id = (result or {}).get("source_item_id")
            if (result or {}).get("resolution") == "snoozed":
                snooze_until = self._parse_mission_timestamp((result or {}).get("snooze_until"))
                if snooze_until and snooze_until <= _utc_now():
                    continue
            if source_item_id:
                item_ids.add(source_item_id)
        return item_ids

    def _mission_bot_review_item(self, decision: Dict[str, Any], item: Dict[str, Any]) -> Dict[str, Any]:
        asset = decision.get("symbol") or item.get("asset") or "BTC"
        setup = item.get("setup") or {}
        decision_id = decision.get("id")
        status = str(decision.get("status") or "planned").lower()
        action = str(decision.get("action") or "hold").lower()
        confidence = self._to_float(decision.get("confidence"))
        amount = self._to_float(decision.get("amount_eur"))
        requested_amount = self._to_float(decision.get("requested_amount_eur"))
        guardrails_result = decision.get("guardrails_result")
        guardrail_reason = decision.get("guardrail_reason")
        reasons = decision.get("reasons") or []
        setup_match = decision.get("setup_match") or {}
        trade_plan = decision.get("trade_plan") or {}

        risk_level = "low"
        if action in {"buy", "sell"}:
            risk_level = "medium"
        if guardrails_result is False or guardrail_reason:
            risk_level = "high"
        if confidence is not None and confidence < 0.55 and action in {"buy", "sell"}:
            risk_level = "high"

        review_status = "handled" if status in {"executed", "skipped", "cancelled", "filled"} else "needs_review"
        amount_label = amount if amount is not None else requested_amount
        summary = f"{asset}: {action}"
        if action == "hold":
            summary += " - geen orderbedrag"
        elif amount_label is not None:
            summary += f" voor EUR {amount_label:g}"
        if guardrail_reason:
            summary += " - guardrail aandacht"

        review_actions = [
            {
                "type": "chat_prompt",
                "label": "Decision uitleg",
                "prompt": f"Leg bot-decision {decision_id} uit",
                "handoff": "bot_decision_review",
                "requires_confirmation": False,
            },
            {
                "type": "chat_prompt",
                "label": "Bot-decision opnieuw maken",
                "prompt": f"Maak bot-decision voor bot #{decision.get('bot_id')}",
                "handoff": "bot_decision",
                "requires_confirmation": True,
            },
        ]
        if review_status == "needs_review" and action in {"buy", "sell"}:
            review_actions.extend([
                {
                    "type": "chat_prompt",
                    "label": "Paper uitvoeren",
                    "prompt": f"Voer bot-decision {decision_id} paper uit",
                    "handoff": "bot_execution_decision",
                    "requires_confirmation": True,
                },
                {
                    "type": "chat_prompt",
                    "label": "Live preflight",
                    "prompt": f"Doe live preflight voor bot-decision {decision_id}",
                    "handoff": "bot_execution_decision",
                    "requires_confirmation": True,
                },
            ])
        if review_status == "needs_review":
            review_actions.append({
                "type": "chat_prompt",
                "label": "Overslaan",
                "prompt": f"Sla bot-decision {decision_id} over",
                "handoff": "bot_execution_decision",
                "requires_confirmation": True,
            })

        return {
            "asset": asset,
            "setup_id": setup.get("id") or decision.get("setup_id"),
            "strategy_id": decision.get("strategy_id"),
            "bot_id": decision.get("bot_id"),
            "bot_name": decision.get("bot_name"),
            "decision_id": decision_id,
            "action": action,
            "status": status,
            "review_status": review_status,
            "risk_level": risk_level,
            "confidence": confidence,
            "amount_eur": amount,
            "requested_amount_eur": requested_amount,
            "summary": summary,
            "guardrails_result": guardrails_result,
            "guardrail_reason": guardrail_reason,
            "setup_match": setup_match,
            "reasons": reasons[:3] if isinstance(reasons, list) else [str(reasons)],
            "trade_plan_present": bool(
                (trade_plan.get("entry_plan") if isinstance(trade_plan, dict) else None)
                or (trade_plan.get("targets") if isinstance(trade_plan, dict) else None)
                or (trade_plan.get("stop_loss") if isinstance(trade_plan, dict) else None)
            ),
            "created_at": decision.get("created_at"),
            "updated_at": decision.get("updated_at"),
            "prompt": f"Leg bot-decision {decision_id} uit",
            "review_actions": review_actions,
        }

    async def _get_recent_finn_activity(self, user_id: int, limit: int = 8) -> List[Dict[str, Any]]:
        if not self.session:
            return []
        rows = await self.session.execute(text("""
            SELECT id, status, payload, trace_id, created_at
            FROM ai_pending_actions
            WHERE user_id = :user_id
              AND (
                id LIKE 'finn%'
                OR payload->'action'->>'type' = 'agent_controller_handoff'
                OR payload->'result'->>'type' = 'agent_controller_handoff'
              )
              AND status IN ('pending', 'executed', 'failed')
            ORDER BY created_at DESC
            LIMIT :limit
        """), {"user_id": user_id, "limit": max(1, min(limit, 200))})
        return [self._mission_activity_item(dict(row._mapping)) for row in rows.fetchall()]

    def _mission_activity_item(self, row: Dict[str, Any]) -> Dict[str, Any]:
        payload = row.get("payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        action = payload.get("action") or {}
        result = payload.get("result") or {}
        action_type = action.get("type") or result.get("type") or "unknown"
        status = row.get("status") or "pending"
        asset = (
            action.get("asset")
            or (action.get("payload") or {}).get("asset")
            or (action.get("payload") or {}).get("symbol")
            or result.get("asset")
            or result.get("symbol")
            or ((result.get("execution_audit") or {}).get("asset") if isinstance(result.get("execution_audit"), dict) else None)
        )
        assets = (action.get("payload") or {}).get("assets") or result.get("assets")
        if not asset and isinstance(assets, list) and assets:
            asset = assets[0]
        result_status = result.get("status")
        verified = result.get("verified") if isinstance(result.get("verified"), dict) else {}
        resolve_state = self._mission_activity_resolve_state(status, result_status, action_type)

        title_by_type = {
            "create_plan": "Setup-flow uitgevoerd",
            "create_strategy": "Strategie opgeslagen",
            "create_bot": "Bot opgeslagen",
            "configure_indicator": "Indicator-config opgeslagen",
            "refresh_daily_scores": "Daily scores ververst",
            "generate_bot_decision": "Bot-decision gemaakt",
            "skip_bot_decision": "Bot-decision overgeslagen",
            "paper_execute_bot_decision": "Paper execution verwerkt",
            "live_preflight_bot_decision": "Live preflight gecontroleerd",
            "bot_config_update": "Bot risk-wijziging bevestigd",
            "manual_order": "Manual order bevestigd",
            "live_manual_order_preflight": "Live order preflight gecontroleerd",
            "live_manual_order_blocked": "Live order geblokkeerd",
            "live_setup_block_acknowledged": "Geblokkeerde setup bewust bevestigd",
            "live_manual_order_confirmed": "Live manual order geplaatst",
            "agent_controller_handoff": "Agent-handoff gevolgd",
            "resolve_mission_item": "Mission Control item bijgewerkt",
            "snooze_mission_item": "Mission Control item uitgesteld",
        }
        label = action.get("label") or title_by_type.get(action_type) or action_type.replace("_", " ")
        outcome = result.get("message") or result.get("response")
        if not outcome:
            if status == "pending":
                outcome = "Wacht nog op bevestiging of uitvoering."
            elif status == "failed":
                outcome = "Actie is niet afgerond."
            elif result_status:
                outcome = f"Status: {result_status}."
            else:
                outcome = "Actie afgerond en vastgelegd."

        created_at = row.get("created_at")
        if hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()

        return {
            "id": row.get("id"),
            "type": action_type,
            "label": label,
            "status": status,
            "resolve_state": resolve_state,
            "asset": asset,
            "created_at": created_at,
            "updated_at": payload.get("updated_at"),
            "trace_id": row.get("trace_id") or payload.get("trace_id") or result.get("trace_id"),
            "result_status": result_status,
            "outcome": outcome,
            "verified": verified,
            "behavioral_event": result.get("behavioral_event") if isinstance(result.get("behavioral_event"), dict) else None,
            "agent_accountability": result.get("agent_accountability") if isinstance(result.get("agent_accountability"), dict) else None,
            "entity_ids": {
                "setup_id": result.get("setup_id") or (action.get("payload") or {}).get("setup_id"),
                "strategy_id": result.get("strategy_id") or (action.get("payload") or {}).get("strategy_id"),
                "bot_id": result.get("bot_id") or (action.get("payload") or {}).get("bot_id"),
                "decision_id": result.get("decision_id") or (action.get("payload") or {}).get("decision_id"),
            },
            "requires_confirmation": bool(action.get("requires_confirmation")),
            "risk_level": action.get("risk_level"),
        }

    def _mission_activity_resolve_state(self, status: Any, result_status: Any, action_type: str) -> str:
        normalized_status = str(status or "").lower()
        normalized_result = str(result_status or "").lower()
        if action_type == "snooze_mission_item":
            return "snoozed"
        if action_type == "resolve_mission_item":
            if normalized_result in {"skipped", "monitor_today", "waiting_for_data"}:
                return normalized_result
            return "resolved"
        if normalized_result in {"skipped", "cancelled"} or action_type == "skip_bot_decision":
            return "skipped"
        if normalized_status == "pending":
            return "needs_user_confirmation"
        if normalized_status == "failed":
            return "needs_user_confirmation"
        if normalized_status == "executed":
            return "resolved"
        return "monitor_today"

    def _mission_plan_health_entry(self, item: Dict[str, Any]) -> Dict[str, Any]:
        asset = item.get("asset") or "BTC"
        setup = item.get("setup") or {}
        stance = item.get("stance")
        blockers = item.get("blockers") or []
        data_readiness = item.get("data_readiness") or {}
        bot_today = item.get("bot_today") or {}
        warnings = ((item.get("indicator_summary") or {}).get("warnings") or [])[:2]

        if stance == "plan_is_active":
            status = "active"
            label = "nu doen"
            reason = "Plan actief volgens je setup-ranges."
        elif stance == "wait_for_scores":
            status = "data_missing"
            label = "eerst data"
            reason = data_readiness.get("message") or "Daily scores ontbreken."
        else:
            status = "blocked"
            label = "niet forceren"
            first_blocker = blockers[0] if blockers else {}
            reason = (
                f"{first_blocker.get('category')} score {first_blocker.get('score')} buiten {first_blocker.get('range')}."
                if first_blocker else "Setup is nog niet actief volgens je planregels."
            )

        category_checks = self._mission_category_checks(item)
        health_score = self._mission_health_score(
            status=status,
            match_percentage=item.get("setup_match_percentage"),
            warnings=warnings,
            data_readiness=data_readiness,
        )

        return {
            "asset": asset,
            "status": status,
            "priority": label,
            "reason": reason,
            "setup": setup,
            "match_percentage": item.get("setup_match_percentage"),
            "health_score": health_score,
            "health_grade": self._mission_health_grade(status, health_score),
            "category_checks": category_checks,
            "lifecycle": self._mission_lifecycle(item),
            "next_best_action": self._mission_next_best_action(item, status),
            "blockers": blockers[:3],
            "warnings": warnings,
            "data_readiness": data_readiness,
            "bot_decision_count": bot_today.get("decision_count", 0),
        }

    def _mission_category_checks(self, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        by_category: Dict[str, Dict[str, Any]] = {}
        for status, source in [
            ("blocked", item.get("blockers") or []),
            ("passed", item.get("passed_checks") or []),
            ("missing", item.get("missing_checks") or []),
        ]:
            for check in source:
                category = check.get("category")
                if not category:
                    continue
                by_category[category] = {
                    "category": category,
                    "status": status,
                    "score": check.get("score"),
                    "range": check.get("range"),
                    "reason": check.get("blocker_reason") or check.get("interpretation"),
                }

        checks = []
        for category in ["macro", "technical", "market"]:
            checks.append(by_category.get(category) or {
                "category": category,
                "status": "unknown",
                "score": None,
                "range": None,
                "reason": "Geen betrouwbare check beschikbaar.",
            })
        return checks

    def _mission_health_score(
        self,
        *,
        status: str,
        match_percentage: Any,
        warnings: List[str],
        data_readiness: Dict[str, Any],
    ) -> int:
        match = self._to_float(match_percentage)
        if match is None:
            match = 25.0 if status == "data_missing" else 50.0
        if status == "active":
            score = max(match, 80.0)
        elif status == "data_missing":
            score = min(match, 35.0)
        else:
            score = match

        score -= min(len(warnings), 3) * 5
        score -= min(len(data_readiness.get("config_gaps") or []), 3) * 5
        return int(max(0, min(100, round(score))))

    def _mission_health_grade(self, status: str, health_score: int) -> str:
        if status == "data_missing":
            return "incomplete"
        if status == "blocked":
            return "blocked"
        if health_score >= 80:
            return "healthy"
        if health_score >= 55:
            return "watch"
        return "weak"

    def _mission_lifecycle(self, item: Dict[str, Any]) -> Dict[str, Any]:
        setup = item.get("setup") or {}
        active_strategy = item.get("active_strategy") or {}
        strategy = active_strategy.get("strategy") or {}
        bot_today = item.get("bot_today") or {}
        data_readiness = item.get("data_readiness") or {}
        decision_count = int(bot_today.get("decision_count") or 0)
        strategy_status = (
            "active_today"
            if active_strategy.get("active")
            else "configured_not_active_today"
            if strategy or active_strategy.get("strategy_exists")
            else "missing"
        )

        return {
            "setup": {
                "status": "configured" if setup else "missing",
                "id": setup.get("id"),
                "name": setup.get("name"),
                "type": setup.get("type"),
                "timeframe": setup.get("timeframe"),
            },
            "strategy": {
                "status": strategy_status,
                "id": strategy.get("id"),
                "name": strategy.get("name"),
            },
            "bot": {
                "status": "review_ready" if decision_count else "needs_decision",
                "decision_count": decision_count,
                "error": bot_today.get("error"),
            },
            "data": {
                "status": data_readiness.get("status") or ("ready" if item.get("has_scores") else "missing"),
                "has_scores": bool(item.get("has_scores")),
                "config_gaps": data_readiness.get("config_gaps") or [],
            },
        }

    def _mission_next_best_action(self, item: Dict[str, Any], status: str) -> Optional[Dict[str, Any]]:
        actions = item.get("follow_up_actions") or []
        preferred_handoffs = {
            "data_missing": ["daily_score_refresh", "indicator_config", "indicator_insight", "bot_decision"],
            "blocked": ["indicator_insight", "indicator_config", "daily_score_refresh", "bot_decision"],
            "active": ["bot_decision", "indicator_insight", "daily_score_refresh", "indicator_config"],
        }.get(status, ["indicator_insight", "daily_score_refresh", "indicator_config", "bot_decision"])

        for handoff in preferred_handoffs:
            action = next((candidate for candidate in actions if candidate.get("handoff") == handoff), None)
            if action:
                return self._mission_action(action, item.get("asset"), status, item.get("setup") or {})
        if actions:
            return self._mission_action(actions[0], item.get("asset"), status, item.get("setup") or {})
        return None

    def _mission_action(
        self,
        action: Dict[str, Any],
        asset: Optional[str],
        plan_status: str,
        setup: Dict[str, Any],
    ) -> Dict[str, Any]:
        handoff = action.get("handoff") or "chat"
        priority_rank = {
            "daily_score_refresh": 10,
            "indicator_config": 20,
            "indicator_insight": 30,
            "bot_decision": 40,
        }.get(handoff, 50)
        return {
            "label": action.get("label") or action.get("prompt") or "Finn actie",
            "prompt": action.get("prompt") or action.get("label") or "",
            "handoff": handoff,
            "requires_confirmation": bool(action.get("requires_confirmation")),
            "asset": asset,
            "setup_id": setup.get("id") if isinstance(setup, dict) else None,
            "plan_status": plan_status,
            "priority_rank": priority_rank,
        }

    def _dedupe_mission_actions(self, actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        unique = []
        for action in sorted(actions, key=lambda item: (item.get("priority_rank", 99), str(item.get("asset") or ""), str(item.get("prompt") or ""))):
            key = (action.get("prompt"), action.get("handoff"), action.get("asset"))
            if not action.get("prompt") or key in seen:
                continue
            seen.add(key)
            unique.append(action)
        return unique

    def _mission_workqueue_from_bot_review(self, item: Dict[str, Any]) -> Dict[str, Any]:
        next_action = next(
            (action for action in item.get("review_actions") or [] if action.get("handoff") == "bot_decision_review"),
            (item.get("review_actions") or [None])[0],
        )
        priority = "high"
        freshness = self._mission_freshness(
            item.get("updated_at") or item.get("created_at"),
            stale_after_minutes=360,
            aging_after_minutes=120,
        )
        priority_rank = 5 if freshness.get("status") == "stale" else 8
        resolve_state = self._mission_resolve_state(
            "bot_decision",
            "stale" if freshness.get("status") == "stale" else "review_ready",
            next_action,
            freshness=freshness,
        )
        return {
            "id": f"bot_decision:{item.get('decision_id')}",
            "type": "bot_decision",
            "priority": priority,
            "priority_rank": priority_rank,
            "sort_rank": priority_rank,
            "status": "stale" if freshness.get("status") == "stale" else "review_ready",
            "resolve_state": resolve_state,
            "asset": item.get("asset"),
            "title": f"Review bot-decision #{item.get('decision_id')}",
            "reason": item.get("summary") or "Bot-decision vraagt review.",
            "next_best_action": next_action,
            "resolve_action": None,
            "freshness": freshness,
            "source_ids": {
                "setup_id": item.get("setup_id"),
                "strategy_id": item.get("strategy_id"),
                "bot_id": item.get("bot_id"),
                "decision_id": item.get("decision_id"),
            },
        }

    def _mission_workqueue_from_plan(self, plan: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        status = plan.get("status")
        if status == "active":
            return None
        item_type = "data_gap" if status == "data_missing" else "blocked_plan"
        priority = "high" if status == "blocked" else "medium"
        freshness = self._mission_freshness(None, fallback_status="stale" if status == "data_missing" else "unknown")
        priority_rank = 9 if priority == "high" else 25
        item_status = "blocked" if status == "blocked" else "blocked_by_data"
        return {
            "id": f"{item_type}:{plan.get('asset')}:{(plan.get('setup') or {}).get('id') or 'none'}",
            "type": item_type,
            "priority": priority,
            "priority_rank": priority_rank,
            "sort_rank": priority_rank,
            "status": item_status,
            "resolve_state": self._mission_resolve_state(item_type, item_status, plan.get("next_best_action"), freshness=freshness),
            "asset": plan.get("asset"),
            "title": f"{plan.get('asset')} plan aandacht",
            "reason": plan.get("reason"),
            "next_best_action": plan.get("next_best_action"),
            "resolve_action": self._mission_resolve_action(
                f"{item_type}:{plan.get('asset')}:{(plan.get('setup') or {}).get('id') or 'none'}",
                "monitor_today" if item_status == "blocked" else "waiting_for_data",
                asset=plan.get("asset"),
                label="Vandaag monitoren" if item_status == "blocked" else "Wachten op data",
                reason=plan.get("reason"),
                source_ids={
                    "setup_id": (plan.get("setup") or {}).get("id"),
                    "strategy_id": ((plan.get("lifecycle") or {}).get("strategy") or {}).get("id"),
                },
            ),
            "resolve_actions": self._mission_resolve_actions(
                f"{item_type}:{plan.get('asset')}:{(plan.get('setup') or {}).get('id') or 'none'}",
                asset=plan.get("asset"),
                reason=plan.get("reason"),
                source_ids={
                    "setup_id": (plan.get("setup") or {}).get("id"),
                    "strategy_id": ((plan.get("lifecycle") or {}).get("strategy") or {}).get("id"),
                },
                include_waiting_for_data=item_status != "blocked",
            ),
            "freshness": freshness,
            "source_ids": {
                "setup_id": (plan.get("setup") or {}).get("id"),
                "strategy_id": ((plan.get("lifecycle") or {}).get("strategy") or {}).get("id"),
            },
            "health_score": plan.get("health_score"),
            "health_grade": plan.get("health_grade"),
        }

    def _mission_workqueue_from_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        item_type = self._mission_workqueue_action_type(action)
        priority = "medium" if action.get("requires_confirmation") else "low"
        freshness = self._mission_freshness(None, fallback_status="unknown")
        priority_rank = action.get("priority_rank", 60) + (0 if priority == "medium" else 10)
        item_status = "needs_user_confirmation" if action.get("requires_confirmation") else "new"
        return {
            "id": f"{item_type}:{action.get('handoff')}:{action.get('asset') or 'portfolio'}:{hashlib.sha1(str(action.get('prompt') or '').encode('utf-8')).hexdigest()[:10]}",
            "type": item_type,
            "priority": priority,
            "priority_rank": priority_rank,
            "sort_rank": priority_rank,
            "status": item_status,
            "resolve_state": self._mission_resolve_state(item_type, item_status, action, freshness=freshness),
            "asset": action.get("asset"),
            "title": action.get("label") or "Finn actie",
            "reason": "Aanbevolen volgende stap vanuit Mission Control.",
            "next_best_action": action,
            "resolve_action": None,
            "freshness": freshness,
            "source_ids": {
                "setup_id": action.get("setup_id"),
            },
        }

    def _mission_workqueue_action_type(self, action: Dict[str, Any]) -> str:
        handoff = action.get("handoff")
        label = str(action.get("label") or action.get("prompt") or "").lower()
        if handoff == "daily_score_refresh":
            return "score_refresh"
        if handoff == "indicator_config":
            return "indicator_gap"
        if handoff == "indicator_insight":
            return "blocker_explanation"
        if handoff == "bot_decision":
            return "bot_decision_request"
        if "data" in label:
            return "data_gap"
        return "open_action"

    def _mission_resolve_action(
        self,
        item_id: str,
        resolution: str,
        *,
        asset: Optional[str] = None,
        label: str = "Markeer afgehandeld",
        reason: Optional[str] = None,
        source_ids: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        resolution_meta = {
            "resolved": {
                "lane": "done",
                "summary": "Haal dit punt uit je dagflow; het is bewust afgehandeld.",
                "what_next": "Ga door naar het volgende item met echte operatorwaarde.",
            },
            "skipped": {
                "lane": "skip",
                "summary": "Leg vast dat je dit bewust niet doorzet.",
                "what_next": "Pak alleen opnieuw op als de context echt veranderd is.",
            },
            "monitor_today": {
                "lane": "monitor",
                "summary": "Houd dit vandaag in beeld zonder nu te forceren.",
                "what_next": "Check later opnieuw als scores, prijsactie of context verschuiven.",
            },
            "waiting_for_data": {
                "lane": "data",
                "summary": "Parkeer dit tot de benodigde data of refresh binnen is.",
                "what_next": "Ververs scores of wacht op nieuwe indicator-data voordat je verdergaat.",
            },
        }.get(resolution, {
            "lane": "done",
            "summary": "Dit item is bijgewerkt.",
            "what_next": "Ga verder met de volgende prioriteit.",
        })
        return {
            "id": self._maintenance_action_id("resolve_mission_item", [item_id, resolution, _utc_now().date().isoformat()]),
            "type": "resolve_mission_item",
            "label": label,
            "resolution": resolution,
            "lane": resolution_meta["lane"],
            "summary": resolution_meta["summary"],
            "what_next": resolution_meta["what_next"],
            "payload": {
                "source_item_id": item_id,
                "resolution": resolution,
                "asset": asset,
                "reason": reason,
                "source_ids": source_ids or {},
                "day_key": _utc_now().date().isoformat(),
            },
            "risk_level": "low",
            "requires_confirmation": False,
            "autonomy_level": "user_initiated",
            "guardrails": {
                "requires_confirmation": False,
                "can_execute_without_user": False,
                "writes_trading_config": False,
                "executes_order": False,
            },
        }

    def _mission_resolve_actions(
        self,
        item_id: str,
        *,
        asset: Optional[str] = None,
        reason: Optional[str] = None,
        source_ids: Optional[Dict[str, Any]] = None,
        include_waiting_for_data: bool = False,
    ) -> List[Dict[str, Any]]:
        actions = [
            self._mission_resolve_action(
                item_id,
                "resolved",
                asset=asset,
                label="Markeer klaar",
                reason=reason,
                source_ids=source_ids,
            ),
            self._mission_resolve_action(
                item_id,
                "monitor_today",
                asset=asset,
                label="Vandaag monitoren",
                reason=reason,
                source_ids=source_ids,
            ),
            self._mission_snooze_action(
                item_id,
                asset=asset,
                label="Later opnieuw bekijken",
                reason=reason,
                source_ids=source_ids,
            ),
        ]
        if include_waiting_for_data:
            actions.insert(0, self._mission_resolve_action(
                item_id,
                "waiting_for_data",
                asset=asset,
                label="Wachten op data",
                reason=reason,
                source_ids=source_ids,
            ))
        return actions

    def _mission_snooze_action(
        self,
        item_id: str,
        *,
        asset: Optional[str] = None,
        label: str = "Later opnieuw bekijken",
        reason: Optional[str] = None,
        source_ids: Optional[Dict[str, Any]] = None,
        minutes: int = 240,
    ) -> Dict[str, Any]:
        snooze_until = _utc_now() + timedelta(minutes=minutes)
        return {
            "id": self._maintenance_action_id("snooze_mission_item", [item_id, str(minutes), _utc_now().date().isoformat()]),
            "type": "snooze_mission_item",
            "label": label,
            "resolution": "snoozed",
            "lane": "later",
            "summary": "Haal dit tijdelijk uit je actieve aandacht, zonder het te vergeten.",
            "what_next": "Pak dit later opnieuw op wanneer de timing beter is.",
            "payload": {
                "source_item_id": item_id,
                "resolution": "snoozed",
                "asset": asset,
                "reason": reason,
                "source_ids": source_ids or {},
                "day_key": _utc_now().date().isoformat(),
                "snooze_until": snooze_until.isoformat(),
                "snooze_minutes": minutes,
            },
            "risk_level": "low",
            "requires_confirmation": False,
            "autonomy_level": "user_initiated",
            "guardrails": {
                "requires_confirmation": False,
                "can_execute_without_user": False,
                "writes_trading_config": False,
                "executes_order": False,
            },
        }

    def _mission_resolve_state(
        self,
        item_type: str,
        status: Optional[str],
        action: Optional[Dict[str, Any]] = None,
        *,
        freshness: Optional[Dict[str, Any]] = None,
    ) -> str:
        normalized_status = str(status or "").lower()
        if normalized_status in {"skipped", "cancelled"}:
            return "skipped"
        if normalized_status in {"executed", "filled", "resolved", "handled"}:
            return "resolved"
        if normalized_status in {"blocked_by_data", "data_missing"} or item_type == "data_gap":
            return "waiting_for_data"
        if bool((action or {}).get("requires_confirmation")):
            return "needs_user_confirmation"
        if item_type in {"bot_decision", "score_refresh", "indicator_gap", "bot_decision_request"}:
            return "needs_user_confirmation"
        if item_type in {"blocked_plan", "blocker_explanation", "portfolio_risk_stack"}:
            return "monitor_today"
        if (freshness or {}).get("status") == "stale":
            return "needs_user_confirmation"
        return "monitor_today"

    def _mission_freshness(
        self,
        timestamp: Any,
        *,
        stale_after_minutes: int = 360,
        aging_after_minutes: int = 120,
        fallback_status: str = "unknown",
    ) -> Dict[str, Any]:
        moment = self._parse_mission_timestamp(timestamp)
        if not moment:
            labels = {
                "fresh": "actueel",
                "aging": "wordt ouder",
                "stale": "verouderd",
                "unknown": "onbekend",
            }
            return {
                "status": fallback_status,
                "age_minutes": None,
                "label": labels.get(fallback_status, fallback_status),
                "source_timestamp": None,
            }
        now = _utc_now()
        age_minutes = max(0, int((now - moment).total_seconds() // 60))
        if age_minutes >= stale_after_minutes:
            status = "stale"
            label = f"{age_minutes} min oud"
        elif age_minutes >= aging_after_minutes:
            status = "aging"
            label = f"{age_minutes} min oud"
        else:
            status = "fresh"
            label = f"{age_minutes} min oud"
        return {
            "status": status,
            "age_minutes": age_minutes,
            "label": label,
            "source_timestamp": moment.isoformat(),
        }

    def _parse_mission_timestamp(self, value: Any) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                return None
        return None

    def _dedupe_workqueue(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        unique = []
        for item in sorted(items, key=lambda entry: (entry.get("priority_rank", 99), str(entry.get("asset") or ""), str(entry.get("id") or ""))):
            key = item.get("id")
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

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

        verdicts = analysis.get("agent_verdicts") or []
        if verdicts:
            lines.append("Agent-verdicts:")
            for verdict in verdicts[:5]:
                lines.append(f"- {verdict.get('label')}: {verdict.get('status')} - {verdict.get('reason')}")
        controller = analysis.get("agent_controller") or {}
        if controller.get("dominant_label"):
            lines.append(
                f"Finn Controller: eerst {controller.get('dominant_label')} volgen - {controller.get('reason')}"
            )

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

        readiness = analysis.get("data_readiness") or {}
        if readiness.get("status") and readiness.get("status") != "ready":
            lines.append("Datakwaliteit:")
            lines.append(f"- {readiness.get('message')}")
            for item in (readiness.get("assets") or [])[:3]:
                if item.get("status") and item.get("status") != "ready":
                    lines.append(f"- {item.get('asset')}: {item.get('message')}")

        portfolio_risk = analysis.get("portfolio_risk") or {}
        if portfolio_risk.get("status") and portfolio_risk.get("status") != "balanced":
            lines.append("Portfolio-risico:")
            exposure_note = self._portfolio_exposure_note(portfolio_risk, analysis.get("question_focus"))
            if exposure_note:
                lines.append(f"- {exposure_note}")
            lines.append(f"- {portfolio_risk.get('message')}")
            ignore_today_assets = portfolio_risk.get("ignore_today_assets") or []
            if ignore_today_assets:
                lines.append("Vandaag liever negeren:")
                for item in ignore_today_assets[:3]:
                    lines.append(f"- {item.get('asset')}: {item.get('reason')}.")
                    if analysis.get("question_focus") == "ignore_today" and item.get("unblock_condition"):
                        lines.append(f"  - Opnieuw oppakken als: {item.get('unblock_condition')}")
            live_bot_hotspots = portfolio_risk.get("live_bot_hotspots") or []
            if live_bot_hotspots:
                lines.append("Live bot-hotspots:")
                for item in live_bot_hotspots[:2]:
                    lines.append(
                        f"- {item.get('asset')}: {item.get('live_bot_count')} live bot(s), {item.get('summary')}."
                    )
            for item in (portfolio_risk.get("asset_risk") or [])[:3]:
                flags = item.get("risk_flags") or []
                flag_text = f" ({', '.join(flags[:3])})" if flags else ""
                lines.append(
                    f"- {item.get('asset')}: {item.get('risk_level')} risk, score {item.get('risk_score')}{flag_text}."
                )
            for stack in (portfolio_risk.get("risk_stacks") or [])[:2]:
                lines.append(f"- Risk stack: {stack.get('reason')}")
            for conflict in (portfolio_risk.get("ranked_conflicts") or portfolio_risk.get("conflicts") or [])[:2]:
                lines.append(f"- Conflict: {conflict.get('reason')}")

        verdicts = analysis.get("agent_verdicts") or []
        if verdicts:
            lines.append("Agent-verdicts:")
            for verdict in verdicts[:5]:
                lines.append(f"- {verdict.get('label')}: {verdict.get('status')} - {verdict.get('reason')}")
        controller = analysis.get("agent_controller") or {}
        if controller.get("dominant_label"):
            lines.append(
                f"Finn Controller: eerst {controller.get('dominant_label')} volgen - {controller.get('reason')}"
            )

        actions = analysis.get("suggested_actions") or []
        if actions:
            lines.append("Veilige volgende stappen:")
            for action in actions[:4]:
                lines.append(f"- {action}")

        lines.append("Ik voer niets automatisch uit vanuit deze portfolio-briefing; dit is advies-only.")
        return "\n".join(lines)

    def _portfolio_exposure_note(self, portfolio_risk: Dict[str, Any], focus: Optional[str]) -> Optional[str]:
        if focus != "exposure":
            return None
        total_equity = self._to_float(portfolio_risk.get("total_equity")) or 0.0
        position_value = self._to_float(portfolio_risk.get("current_position_value")) or 0.0
        allocations = portfolio_risk.get("allocations_pct") or {}
        cash_pct = self._to_float(allocations.get("Cash"))
        concentration = portfolio_risk.get("concentration_warnings") or []
        if total_equity <= 0:
            return "Exposure-check: ik zie nog geen portfolio equity om exposure betrouwbaar te wegen."
        if position_value <= 0 or (cash_pct is not None and cash_pct >= 99):
            top_asset = portfolio_risk.get("top_asset")
            top_reason = portfolio_risk.get("top_reason") or "geen exposure-signaal"
            if top_asset:
                return (
                    f"Exposure-check: nee, ik zie nu geen open positie-exposure; je staat praktisch in cash. "
                    f"Het grootste aandachtspunt is {top_asset}: {top_reason}."
                )
            return "Exposure-check: nee, ik zie nu geen open positie-exposure; je staat praktisch in cash."
        if concentration:
            first = concentration[0]
            asset = first.get("asset")
            pct = first.get("allocation_pct") or first.get("position_share_pct")
            if cash_pct is not None and cash_pct < 0:
                return (
                    f"Exposure-check: ja, {asset} staat boven portfolio-equity ({pct}%). "
                    f"De cash-allocatie is negatief ({cash_pct}%), wat wijst op overallocatie, leverage of overlappende botbudgetten. "
                    "Review eerst budgetten en open bot-exposure voordat je nieuwe acties toevoegt."
                )
            if pct is not None and float(pct) > 100:
                return (
                    f"Exposure-check: ja, {asset} staat boven 100% portfolio-equity ({pct}%). "
                    "Dat voelt als overallocatie of budget overlap; review dit eerst voordat je verder opschaalt."
                )
            return f"Exposure-check: ja, {asset} is geconcentreerd rond {pct}% en vraagt eerst review."
        return (
            f"Exposure-check: ik zie {round(position_value, 2)} euro open positie-waarde op {round(total_equity, 2)} euro equity; "
            "geen harde concentratievlag gevonden."
        )

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

    def _execution_review_action(
        self,
        *,
        label: str,
        prompt: str,
        handoff: str,
        asset: Optional[str] = None,
        requires_confirmation: bool = False,
    ) -> Dict[str, Any]:
        return {
            "type": "chat_prompt",
            "label": label,
            "prompt": prompt,
            "handoff": handoff,
            "requires_confirmation": requires_confirmation,
            "asset": asset,
        }

    def _build_plan_status_execution_review(
        self,
        asset: str,
        analysis: Dict[str, Any],
        *,
        source: str,
    ) -> Dict[str, Any]:
        blockers = analysis.get("blockers") or []
        has_scores = bool(analysis.get("has_scores"))
        active = bool(analysis.get("is_active"))
        reasons = self._analysis_reasons(analysis)[:3]
        dominant_blocker = blockers[0] if blockers else None
        setup = analysis.get("setup") or {}

        if not has_scores:
            status = "waiting_for_data"
            summary = f"Ik kan {asset} nog niet betrouwbaar vrijgeven, omdat de scorelaag vandaag nog niet compleet is."
            why_now = "Zonder verse macro-, technical- en market-scores is een plancheck te dun om op te handelen."
            what_next = [
                "Ververs eerst de daily scores.",
                "Controleer daarna opnieuw of je setup actief is.",
            ]
            actions = [
                self._execution_review_action(
                    label="Daily scores verversen",
                    prompt=f"Ververs daily scores voor {asset}",
                    handoff="daily_score_refresh",
                    asset=asset,
                    requires_confirmation=True,
                ),
            ]
            do_not_do = "Forceer geen entry of override zolang de scorelaag van vandaag ontbreekt."
        elif blockers:
            status = "blocked"
            blocker_category = dominant_blocker.get("category") if dominant_blocker else "score"
            summary = f"Je {asset} setup wordt nu geblokkeerd door je eigen planranges."
            why_now = (
                f"De grootste blokkade zit nu in {blocker_category}: score {dominant_blocker.get('score')} valt buiten {dominant_blocker.get('range')}."
                if dominant_blocker else
                "Een of meer scorelagen vallen buiten je ingestelde ranges."
            )
            what_next = [
                "Los eerst de blocker of datagat op.",
                "Gebruik daarna pas een bot-decision of handmatige entry als tweede stap.",
            ]
            categories = [item.get("category") for item in blockers if item.get("category")]
            actions = [
                self._execution_review_action(
                    label=f"Waarom blokkeert {category}?",
                    prompt=f"Waarom blokkeert {category} mijn {asset} setup?",
                    handoff="indicator_insight",
                    asset=asset,
                )
                for category in categories[:2]
            ]
            actions.append(
                self._execution_review_action(
                    label="Live bots op dit asset reviewen",
                    prompt=f"Welke live bots vragen vandaag review voor {asset}?",
                    handoff="daily_coach",
                    asset=asset,
                )
            )
            do_not_do = "Gebruik een blokkade niet als excuus om je entry handmatig te forceren."
        else:
            status = "clear"
            summary = f"Je {asset} setup ligt nu binnen je ranges; deze check geeft geen scoreblokkade."
            why_now = "Deze explain-check bevestigt dat de scorelaag niet het probleem is, zodat je de volgende stap bewust kunt kiezen."
            what_next = [
                "Gebruik dit als plancheck, niet als automatisch koopsein.",
                "Bekijk een bot-decision of dagelijkse prioriteiten als je nog richting zoekt.",
            ]
            actions = [
                self._execution_review_action(
                    label="Maak bot-decision",
                    prompt=f"Maak bot-decision voor {asset}",
                    handoff="bot_decision",
                    asset=asset,
                    requires_confirmation=True,
                ),
                self._execution_review_action(
                    label="Daily coach",
                    prompt=f"Wat moet ik vandaag doen met mijn {asset} setup?",
                    handoff="daily_coach",
                    asset=asset,
                ),
            ]
            do_not_do = "Verwar 'geen blocker' niet met 'nu meteen uitvoeren'."

        evidence = [
            {"label": "Asset", "value": asset},
            {"label": "Bron", "value": "conceptplan" if source == "draft" else "opgeslagen setup"},
            {"label": "Status", "value": status},
        ]
        if setup.get("id"):
            evidence.append({"label": "Setup", "value": f"#{setup.get('id')}"})
        if analysis.get("match_percentage") is not None:
            evidence.append({"label": "Match", "value": f"{analysis.get('match_percentage')}%"})

        return {
            "type": "execution_review",
            "topic": "plan_status",
            "title": f"Waarom deze planstatus voor {asset}?",
            "status": status,
            "summary": summary,
            "why_this": reasons,
            "why_now": why_now,
            "what_next": what_next,
            "do_not_do": do_not_do,
            "evidence": evidence,
            "actions": actions,
        }

    def _build_indicator_execution_review(self, asset: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        reasons = self._indicator_insight_reasons(analysis)[:3]
        warnings = analysis.get("warnings") or []
        suggestions = analysis.get("suggestions") or []
        categories = analysis.get("categories") or {}
        has_scores = bool(analysis.get("has_daily_scores"))

        status = "explain"
        if warnings:
            status = "attention"
        if not has_scores:
            status = "partial_data"

        what_next = suggestions[:2] or ["Gebruik deze uitleg om je zwakste scorelaag gericht te reviewen."]
        actions = [
            self._execution_review_action(
                label="Planstatus bekijken",
                prompt=f"Waarom is mijn {asset} setup inactief?",
                handoff="plan_status",
                asset=asset,
            ),
        ]
        if categories.get("technical"):
            actions.append(
                self._execution_review_action(
                    label="Technical blockers",
                    prompt=f"Waarom blokkeert technical mijn {asset} setup?",
                    handoff="indicator_insight",
                    asset=asset,
                )
            )

        evidence = [{"label": "Asset", "value": asset}, {"label": "Scorelaag", "value": "indicator explain"}]
        for category, summary in list(categories.items())[:3]:
            score = summary.get("score")
            if score is not None:
                evidence.append({"label": category.capitalize(), "value": str(score)})

        return {
            "type": "execution_review",
            "topic": "indicator_insight",
            "title": f"Waarom bewegen je indicatoren zo voor {asset}?",
            "status": status,
            "summary": (
                f"Finn legt hier uit welke indicatorlagen je {asset} score nu dragen of afremmen."
                if has_scores else
                f"Finn kan {asset} nog maar deels verklaren, omdat de daily score van vandaag ontbreekt."
            ),
            "why_this": reasons,
            "why_now": warnings[:2] or ["Deze laag helpt je onderscheiden of het probleem in data, configuratie of echte marktzwakte zit."],
            "what_next": what_next,
            "do_not_do": "Ga geen indicatorconfig aanpassen alleen omdat één losse explain-check onrust geeft.",
            "evidence": evidence,
            "actions": actions,
        }

    def _build_bot_decision_execution_review(self, review: Dict[str, Any]) -> Dict[str, Any]:
        confidence = review.get("confidence")
        confidence_value = (
            f"{round(confidence * 100)}%"
            if isinstance(confidence, (int, float))
            else "onbekend"
        )
        reasons = [reason for reason in (review.get("reasons") or [])[:3] if reason]
        if not reasons:
            reasons = ["Deze bot-decision is een voorstel, geen uitgevoerde order."]

        status = review.get("review_status") or "review_ready"
        if review.get("risk_level") == "high":
            status = "needs_review"

        what_next = []
        if review.get("review_status") == "needs_review":
            what_next.append("Review eerst guardrails, setup-match en bedrag voordat je iets uitvoert.")
        if review.get("action") == "hold":
            what_next.append("Gebruik hold als monitor-signaal, niet als verborgen execute-trigger.")
        else:
            what_next.append("Kies daarna bewust tussen paper, live preflight of overslaan.")

        evidence = [
            {"label": "Decision", "value": f"#{review.get('decision_id')}"},
            {"label": "Asset", "value": review.get("asset")},
            {"label": "Risico", "value": review.get("risk_level")},
            {"label": "Confidence", "value": confidence_value},
        ]
        if review.get("amount_eur") is not None:
            evidence.append({"label": "Bedrag", "value": f"EUR {review.get('amount_eur'):g}"})

        why_now = (
            f"Deze decision wacht nog op operator-review en raakt {review.get('asset')} direct."
            if review.get("review_status") == "needs_review" else
            "Deze decision is al afgehandeld; de waarde hier zit in begrijpen waarom hij zo stond."
        )
        if review.get("guardrail_reason"):
            why_now = f"Guardrail aandacht: {review.get('guardrail_reason')}."

        return {
            "type": "execution_review",
            "topic": "bot_decision_review",
            "title": f"Waarom dit bot-voorstel voor {review.get('asset')}?",
            "status": status,
            "summary": review.get("summary") or f"{review.get('asset')}: {review.get('action')}",
            "why_this": reasons,
            "why_now": why_now,
            "what_next": what_next,
            "do_not_do": "Voer niets direct uit vanuit deze explain-flow; gebruik eerst paper, preflight of skip als bewuste vervolgstap.",
            "evidence": evidence,
            "actions": (review.get("review_actions") or [])[:4],
        }

    def _build_plan_status_agent_verdicts(
        self,
        asset: str,
        analysis: Dict[str, Any],
        *,
        source: str,
    ) -> List[Dict[str, Any]]:
        blockers = analysis.get("blockers") or []
        checks = analysis.get("checks") or {}
        has_scores = bool(analysis.get("has_scores"))

        def blocker_for(category: str) -> Optional[Dict[str, Any]]:
            return next((item for item in blockers if item.get("category") == category), None)

        def score_verdict(category: str, label: str) -> Dict[str, Any]:
            blocker = blocker_for(category)
            check = checks.get(category) if isinstance(checks, dict) else None
            if blocker:
                status = "blocks_plan"
                priority = "high"
                reason = f"{label} blokkeert: score {blocker.get('score')} buiten range {blocker.get('range')}."
                next_action = f"Vraag waarom {category} mijn {asset} setup blokkeert."
            elif not has_scores or not check:
                status = "missing_data"
                priority = "medium"
                reason = f"{label} heeft onvoldoende scoredata voor deze status-check."
                next_action = "Ververs daily scores."
            else:
                status = "clear"
                priority = "low"
                reason = f"{label} valt binnen je planrange."
                next_action = "Geen actie nodig."
            return {
                "agent": f"{category}_agent",
                "label": f"{label} Agent",
                "status": status,
                "priority": priority,
                "reason": reason,
                "evidence": {
                    "asset": asset,
                    "source": source,
                    "check": check,
                    "blocker": blocker,
                },
                "next_action": next_action,
            }

        risk_status = "blocked" if blockers else ("clear" if analysis.get("is_active") else "unknown")
        return [
            score_verdict("macro", "Macro"),
            score_verdict("technical", "Technical"),
            score_verdict("market", "Market"),
            {
                "agent": "risk_agent",
                "label": "Risk Agent",
                "status": risk_status,
                "priority": "high" if blockers else "low",
                "reason": "Je setup is niet actief volgens je eigen ranges." if blockers else "Geen score-blocker gevonden." if analysis.get("is_active") else analysis.get("reason") or "Status nog onzeker.",
                "evidence": {
                    "asset": asset,
                    "source": source,
                    "match_percentage": analysis.get("match_percentage"),
                    "blocker_count": len(blockers),
                },
                "next_action": "Niet forceren; los eerst de blocker of data-gap op." if blockers else "Gebruik dit als plan-check, niet als emotionele trigger.",
            },
        ]

    def _status_message(self, asset: str, analysis: Dict[str, Any], source: str) -> str:
        if not analysis.get("has_scores"):
            lines = [
                f"Ik kan nog niet betrouwbaar zeggen of {asset} actief is, omdat ik geen scores van vandaag vind. "
                "Zodra macro, technical en market scores beschikbaar zijn kan ik dit onderbouwen."
            ]
            verdicts = analysis.get("agent_verdicts") or []
            if verdicts:
                lines.append("Agent-verdicts:")
                lines.extend([f"- {item.get('label')}: {item.get('status')} - {item.get('reason')}" for item in verdicts[:4]])
            controller = analysis.get("agent_controller") or {}
            if controller.get("dominant_label"):
                lines.append(f"Finn Controller: eerst {controller.get('dominant_label')} volgen - {controller.get('reason')}")
            return "\n".join(lines)

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
            verdicts = analysis.get("agent_verdicts") or []
            if verdicts:
                lines.append("Agent-verdicts:")
                lines.extend([f"- {item.get('label')}: {item.get('status')} - {item.get('reason')}" for item in verdicts[:4]])
            controller = analysis.get("agent_controller") or {}
            if controller.get("dominant_label"):
                lines.append(f"Finn Controller: eerst {controller.get('dominant_label')} volgen - {controller.get('reason')}")
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
        verdicts = analysis.get("agent_verdicts") or []
        if verdicts:
            lines.append("Agent-verdicts:")
            lines.extend([f"- {item.get('label')}: {item.get('status')} - {item.get('reason')}" for item in verdicts[:4]])
        controller = analysis.get("agent_controller") or {}
        if controller.get("dominant_label"):
            lines.append(f"Finn Controller: eerst {controller.get('dominant_label')} volgen - {controller.get('reason')}")
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
        if action and action.get("type") == "refresh_daily_scores":
            return await self._execute_refresh_daily_scores_action(user_id, action)
        if action and action.get("type") == "generate_bot_decision":
            return await self._execute_generate_bot_decision_action(user_id, action)
        if action and action.get("type") == "skip_bot_decision":
            return await self._execute_skip_bot_decision_action(user_id, action)
        if action and action.get("type") == "paper_execute_bot_decision":
            return await self._execute_paper_bot_decision_action(user_id, action)
        if action and action.get("type") == "live_preflight_bot_decision":
            return await self._execute_live_preflight_bot_decision_action(user_id, action)
        if action and action.get("type") == "resolve_mission_item":
            return await self._execute_resolve_mission_item_action(user_id, action)
        if action and action.get("type") == "snooze_mission_item":
            return await self._execute_resolve_mission_item_action(user_id, action)
        if action and action.get("type") == "agent_controller_handoff":
            return await self._execute_agent_controller_handoff_action(user_id, action)
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
        pressure_context = await self._plan_deviation_context_for_draft(user_id, draft)
        behavioral_event = self._behavioral_event_from_bot_draft(draft, pressure_context)
        if behavioral_event:
            result["behavioral_event"] = behavioral_event
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
        behavioral_event = self._behavioral_event_from_strategy_draft(draft)
        if behavioral_event:
            result["behavioral_event"] = behavioral_event
        await self._upsert_action_audit(user_id, action_id, action, status="executed", result=result)
        await self.clear_state(user_id)
        return result

    async def _execute_refresh_daily_scores_action(self, user_id: int, action: Dict[str, Any]) -> Dict[str, Any]:
        payload = action.get("payload") or {}
        assets = [
            str(asset).upper()
            for asset in (payload.get("assets") or [])
            if str(asset).upper() in SUPPORTED_ASSETS
        ] or ["BTC"]
        action_id = f"{action.get('id') or self._maintenance_action_id('refresh_daily_scores', assets)}-u{user_id}"
        acquired = await self._try_create_pending_action(user_id, action_id, action)
        if not acquired:
            existing_result = await self._wait_for_action_result(user_id, action_id)
            if existing_result:
                return existing_result
            raise HTTPException(409, "Deze Finn actie wordt al verwerkt. Probeer zo opnieuw.")

        refreshed = {}
        score_service = ScoreService(ScoreRepository(self.session))
        try:
            for asset in assets:
                await score_service.get_daily_scores(user_id, asset)
                row = await ScoreRepository(self.session).fetch_daily_scores(user_id, asset)
                refreshed[asset] = bool(row)
        except Exception:
            await self.session.rollback()
            await self._upsert_action_audit(user_id, action_id, action, status="failed", result={"ok": False, "assets": assets})
            raise

        result = {
            "ok": all(refreshed.values()),
            "message": f"Daily scores ververst voor: {', '.join(assets)}.",
            "action_id": action_id,
            "assets": assets,
            "verified": {"daily_scores": refreshed},
        }
        await self._upsert_action_audit(user_id, action_id, action, status="executed", result=result)
        return result

    async def execute_issued_action(
        self,
        user_id: int,
        action_id: str,
        fallback_action: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self.session:
            raise HTTPException(503, "Finn action store is niet beschikbaar.")
        existing = await self._get_pending_action_row(user_id, action_id)
        if not existing and str(action_id).startswith("finn-") and not str(action_id).endswith(f"-u{user_id}"):
            existing = await self._get_pending_action_row(user_id, f"{action_id}-u{user_id}")
        if not existing and self._can_execute_fallback_action_from_request(user_id, action_id, fallback_action):
            return await self.execute_action(user_id, dict(fallback_action))
        if not existing:
            raise HTTPException(404, "Finn action token niet gevonden of niet geautoriseerd.")
        payload = existing["payload"] or {}
        if isinstance(payload, str):
            payload = json.loads(payload)
        if existing["status"] == "executed":
            result = payload.get("result")
            if isinstance(result, dict):
                action = payload.get("action") if isinstance(payload.get("action"), dict) else {}
                result = self._hydrate_legacy_follow_through_result(action, result)
                return {**result, "replayed": True}
        if existing["status"] not in {"pending", "executing"}:
            raise HTTPException(409, f"Finn action token is niet uitvoerbaar (status: {existing['status']}).")
        action = payload.get("action")
        if not isinstance(action, dict):
            raise HTTPException(409, "Finn action token mist server-side action payload.")
        return await self.execute_action(user_id, action)

    def _can_execute_fallback_action_from_request(
        self,
        user_id: int,
        action_id: str,
        action: Optional[Dict[str, Any]],
    ) -> bool:
        if not isinstance(action, dict):
            return False
        action_type = str(action.get("type") or "")
        if action_type != "refresh_daily_scores":
            return False
        payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
        assets = payload.get("assets") if isinstance(payload.get("assets"), list) else []
        assets = sorted({str(asset).upper() for asset in assets if str(asset).upper() in SUPPORTED_ASSETS})
        if not assets:
            return False
        expected_base_id = str(action.get("id") or self._maintenance_action_id("refresh_daily_scores", assets))
        expected_action_id = f"{expected_base_id}-u{user_id}"
        return str(action_id) in {expected_base_id, expected_action_id}

    async def _get_pending_action_row(self, user_id: int, action_id: str):
        row = await self.session.execute(text("""
            SELECT payload, status
            FROM ai_pending_actions
            WHERE id = :id AND user_id = :user_id
            LIMIT 1
        """), {"id": action_id, "user_id": user_id})
        return row.mappings().first()

    async def _execute_generate_bot_decision_action(self, user_id: int, action: Dict[str, Any]) -> Dict[str, Any]:
        payload = action.get("payload") or {}
        bot_id = int(payload.get("bot_id") or 0)
        if bot_id <= 0:
            raise HTTPException(422, "bot_id is verplicht voor een bot-decision.")
        action_id = f"{action.get('id') or self._maintenance_action_id('generate_bot_decision', [str(bot_id)])}-u{user_id}"
        acquired = await self._try_create_pending_action(user_id, action_id, action)
        if not acquired:
            existing_result = await self._wait_for_action_result(user_id, action_id)
            if existing_result:
                return existing_result
            raise HTTPException(409, "Deze Finn actie wordt al verwerkt. Probeer zo opnieuw.")

        try:
            generated = await BotService(self.session).run_bot_agent_generate(bot_id, None, user_id)
        except Exception:
            await self.session.rollback()
            await self._upsert_action_audit(user_id, action_id, action, status="failed", result={"ok": False, "bot_id": bot_id})
            raise
        result = {
            "ok": bool(generated.get("ok")),
            "message": "Bot-decision gegenereerd. Review het voorstel voordat je iets uitvoert.",
            "action_id": action_id,
            "bot_id": bot_id,
            "result": generated,
            "verified": {"bot_decision": bool(generated.get("ok"))},
        }
        behavioral_event = self._behavioral_event_from_generate_bot_decision_action(action)
        if behavioral_event:
            result["behavioral_event"] = behavioral_event
        await self._upsert_action_audit(user_id, action_id, action, status="executed", result=result)
        return result

    async def _execute_skip_bot_decision_action(self, user_id: int, action: Dict[str, Any]) -> Dict[str, Any]:
        payload = action.get("payload") or {}
        bot_id = int(payload.get("bot_id") or 0)
        decision_id = int(payload.get("decision_id") or 0)
        if bot_id <= 0 or decision_id <= 0:
            raise HTTPException(422, "bot_id en decision_id zijn verplicht.")
        action_id = f"{action.get('id') or self._maintenance_action_id('skip_bot_decision', [str(bot_id), str(decision_id)])}-u{user_id}"
        acquired = await self._try_create_pending_action(user_id, action_id, action)
        if not acquired:
            existing_result = await self._wait_for_action_result(user_id, action_id)
            if existing_result:
                return existing_result
            raise HTTPException(409, "Deze Finn actie wordt al verwerkt. Probeer zo opnieuw.")

        try:
            skipped = await BotService(self.session).skip_bot_today(bot_id, None, user_id)
            status = await self._read_bot_decision_status(user_id, decision_id)
        except Exception:
            await self.session.rollback()
            await self._upsert_action_audit(user_id, action_id, action, status="failed", result={"ok": False, "bot_id": bot_id, "decision_id": decision_id})
            raise

        operator_resolution = {
            "type": "operator_resolution",
            "title": f"Bot-decision #{decision_id} bewust overgeslagen",
            "status": "skipped",
            "summary": "Je hebt deze decision niet doorgedrukt; Finn legt dat vast als bewuste frictie.",
            "what_changed": [
                f"Decision #{decision_id} staat nu op skipped.",
                "Deze review telt niet meer als open actie voor vandaag.",
            ],
            "what_next": [
                "Ga alleen opnieuw naar een decision als de context echt veranderd is.",
                "Pak liever de volgende open review of prioriteit op.",
            ],
        }
        result = {
            "ok": bool(skipped.get("ok")),
            "message": f"Bot-decision #{decision_id} is overgeslagen.",
            "action_id": action_id,
            "bot_id": bot_id,
            "decision_id": decision_id,
            "status": status,
            "verified": {"bot_decision_skipped": status == "skipped"},
            "operator_resolution": operator_resolution,
            "action_follow_through": operator_resolution,
            "state": {
                "analysis": {
                    "operator_resolution": operator_resolution,
                    "action_follow_through": operator_resolution,
                }
            },
        }
        await self._upsert_action_audit(user_id, action_id, action, status="executed", result=result)
        return result

    async def _execute_resolve_mission_item_action(self, user_id: int, action: Dict[str, Any]) -> Dict[str, Any]:
        payload = action.get("payload") or {}
        source_item_id = str(payload.get("source_item_id") or "").strip()
        resolution = str(payload.get("resolution") or "resolved").strip()
        day_key = str(payload.get("day_key") or _utc_now().date().isoformat())
        if not source_item_id:
            raise HTTPException(422, "source_item_id is verplicht.")
        allowed = {"resolved", "skipped", "monitor_today", "waiting_for_data", "snoozed"}
        if resolution not in allowed:
            raise HTTPException(422, "Ongeldige resolve status.")
        action_type = action.get("type") or "resolve_mission_item"
        action_id = f"{action.get('id') or self._maintenance_action_id(action_type, [source_item_id, resolution, day_key])}-u{user_id}"
        acquired = await self._try_create_pending_action(user_id, action_id, action)
        if not acquired:
            existing_result = await self._wait_for_action_result(user_id, action_id)
            if existing_result:
                return existing_result
            raise HTTPException(409, "Deze Mission Control actie wordt al verwerkt. Probeer zo opnieuw.")

        operator_resolution = {
            "type": "operator_resolution",
            "title": f"Mission Control: {resolution.replace('_', ' ')}",
            "status": resolution,
            "summary": self._mission_resolve_message(resolution),
            "what_changed": [
                f"Item {source_item_id} is vastgelegd als {resolution}.",
                "Je werkqueue en daglog kunnen nu zonder dit item verder.",
            ],
            "what_next": [
                {
                    "resolved": "Ga door naar de volgende prioriteit met de meeste operatorwaarde.",
                    "skipped": "Pak dit alleen opnieuw op als je context of overtuiging verandert.",
                    "monitor_today": "Laat dit vandaag meelopen zonder nu te forceren.",
                    "waiting_for_data": "Ververs of wacht op data voordat je dit opnieuw beoordeelt.",
                    "snoozed": "Kom hier later bewust op terug in plaats van het half open te laten hangen.",
                }.get(resolution, "Ga verder met de volgende stap in Mission Control.")
            ],
        }
        result = {
            "ok": True,
            "message": self._mission_resolve_message(resolution),
            "action_id": action_id,
            "source_item_id": source_item_id,
            "resolution": resolution,
            "status": resolution,
            "asset": payload.get("asset"),
            "day_key": day_key,
            "snooze_until": payload.get("snooze_until"),
            "source_ids": payload.get("source_ids") or {},
            "verified": {"mission_item_resolved": True},
            "operator_resolution": operator_resolution,
            "action_follow_through": operator_resolution,
            "state": {
                "analysis": {
                    "operator_resolution": operator_resolution,
                    "action_follow_through": operator_resolution,
                }
            },
        }
        await self._upsert_action_audit(user_id, action_id, action, status="executed", result=result)
        return result

    async def _execute_agent_controller_handoff_action(self, user_id: int, action: Dict[str, Any]) -> Dict[str, Any]:
        payload = action.get("payload") or {}
        controller = payload.get("agent_controller") if isinstance(payload.get("agent_controller"), dict) else {}
        primary_action = payload.get("primary_action") if isinstance(payload.get("primary_action"), dict) else {}
        dominant_agent = controller.get("dominant_agent") or payload.get("dominant_agent")
        action_id = f"{action.get('id') or self._maintenance_action_id('agent_controller_handoff', [dominant_agent or 'agent', primary_action.get('prompt') or 'handoff'])}-u{user_id}"
        acquired = await self._try_create_pending_action(user_id, action_id, action)
        if not acquired:
            existing_result = await self._wait_for_action_result(user_id, action_id)
            if existing_result:
                return existing_result
            raise HTTPException(409, "Deze agent-handoff wordt al vastgelegd. Probeer zo opnieuw.")

        result = {
            "ok": True,
            "message": "Agent-handoff vastgelegd voor accountability.",
            "action_id": action_id,
            "type": "agent_controller_handoff",
            "dominant_agent": dominant_agent,
            "dominant_label": controller.get("dominant_label"),
            "primary_action": primary_action,
            "asset": primary_action.get("asset") or payload.get("asset"),
            "status": "followed",
            "verified": {"agent_handoff_logged": True},
            "agent_accountability": {
                "dominant_agent": dominant_agent,
                "dominant_label": controller.get("dominant_label"),
                "controller_status": controller.get("status"),
                "controller_score": controller.get("dominant_score"),
                "primary_action_label": primary_action.get("label"),
                "primary_action_handoff": primary_action.get("handoff"),
                "primary_item_id": controller.get("primary_item_id"),
            },
        }
        await self._upsert_action_audit(user_id, action_id, action, status="executed", result=result)
        return result

    def _mission_resolve_message(self, resolution: str) -> str:
        return {
            "resolved": "Mission Control item is afgehandeld voor vandaag.",
            "skipped": "Mission Control item is overgeslagen en vastgelegd.",
            "monitor_today": "Mission Control item staat op monitoren voor vandaag.",
            "waiting_for_data": "Mission Control item wacht op data en is voor nu uit je werkqueue gehaald.",
            "snoozed": "Mission Control item is uitgesteld en voor nu uit je werkqueue gehaald.",
        }.get(resolution, "Mission Control item is bijgewerkt.")

    def _behavioral_event_from_generate_bot_decision_action(self, action: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        payload = action.get("payload") or {}
        context = payload.get("behavioral_context") if isinstance(payload.get("behavioral_context"), dict) else {}
        churn = context.get("decision_churn") if isinstance(context.get("decision_churn"), dict) else {}
        open_ids = churn.get("existing_decision_ids") or []
        if not open_ids:
            return None
        return {
            "type": "decision_churn",
            "severity": "medium",
            "asset": payload.get("asset"),
            "bot_id": payload.get("bot_id"),
            "existing_decision_ids": open_ids,
            "reasons": [
                f"nieuwe bot-decision gevraagd terwijl {len(open_ids)} open review(s) nog niet afgehandeld waren"
            ],
        }

    def _behavioral_event_from_execution_action(self, action: Dict[str, Any], *, result_status: Optional[str] = None) -> Optional[Dict[str, Any]]:
        payload = action.get("payload") or {}
        context = payload.get("behavioral_context") if isinstance(payload.get("behavioral_context"), dict) else {}
        reasons = []
        confidence = self._to_float(context.get("confidence"))
        setup_match_score = self._to_float(context.get("setup_match_score"))
        guardrail_reason = context.get("guardrail_reason")
        if confidence is not None and confidence < 0.55:
            reasons.append(f"confidence {confidence:g} onder 0.55")
        if setup_match_score is not None and setup_match_score < 70:
            reasons.append(f"setup match {setup_match_score:g} onder 70")
        if guardrail_reason:
            reasons.append(f"guardrail: {guardrail_reason}")
        if action.get("type") == "live_preflight_bot_decision":
            reasons.append("live preflight aangevraagd")
        if not reasons:
            return None
        event_type = "execution_pressure" if action.get("type") == "live_preflight_bot_decision" else "plan_deviation_attempt"
        return {
            "type": event_type,
            "severity": "medium",
            "asset": payload.get("asset"),
            "bot_id": payload.get("bot_id"),
            "decision_id": payload.get("decision_id"),
            "decision_action": context.get("decision_action"),
            "result_status": result_status,
            "reasons": reasons,
        }

    def _is_plan_deviation_ack(self, q_lower: str) -> bool:
        return any(phrase in q_lower for phrase in [
            "bewuste override",
            "ik wijk bewust af",
            "override akkoord",
            "override bevestig",
            "bewust afwijken",
            "toch doorgaan",
            "ik bevestig de afwijking",
        ])

    def _draft_requires_plan_deviation_ack(self, draft: Dict[str, Any]) -> bool:
        warning = draft.get("plan_deviation")
        return bool(isinstance(warning, dict) and warning.get("requires_ack") and not warning.get("acknowledged"))

    def _plan_deviation_warning_from_event(self, event: Optional[Dict[str, Any]], *, acknowledged: bool = False) -> Optional[Dict[str, Any]]:
        if not event:
            return None
        context = event.get("context") if isinstance(event.get("context"), dict) else {}
        if context.get("status") not in {"blocked", "data_missing"}:
            return None
        status = context.get("status")
        asset = event.get("asset") or context.get("asset")
        if status == "blocked":
            message = (
                f"Je wijzigt nu {asset or 'dit plan'} terwijl je setup volgens je eigen macro/technical/market ranges blokkeert."
            )
            safe_alternative = "Wacht tot de setup actief is, of markeer dit bewust als override."
        else:
            message = (
                f"Je wijzigt nu {asset or 'dit plan'} terwijl Finn nog geen complete score-/setup-check heeft."
            )
            safe_alternative = "Ververs daily scores of rond data-config af voordat je dit doorzet."
        return {
            "type": event.get("type"),
            "severity": event.get("severity") or ("high" if status == "blocked" else "medium"),
            "status": status,
            "asset": asset,
            "setup_id": context.get("setup_id"),
            "requires_ack": True,
            "acknowledged": acknowledged,
            "message": message,
            "reasons": event.get("reasons") or [],
            "safe_alternative": safe_alternative,
            "ack_phrase": "bewuste override",
        }

    async def _plan_deviation_context_for_draft(self, user_id: int, draft: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.session:
            return None
        asset = str(draft.get("asset") or "").upper()
        setup_id = draft.get("setup_id")
        if not asset and not setup_id:
            return None
        try:
            score_repo = ScoreRepository(self.session)
            active_setups = await score_repo.fetch_active_setups(user_id)
            setup = None
            if setup_id:
                setup = next((item for item in active_setups if int(item.get("id") or 0) == int(setup_id)), None)
            if not setup and asset:
                setup = next((item for item in active_setups if str(item.get("symbol") or "").upper() == asset), None)
            if not setup:
                return None
            asset = str(setup.get("symbol") or asset or "").upper()
            daily_scores = await self._fetch_daily_scores_with_runtime_refresh(user_id, asset)
            analysis = self._evaluate_setup_row(setup, daily_scores)
            if analysis.get("is_active"):
                return {
                    "status": "active",
                    "asset": asset,
                    "setup_id": setup.get("id"),
                    "has_scores": bool(daily_scores),
                    "match_percentage": analysis.get("match_percentage"),
                    "reasons": [],
                }
            blockers = analysis.get("blockers") or []
            missing = analysis.get("missing_checks") or []
            reasons = [
                f"{item.get('category')} score {item.get('score')} buiten {item.get('range')}"
                for item in blockers[:3]
            ]
            if missing:
                reasons.extend([
                    f"{item.get('category')} score of range ontbreekt"
                    for item in missing[:3]
                ])
            return {
                "status": "blocked" if blockers else "data_missing",
                "asset": asset,
                "setup_id": setup.get("id"),
                "has_scores": bool(daily_scores),
                "match_percentage": analysis.get("match_percentage"),
                "reasons": reasons or ["setup is niet actief volgens de huidige score-context"],
            }
        except Exception:
            return None

    def _append_plan_deviation_context(self, event: Dict[str, Any], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not context or context.get("status") == "active":
            return event
        context_reasons = context.get("reasons") or []
        reasons = list(event.get("reasons") or [])
        if context.get("status") == "blocked":
            reasons.append("actie terwijl setup-score blokkeert")
        elif context.get("status") == "data_missing":
            reasons.append("actie terwijl scoredata of setup-check incompleet is")
        reasons.extend(str(reason) for reason in context_reasons[:3])
        event["reasons"] = list(dict.fromkeys(reasons))
        event["context"] = {
            "status": context.get("status"),
            "asset": context.get("asset"),
            "setup_id": context.get("setup_id"),
            "has_scores": bool(context.get("has_scores")),
            "match_percentage": context.get("match_percentage"),
            "reasons": context_reasons[:3],
        }
        if context.get("status") == "blocked":
            event["severity"] = "high"
        return event

    def _behavioral_event_from_bot_draft(self, draft: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if draft.get("operation") != "update":
            return None
        reasons = []
        for change in draft.get("changes") or []:
            field = change.get("field")
            before = self._to_float(change.get("from"))
            after = self._to_float(change.get("to"))
            if field in {"budget_total_eur", "budget_daily_limit_eur", "budget_max_order_eur"} and before is not None and after is not None and after > before:
                reasons.append(f"{field} verhoogd van {before:g} naar {after:g}")
            if field == "is_live" and change.get("from") is False and change.get("to") is True:
                reasons.append("bot naar live gezet")
            if field == "mode" and str(change.get("to") or "").lower() in {"auto", "semi-auto"} and str(change.get("from") or "").lower() == "manual":
                reasons.append(f"bot mode verhoogd naar {change.get('to')}")
        if not reasons and not (context and context.get("status") in {"blocked", "data_missing"}):
            return None
        event = {
            "type": "plan_deviation_attempt",
            "severity": "medium",
            "asset": draft.get("asset"),
            "bot_id": draft.get("bot_id"),
            "strategy_id": draft.get("strategy_id"),
            "reasons": reasons,
        }
        return self._append_plan_deviation_context(event, context)

    def _behavioral_event_from_strategy_draft(self, draft: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        if draft.get("operation") != "update":
            return None
        sensitive_fields = {"base_amount_eur", "entry", "stop_loss", "targets", "entry_type"}
        changed = [change for change in draft.get("changes") or [] if change.get("field") in sensitive_fields]
        if not changed and not (context and context.get("status") in {"blocked", "data_missing"}):
            return None
        event = {
            "type": "strategy_change_pressure",
            "severity": "low",
            "asset": draft.get("asset"),
            "setup_id": draft.get("setup_id"),
            "strategy_id": draft.get("strategy_id"),
            "reasons": [
                f"{change.get('field')} gewijzigd"
                for change in changed[:4]
            ],
        }
        return self._append_plan_deviation_context(event, context)

    async def _execute_paper_bot_decision_action(self, user_id: int, action: Dict[str, Any]) -> Dict[str, Any]:
        payload = action.get("payload") or {}
        bot_id = int(payload.get("bot_id") or 0)
        decision_id = int(payload.get("decision_id") or 0)
        if bot_id <= 0 or decision_id <= 0:
            raise HTTPException(422, "bot_id en decision_id zijn verplicht.")
        action_id = f"{action.get('id') or self._maintenance_action_id('paper_execute_bot_decision', [str(bot_id), str(decision_id)])}-u{user_id}"
        acquired = await self._try_create_pending_action(user_id, action_id, action)
        if not acquired:
            existing_result = await self._wait_for_action_result(user_id, action_id)
            if existing_result:
                return existing_result
            raise HTTPException(409, "Deze Finn actie wordt al verwerkt. Probeer zo opnieuw.")

        bot_service = BotService(self.session)
        bot = await bot_service.repository.get_bot_config(user_id, bot_id)
        if not bot:
            await self._upsert_action_audit(user_id, action_id, action, status="failed", result={"ok": False, "bot_id": bot_id, "decision_id": decision_id})
            raise HTTPException(404, "Bot niet gevonden.")
        if bot.get("is_live"):
            await self._upsert_action_audit(user_id, action_id, action, status="failed", result={"ok": False, "bot_id": bot_id, "decision_id": decision_id, "reason": "live_bot"})
            raise HTTPException(422, "Live bots moeten eerst door live preflight; Finn voert live orders niet vanuit deze stap uit.")

        try:
            executed = await bot_service.mark_bot_executed(bot_id, decision_id, user_id)
            status = await self._read_bot_decision_status(user_id, decision_id)
        except Exception:
            await self.session.rollback()
            await self._upsert_action_audit(user_id, action_id, action, status="failed", result={"ok": False, "bot_id": bot_id, "decision_id": decision_id})
            raise

        result = {
            "ok": bool(executed.get("ok")),
            "message": f"Bot-decision #{decision_id} is als paper/manual execution verwerkt.",
            "action_id": action_id,
            "bot_id": bot_id,
            "decision_id": decision_id,
            "status": status,
            "verified": {"paper_execution": bool(executed.get("ok"))},
        }
        behavioral_event = self._behavioral_event_from_execution_action(action, result_status=status)
        if behavioral_event:
            result["behavioral_event"] = behavioral_event
        await self._upsert_action_audit(user_id, action_id, action, status="executed", result=result)
        return result

    async def _execute_live_preflight_bot_decision_action(self, user_id: int, action: Dict[str, Any]) -> Dict[str, Any]:
        payload = action.get("payload") or {}
        bot_id = int(payload.get("bot_id") or 0)
        decision_id = int(payload.get("decision_id") or 0)
        if bot_id <= 0 or decision_id <= 0:
            raise HTTPException(422, "bot_id en decision_id zijn verplicht.")
        action_id = f"{action.get('id') or self._maintenance_action_id('live_preflight_bot_decision', [str(bot_id), str(decision_id)])}-u{user_id}"
        acquired = await self._try_create_pending_action(user_id, action_id, action)
        # Live preflight is a read-only safety check. Re-run it against live DB
        # state even when the same action id was executed before, because
        # decision freshness can change minute by minute.
        if not acquired:
            await asyncio.sleep(0)

        bot_service = BotService(self.session)
        bot = await bot_service.repository.get_bot_config(user_id, bot_id)
        keys = await ExchangeRepository(self.session).get_active_keys(user_id)
        freshness = None
        stale_block = None
        if bot and bot.get("is_live") and keys:
            try:
                freshness = await bot_service.require_fresh_live_decision_context(user_id, bot_id)
            except HTTPException as exc:
                stale_block = exc.detail
        ready = bool(bot and bot.get("is_live") and keys and not stale_block)
        result = {
            "ok": True,
            "message": (
                "Live preflight geslaagd. Review alsnog handmatig voordat je buiten Finn live uitvoert."
                if ready else (
                    "Live preflight blokkeert: decision/score context is niet vers genoeg."
                    if stale_block else "Live preflight blokkeert: live bot of actieve exchange keys ontbreken."
                )
            ),
            "action_id": action_id,
            "bot_id": bot_id,
            "decision_id": decision_id,
            "live_preflight_token": action_id,
            "verified": {
                "live_preflight": ready,
                "live_bot": bool(bot and bot.get("is_live")),
                "exchange_keys": bool(keys),
                "fresh_decision_context": bool(freshness and freshness.get("fresh")),
            },
        }
        if freshness or stale_block:
            result["freshness"] = freshness or (stale_block or {}).get("freshness")
        if stale_block:
            result["stale_data_block"] = stale_block
        behavioral_event = self._behavioral_event_from_execution_action(action, result_status="ready" if ready else "blocked")
        if behavioral_event:
            result["behavioral_event"] = behavioral_event
        await self._upsert_action_audit(user_id, action_id, action, status="executed", result=result)
        return result

    async def _read_bot_decision_status(self, user_id: int, decision_id: int) -> Optional[str]:
        rows = await BotService(self.session).repository.get_bot_decisions_by_date(user_id, _utc_now().date())
        row = next((item for item in rows if int(item.get("id") or 0) == int(decision_id)), None)
        return str(row.get("status")) if row else None

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
        pressure_context = await self._plan_deviation_context_for_draft(user_id, draft)
        behavioral_event = self._behavioral_event_from_strategy_draft(draft, pressure_context)
        if behavioral_event:
            result["behavioral_event"] = behavioral_event
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
            pressure_context = await self._plan_deviation_context_for_draft(user_id, draft)
            behavioral_event = self._behavioral_event_from_bot_draft(draft, pressure_context)
            draft["plan_deviation"] = self._plan_deviation_warning_from_event(behavioral_event, acknowledged=bool(draft.get("plan_deviation_ack")))
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
                pressure_context = await self._plan_deviation_context_for_draft(user_id, draft)
                behavioral_event = self._behavioral_event_from_strategy_draft(draft, pressure_context)
                draft["plan_deviation"] = self._plan_deviation_warning_from_event(behavioral_event, acknowledged=bool(draft.get("plan_deviation_ack")))
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
            "trace_id": self.trace_id,
            "updated_at": _utc_now().isoformat(),
        }
        row = await self.session.execute(text("""
            INSERT INTO ai_pending_actions (id, user_id, type, payload, status, expires_at, trace_id)
            VALUES (:id, :user_id, 'finn_create_plan', CAST(:payload AS JSONB), 'pending', :expires_at, :trace_id)
            ON CONFLICT (id) DO NOTHING
            RETURNING id
        """), {
            "id": action_id,
            "user_id": user_id,
            "payload": json.dumps(payload),
            "expires_at": _utc_db_timestamp() + timedelta(days=7),
            "trace_id": self.trace_id,
        })
        acquired = row.fetchone() is not None
        if not acquired:
            claim = await self.session.execute(text("""
                UPDATE ai_pending_actions
                SET status = 'executing',
                    trace_id = COALESCE(:trace_id, trace_id)
                WHERE id = :id
                  AND user_id = :user_id
                  AND status = 'pending'
                RETURNING id
            """), {
                "id": action_id,
                "user_id": user_id,
                "trace_id": self.trace_id,
            })
            acquired = claim.fetchone() is not None
        await self.session.commit()
        return acquired

    async def issue_response_actions(self, user_id: int, response: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(response, dict):
            return response
        await self._issue_actions_in_structure(user_id, response)
        return response

    async def _issue_actions_in_structure(self, user_id: int, node: Any) -> Any:
        if isinstance(node, list):
            for item in node:
                await self._issue_actions_in_structure(user_id, item)
            return node
        if not isinstance(node, dict):
            return node

        if self._is_server_issued_action(node):
            action_id = node.get("action_id") or f"{node.get('id') or self._maintenance_action_id(node.get('type'), [json.dumps(node, sort_keys=True, default=str)])}-u{user_id}"
            if not self._should_skip_pending_action_issue(node):
                await self._issue_pending_action(user_id, action_id, node)
            node["action_id"] = action_id

        for value in node.values():
            await self._issue_actions_in_structure(user_id, value)
        return node

    def _is_server_issued_action(self, action: Dict[str, Any]) -> bool:
        if not isinstance(action, dict):
            return False
        action_type = action.get("type")
        if not action_type or action_type == "chat_prompt":
            return False
        return action_type in {
            "create_plan",
            "refresh_daily_scores",
            "generate_bot_decision",
            "skip_bot_decision",
            "paper_execute_bot_decision",
            "live_preflight_bot_decision",
            "resolve_mission_item",
            "snooze_mission_item",
            "agent_controller_handoff",
            "configure_indicator",
            "create_bot",
            "create_strategy",
        }

    def _should_skip_pending_action_issue(self, action: Dict[str, Any]) -> bool:
        if not isinstance(action, dict):
            return False
        return str(action.get("type") or "") == "refresh_daily_scores"

    async def _issue_pending_action(self, user_id: int, action_id: str, action: Dict[str, Any]) -> None:
        if not self.session:
            return
        payload = {
            "action": action,
            "result": None,
            "trace_id": self.trace_id,
            "updated_at": _utc_now().isoformat(),
            "issued_by": "finn_server",
        }
        await self.session.execute(text("""
            INSERT INTO ai_pending_actions (id, user_id, type, payload, status, expires_at, trace_id)
            VALUES (:id, :user_id, 'finn_create_plan', CAST(:payload AS JSONB), 'pending', :expires_at, :trace_id)
            ON CONFLICT (id) DO NOTHING
        """), {
            "id": action_id,
            "user_id": user_id,
            "payload": json.dumps(payload),
            "expires_at": _utc_db_timestamp() + timedelta(days=7),
            "trace_id": self.trace_id,
        })
        await self.session.commit()

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
        if isinstance(result, dict):
            action = payload.get("action") if isinstance(payload.get("action"), dict) else {}
            result = self._hydrate_legacy_follow_through_result(action, result)
            return {**result, "replayed": True}
        return None

    def _hydrate_legacy_follow_through_result(self, action: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(action, dict) or not isinstance(result, dict):
            return result
        action_type = str(action.get("type") or "")
        if action_type == "skip_bot_decision":
            if result.get("operator_resolution") and result.get("action_follow_through"):
                return result
            decision_id = self._safe_int((result.get("decision_id")) or ((action.get("payload") or {}).get("decision_id")))
            resolution = {
                "type": "operator_resolution",
                "title": f"Bot-decision #{decision_id} bewust overgeslagen" if decision_id else "Bot-decision bewust overgeslagen",
                "status": "skipped",
                "summary": "Je hebt deze decision niet doorgedrukt; Finn legt dat vast als bewuste frictie.",
                "what_changed": [
                    f"Decision #{decision_id} staat nu op skipped." if decision_id else "Deze decision staat nu op skipped.",
                    "Deze review telt niet meer als open actie voor vandaag.",
                ],
                "what_next": [
                    "Ga alleen opnieuw naar een decision als de context echt veranderd is.",
                    "Pak liever de volgende open review of prioriteit op.",
                ],
            }
            analysis = result.get("state", {}).get("analysis") if isinstance(result.get("state"), dict) else None
            merged_analysis = {
                **(analysis if isinstance(analysis, dict) else {}),
                "operator_resolution": resolution,
                "action_follow_through": resolution,
            }
            return {
                **result,
                "operator_resolution": resolution,
                "action_follow_through": resolution,
                "state": {
                    **(result.get("state") if isinstance(result.get("state"), dict) else {}),
                    "analysis": merged_analysis,
                },
            }
        return result

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
        if isinstance(result, dict) and self.trace_id and not result.get("trace_id"):
            result = {**result, "trace_id": self.trace_id}
        payload = {
            "action": action,
            "result": result,
            "trace_id": self.trace_id,
            "updated_at": _utc_now().isoformat(),
        }
        await self.session.execute(text("""
            INSERT INTO ai_pending_actions (id, user_id, type, payload, status, expires_at, trace_id)
            VALUES (:id, :user_id, 'finn_create_plan', CAST(:payload AS JSONB), :status, :expires_at, :trace_id)
            ON CONFLICT (id) DO UPDATE SET
                payload = EXCLUDED.payload,
                status = EXCLUDED.status,
                trace_id = COALESCE(EXCLUDED.trace_id, ai_pending_actions.trace_id)
            WHERE ai_pending_actions.user_id = EXCLUDED.user_id
        """), {
            "id": action_id,
            "user_id": user_id,
            "payload": json.dumps(payload),
            "status": status,
            "expires_at": _utc_db_timestamp() + timedelta(days=7),
            "trace_id": self.trace_id,
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
