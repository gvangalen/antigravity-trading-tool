import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

from fastapi import HTTPException

import backend.services.finn_plan_service as finn_plan_module
from backend.services.finn_plan_service import FinnPlanService
from backend.services.finn_plan_service import _utc_now
from backend.services.finn_plan_service import empty_indicator_config_draft
from backend.services.ai_action_engine import _utc_db_timestamp
from backend.services.ai_assistant_service import AiAssistantService
from backend.services.strategy_service import StrategyService
from backend.schemas.assistant_schema import AssistantContextSchema


def _service():
    return FinnPlanService(db_session=None)


class _MemoryStateRepo:
    store = {}

    def __init__(self, session):
        self.session = session

    async def get_state(self, user_id):
        return self.store.get(user_id)

    async def save_state(self, user_id, current_flow, asset, slots):
        self.store[user_id] = {
            "current_flow": current_flow,
            "asset": asset,
            "updated_at": _utc_now(),
            "slots": slots,
        }

    async def clear_state(self, user_id):
        self.store.pop(user_id, None)


async def _route_turn(service, user_id, query, context=None):
    hydrated = await service.hydrate_context(user_id, context or {})
    sanitized = service.sanitize_context_for_query(query, hydrated)
    draft_used = bool(isinstance(sanitized.get("finn_draft"), dict))

    if service.looks_like_general_capability_request(query):
        response = {
            "intent": "general_help",
            "flow": "general_help",
            "response": "help",
            "state": {"current_flow": "general_help"},
        }
    elif service.looks_like_education_request(query):
        response = {
            "intent": "education",
            "flow": "education",
            "response": "education",
            "state": {"current_flow": "education"},
        }
    elif service.looks_like_plan_adherence_review_request(query):
        response = {
            "intent": "plan_adherence_review",
            "flow": "plan_adherence_review",
            "response": "adherence",
            "state": {"current_flow": "plan_adherence_review"},
        }
    elif service.looks_like_decision_review_request(query, sanitized):
        response = {
            "intent": "decision_review",
            "flow": "decision_review",
            "response": "review",
            "state": {"current_flow": "decision_review"},
        }
    elif service.looks_like_entity_explain_request(query, sanitized):
        response = {
            "intent": "context_explain",
            "flow": "context_explain",
            "response": "explain",
            "state": {"current_flow": "context_explain"},
        }
    elif service.looks_like_behavioral_intelligence_request(query):
        response = {
            "intent": "behavioral_intelligence",
            "flow": "behavioral_intelligence",
            "response": "coaching",
            "state": {"current_flow": "behavioral_intelligence"},
        }
    elif service.looks_like_bot_request(query, sanitized):
        response = {
            "intent": "bot_creation",
            "flow": "bot_creation",
            "response": "bot",
            "draft": {
                "draft_kind": "bot",
                "asset": sanitized.get("symbol") or sanitized.get("asset") or "BTC",
                "strategy_id": sanitized.get("strategy_id") or 257,
            },
            "state": {"current_flow": "bot_creation"},
            "missing_fields": [],
            "invalid_fields": [],
            "can_confirm": False,
        }
    elif service.looks_like_plan_request(query, sanitized.get("finn_draft")):
        response = service.build_response(query, sanitized)
    else:
        response = {
            "intent": "unknown",
            "flow": "unknown",
            "response": "unknown",
            "state": {"current_flow": "unknown"},
        }

    await service.persist_response_state(user_id, response)
    return response, sanitized


def test_assistant_context_preserves_transactional_follow_up_state():
    context = AssistantContextSchema(
        current_flow="bot_decision",
        pending_behavioral_memory_friction={
            "type": "decision_churn",
            "requires_ack": True,
        },
    )

    payload = context.dict(exclude_none=True)

    assert payload["current_flow"] == "bot_decision"
    assert payload["pending_behavioral_memory_friction"]["type"] == "decision_churn"


def test_sanitize_context_drops_stale_bot_draft_for_education_prompt():
    service = _service()
    context = {
        "symbol": "BTC",
        "finn_draft": {
            "draft_kind": "bot",
            "operation": "create",
            "asset": "ETH",
            "strategy_id": 257,
            "existing_bot_id": 130,
        },
        "finn_state": {"current_flow": "bot_creation"},
        "current_flow": "bot_creation",
    }

    sanitized = service.sanitize_context_for_query("Wat is RSI in simpele taal?", context)

    assert "finn_draft" not in sanitized
    assert "finn_state" not in sanitized
    assert sanitized.get("current_flow") is None


def test_sanitize_context_keeps_bot_draft_for_real_transactional_follow_up():
    service = _service()
    context = {
        "finn_draft": {
            "draft_kind": "bot",
            "operation": "create",
            "strategy_id": 257,
        },
        "finn_state": {
            "current_flow": "bot_creation",
            "updated_at": _utc_now().isoformat(),
        },
        "current_flow": "bot_creation",
    }

    sanitized = service.sanitize_context_for_query("strategie 257", context)

    assert sanitized["finn_draft"]["draft_kind"] == "bot"
    assert sanitized["current_flow"] == "bot_creation"


def test_sanitize_context_drops_stale_plan_draft_for_setup_explain_prompt():
    service = _service()
    context = {
        "setup_id": 62,
        "current_flow": "plan_creation",
        "finn_draft": {
            "plan_type": "trade",
            "asset": "BTC",
            "setup": {"name": "BTC Trade Plan"},
        },
    }

    sanitized = service.sanitize_context_for_query("Leg mijn setup uit", context)

    assert "finn_draft" not in sanitized
    assert sanitized.get("current_flow") is None


def test_sanitize_context_drops_stale_plan_draft_for_fomo_prompt():
    service = _service()
    context = {
        "current_flow": "plan_creation",
        "finn_draft": {
            "plan_type": "trade",
            "asset": "BTC",
        },
    }

    sanitized = service.sanitize_context_for_query("Ik voel FOMO, wat moet ik doen?", context)

    assert "finn_draft" not in sanitized
    assert sanitized.get("current_flow") is None


def test_sanitize_context_drops_conflicting_transactional_draft_for_other_asset():
    service = _service()
    context = {
        "symbol": "BTC",
        "current_flow": "plan_creation",
        "finn_state": {"current_flow": "plan_creation", "updated_at": _utc_now().isoformat()},
        "finn_draft": {
            "plan_type": "trade",
            "asset": "ETH",
        },
    }

    sanitized = service.sanitize_context_for_query("Maak een BTC setup", context)

    assert "finn_draft" not in sanitized
    assert "finn_state" not in sanitized
    assert sanitized.get("current_flow") is None


def test_sanitize_context_drops_expired_transactional_draft():
    service = _service()
    stale = (_utc_now() - timedelta(minutes=90)).isoformat()
    context = {
        "current_flow": "bot_creation",
        "finn_state": {"current_flow": "bot_creation", "updated_at": stale},
        "finn_draft": {
            "draft_kind": "bot",
            "asset": "BTC",
            "strategy_id": 257,
        },
    }

    sanitized = service.sanitize_context_for_query("strategie 257", context)

    assert "finn_draft" not in sanitized
    assert "finn_state" not in sanitized
    assert sanitized.get("current_flow") is None


def test_bot_request_detection_does_not_hijack_general_or_explain_prompts():
    service = _service()
    context = {
        "finn_draft": {
            "draft_kind": "bot",
            "operation": "create",
            "strategy_id": 257,
        },
        "strategy_id": 257,
    }

    assert service.looks_like_bot_request("Hoi FINN, wat kun je voor mij doen?", context) is False
    assert service.looks_like_bot_request("Welke strategie bekijk ik nu?", context) is False
    assert service.looks_like_bot_request("Wat is RSI in simpele taal?", context) is False


def test_education_and_general_request_detection_are_explicit():
    service = _service()

    assert service.looks_like_general_capability_request("Hoi FINN, wat kun je voor mij doen?") is True
    assert service.looks_like_product_help_request("Wat kan ik hier doen?", {"page_type": "Dashboard"}) is True
    assert service.looks_like_mission_control_explain_request("Vat Mission Control samen in drie bullets", {"scope": "mission_control"}) is True
    assert service.looks_like_education_request("Wat is RSI in simpele taal?") is True
    assert service.looks_like_education_request("Wat is DCA?") is True
    assert service.looks_like_behavioral_intelligence_request("Ik voel FOMO, wat moet ik doen?") is True
    assert service.looks_like_behavioral_intelligence_request("Ik denk eraan om all-in te gaan, wat moet ik doen?") is True
    assert service.looks_like_behavioral_intelligence_request("Ik wijk af van mijn strategie, wat moet ik doen?") is True
    assert service.looks_like_entity_explain_request(
        "Welke strategie bekijk ik nu?",
        {"strategy_id": 257, "page": "/strategy"},
    ) is True
    assert service.looks_like_entity_explain_request(
        "Leg mijn setup uit",
        {"setup_id": 62, "page": "/setup"},
    ) is True
    assert service.looks_like_entity_explain_request(
        "Welk rapport zie ik nu?",
        {"page_type": "report", "page": "/report"},
    ) is True


def test_build_education_response_covers_core_topic_in_simple_mode():
    service = _service()

    result = asyncio.run(service.build_education_response(30, "Wat is Wyckoff in simpele taal?"))

    assert result["intent"] == "education"
    assert result["flow"] == "education"
    assert result["state"]["topic"] == "wyckoff"
    assert result["analysis"]["topic_label"] == "Wyckoff"
    assert result["analysis"]["difficulty"] == "simple"
    assert result["analysis"]["confidence"] == "high"
    assert "Wat het is:" in result["response"]
    assert "Waarom het telt:" in result["response"]
    assert "Veilig gebruiken:" in result["response"]
    assert "Veelgemaakte fout:" in result["response"]
    assert result["analysis"]["what_it_is"]
    assert result["analysis"]["why_it_matters"]
    assert result["analysis"]["how_to_use_it_safely"]
    assert result["analysis"]["common_mistake"]


def test_build_education_response_handles_do_nothing_guidance():
    service = _service()

    result = asyncio.run(service.build_education_response(30, "Wanneer zou jij zeggen dat ik beter even niets doe?"))

    assert result["intent"] == "education"
    assert result["state"]["topic"] == "do_nothing"
    assert "Niets doen" in result["analysis"]["topic_label"]
    assert "geen slechte trade" in result["response"].lower()


def test_context_confidence_prefers_strong_page_entity():
    service = _service()

    confidence = service._context_confidence({
        "page_type": "Strategy",
        "strategy_id": 257,
        "symbol": "ETH",
    })

    assert confidence["level"] == "high"
    assert confidence["entity_type"] == "strategy"
    assert confidence["entity_id"] == 257
    assert confidence["reason"] == "page_entity_match"
    assert confidence["why"] == "page context matched active strategy"


def test_context_confidence_stays_low_without_entity():
    service = _service()

    confidence = service._context_confidence({
        "page_type": "Dashboard",
        "symbol": "BTC",
    })

    assert confidence["level"] == "low"
    assert confidence["entity_type"] == "unknown"
    assert confidence["entity_id"] is None
    assert confidence["reason"] == "generic_fallback"


def test_build_context_explain_response_returns_low_confidence_fallback_without_entity():
    service = _service()

    result = asyncio.run(service.build_context_explain_response(30, "Welke setup heb ik nu open?", {
        "page": "/dashboard",
        "page_type": "Dashboard",
        "symbol": "BTC",
    }))

    assert result["intent"] == "context_explain"
    assert result["analysis"]["entity_type"] == "setup"
    assert result["analysis"]["context_confidence"]["level"] == "low"
    assert "BTC als je actieve asset-context" in result["response"]
    assert "geen zekere setup-entiteit" in result["response"]


def test_build_context_explain_response_can_explain_current_page():
    service = _service()

    result = asyncio.run(service.build_context_explain_response(30, "Wat bekijk ik nu?", {
        "page": "/dashboard",
        "page_type": "Dashboard",
        "symbol": "BTC",
    }))

    assert result["intent"] == "context_explain"
    assert result["analysis"]["entity_type"] == "page"
    assert result["analysis"]["context_confidence"]["level"] == "high"
    assert "dashboard" in result["response"].lower()


def test_build_product_help_response_includes_supported_and_not_supported_capabilities():
    service = _service()

    result = asyncio.run(service.build_product_help_response(30, "Wat kan ik hier doen?", {
        "page": "/strategy/257",
        "page_type": "Strategy",
        "strategy_id": 257,
        "symbol": "ETH",
    }))

    assert result["intent"] == "product_help"
    assert result["flow"] == "product_help"
    assert result["analysis"]["product_help"]["current_entity"]["strategy_id"] == 257
    assert "watchlist_wijzigen_via_finn" in result["analysis"]["product_help"]["not_supported_yet"]
    assert "uitleg van je huidige scherm" in result["response"]


def test_build_behavioral_intelligence_response_exposes_safe_coaching_contract(monkeypatch):
    service = FinnPlanService(db_session=object())
    service._get_recent_finn_activity = AsyncMock(return_value=[])
    service._mission_day_log = lambda activity_feed: {"handled_count": 0, "skipped_count": 0, "snoozed_count": 0}
    service._build_behavioral_insight_from_activity = lambda activity_feed, day_log: {
        "status": "attention",
        "trend": {"summary": "Je drukt wat hard op nieuwe acties."},
        "coaching": {
            "primary_reflection": "Ik zie druk om sneller te handelen dan je plan vraagt.",
            "safe_next_step": "Wacht tot je plan weer helder actief is.",
            "do_not_do": "Ga nu niet forceren of all-in.",
        },
        "risk_flags": [{"id": "fomo_pressure", "summary": "Je zoekt versnelling zonder extra duidelijkheid."}],
    }

    result = asyncio.run(service.build_behavioral_intelligence_response(30, "Ik voel FOMO, wat moet ik doen?"))

    assert result["intent"] == "behavioral_intelligence"
    analysis = result["state"]["analysis"]
    assert analysis["variant"] == "direct_coach"
    assert analysis["risk_signal"] == "fomo_pressure"
    assert analysis["what_i_notice"] == "Ik zie druk om sneller te handelen dan je plan vraagt."
    assert analysis["why_this_is_risky"] == "Je zoekt versnelling zonder extra duidelijkheid."
    assert analysis["what_to_do_now"] == "Wacht tot je plan weer helder actief is."
    assert analysis["what_not_to_do"] == "Ga nu niet forceren of all-in."
    assert analysis["behavioral_intelligence"]["variant"] == "direct_coach"
    assert "Stop even en vertraag direct." in result["response"]


def test_build_context_explain_response_prioritizes_score_explain_when_asset_context_is_present(monkeypatch):
    class ScoreRepo:
        def __init__(self, session):
            self.session = session

        async def fetch_daily_scores(self, user_id, symbol):
            return {
                "macro_score": 50,
                "technical_score": 42,
                "market_score": 18,
                "setup_score": 73,
            }

    monkeypatch.setattr("backend.services.finn_plan_service.ScoreRepository", ScoreRepo)
    service = FinnPlanService(db_session=object())
    service._fetch_daily_scores_with_runtime_refresh = AsyncMock(return_value={
        "macro_score": 50,
        "technical_score": 42,
        "market_score": 18,
        "setup_score": 73,
    })

    result = asyncio.run(service.build_context_explain_response(30, "Welke score zie ik nu?", {
        "page": "/dashboard",
        "page_type": "Dashboard",
        "symbol": "BTC",
        "strategy_id": 257,
    }))

    assert result["intent"] == "context_explain"
    assert result["analysis"]["entity_type"] == "score"
    assert result["analysis"]["entity"]["asset"] == "BTC"
    assert result["analysis"]["entity"]["weakest_component"]["category"] == "market"
    assert result["analysis"]["entity"]["top_support"]["category"] == "setup"
    assert result["analysis"]["context_confidence"]["level"] == "high"
    assert "Macro is 50.0" in result["response"]


def test_build_context_explain_response_can_summarize_report_entity(monkeypatch):
    class Repo:
        def __init__(self, session):
            self.session = session

        async def get_latest_report(self, user_id, table_name, symbol=None):
            return {
                "id": 7,
                "report_date": "2026-05-30",
                "summary": "BTC bleef onder druk en vroeg vooral om geduld.",
            }

    monkeypatch.setattr("backend.services.finn_plan_service.ReportRepository", Repo)
    service = FinnPlanService(db_session=object())

    result = asyncio.run(service.build_context_explain_response(30, "Leg mijn weekrapport uit", {
        "page": "/report",
        "page_type": "Report",
    }))

    assert result["intent"] == "context_explain"
    assert result["analysis"]["entity_type"] == "report"
    assert result["analysis"]["entity"]["table_name"] == "weekly_reports"
    assert result["analysis"]["entity"]["report_type"] == "weekrapport"
    assert result["analysis"]["entity"]["headline"] == "BTC bleef onder druk en vroeg vooral om geduld."
    assert result["analysis"]["context_confidence"]["level"] == "high"
    assert "weekrapport" in result["response"].lower()
    assert "BTC bleef onder druk" in result["response"]


def test_build_context_explain_response_enriches_bot_entity_from_repository(monkeypatch):
    class Repo:
        async def get_bot_config(self, user_id, bot_id):
            return {
                "id": bot_id,
                "name": "BTC Review Bot",
                "symbol": "BTC",
                "is_active": True,
                "is_live": False,
                "strategy_id": 257,
                "strategy_name": "ETH Live QA Strategy 542357",
                "setup_id": 62,
                "setup_name": "Breakout long test",
            }

    class FakeBotService:
        def __init__(self, session):
            self.repository = Repo()

        async def get_bot_today(self, user_id, symbol=None, lean=False):
            return {
                "decisions": [
                    {"id": 121110, "bot_id": 17, "status": "needs_review"},
                ]
            }

    monkeypatch.setattr("backend.services.finn_plan_service.BotService", FakeBotService)
    service = FinnPlanService(db_session=object())

    result = asyncio.run(service.build_context_explain_response(30, "Leg mijn bot uit", {
        "page": "/bot/17",
        "page_type": "Bot",
        "bot_id": 17,
    }))

    assert result["intent"] == "context_explain"
    assert result["analysis"]["entity_type"] == "bot"
    assert result["analysis"]["entity"]["id"] == 17
    assert result["analysis"]["entity"]["what_this_bot_is"] == "Een paper/manual bot voor BTC"
    assert result["analysis"]["entity"]["current_state"] == "reviewing"
    assert result["analysis"]["entity"]["open_decisions"][0]["id"] == 121110
    assert result["analysis"]["context_confidence"]["level"] == "high"
    assert "BTC Review Bot" in result["response"]
    assert "Breakout long test" in result["response"]
    assert "open bot-decision review" in result["response"]
    assert "Review eerst de open bot-decisions" in result["response"]


def test_entity_explain_detects_asset_and_bot_context_without_drifting_to_daily_coach():
    service = _service()

    assert service.looks_like_entity_explain_request(
        "Met welke asset en bot werk ik nu?",
        {"page": "/bot/17", "page_type": "Bot", "symbol": "BTC", "bot_id": 17},
    ) is True


def test_build_context_explain_response_can_answer_current_asset():
    service = _service()

    result = asyncio.run(service.build_context_explain_response(30, "Met welke asset werk ik nu?", {
        "page": "/dashboard",
        "page_type": "Dashboard",
        "symbol": "BTC",
    }))

    assert result["intent"] == "context_explain"
    assert result["analysis"]["entity_type"] == "asset"
    assert result["analysis"]["entity"]["asset"] == "BTC"
    assert result["analysis"]["context_confidence"]["reason"] == "explicit_context_match"
    assert result["analysis"]["context_entity_resolution"]["target"] == "asset"
    assert result["analysis"]["context_entity_resolution"]["resolved_from"] == "explicit_prompt_or_context"
    assert result["analysis"]["context_entity_resolution"]["resolved_asset"] == "BTC"


def test_build_context_explain_response_can_answer_current_asset_and_bot(monkeypatch):
    class Repo:
        async def get_bot_config(self, user_id, bot_id):
            return {
                "id": bot_id,
                "name": "BTC Review Bot",
                "symbol": "BTC",
                "strategy_id": 257,
            }

    class FakeBotService:
        def __init__(self, session):
            self.repository = Repo()

    monkeypatch.setattr("backend.services.finn_plan_service.BotService", FakeBotService)
    service = FinnPlanService(db_session=object())

    result = asyncio.run(service.build_context_explain_response(30, "Met welke asset en bot werk ik nu?", {
        "page": "/bot/17",
        "page_type": "Bot",
        "symbol": "BTC",
        "bot_id": 17,
    }))

    assert result["intent"] == "context_explain"
    assert result["analysis"]["entity_type"] == "asset"
    assert result["analysis"]["context_entity_resolution"]["target"] == "asset"
    assert "BTC" in result["response"]
    assert "BTC Review Bot" in result["response"]


def test_build_context_explain_response_uses_asset_specific_low_confidence_message_for_strategy():
    service = _service()

    result = asyncio.run(service.build_context_explain_response(30, "Welke strategie bekijk ik nu?", {
        "page": "/dashboard",
        "page_type": "Dashboard",
        "symbol": "BTC",
    }))

    assert result["intent"] == "context_explain"
    assert result["analysis"]["entity_type"] == "strategy"
    assert "Ik zie wel BTC als je actieve asset-context" in result["response"]
    assert "geen zekere strategie-entiteit" in result["response"]


def test_context_explain_reuses_recent_strategy_entity_in_mixed_session():
    service = _service()
    context = {
        "page": "/dashboard",
        "page_type": "Dashboard",
        "symbol": "ETH",
        "finn_state": {
            "current_flow": "general_help",
            "recent_context_entities": [
                {
                    "entity_type": "strategy",
                    "entity_id": 257,
                    "asset": "ETH",
                    "resolved_from": "page_context",
                }
            ],
            "analysis": {},
        },
    }

    result = asyncio.run(service.build_context_explain_response(30, "Welke strategie bekijk ik nu?", context))

    assert result["intent"] == "context_explain"
    assert result["analysis"]["entity_type"] == "strategy"
    assert result["analysis"]["context_confidence"]["level"] == "medium"
    assert result["analysis"]["context_entity_resolution"]["resolved_from"] == "recent_read_only_state"
    assert "geen zekere strategie-entiteit" not in result["response"]


def test_context_explain_reuses_recent_setup_entity_in_mixed_session():
    service = _service()
    context = {
        "page": "/dashboard",
        "page_type": "Dashboard",
        "symbol": "BTC",
        "finn_state": {
            "current_flow": "education",
            "recent_context_entities": [
                {
                    "entity_type": "setup",
                    "entity_id": 62,
                    "asset": "BTC",
                    "resolved_from": "page_context",
                }
            ],
            "analysis": {},
        },
    }

    result = asyncio.run(service.build_context_explain_response(30, "Welke setup heb ik nu open?", context))

    assert result["intent"] == "context_explain"
    assert result["analysis"]["entity_type"] == "setup"
    assert result["analysis"]["context_confidence"]["level"] == "medium"
    assert result["analysis"]["context_entity_resolution"]["resolved_from"] == "recent_read_only_state"
    assert "geen zekere setup-entiteit" not in result["response"]


def test_context_explain_prefers_latest_compatible_recent_entity_and_ignores_conflict():
    service = _service()
    context = {
        "page": "/dashboard",
        "page_type": "Dashboard",
        "symbol": "ETH",
        "finn_state": {
            "current_flow": "general_help",
            "recent_context_entities": [
                {"entity_type": "strategy", "entity_id": 101, "asset": "BTC", "page_family": "strategy", "resolved_from": "page_context"},
                {"entity_type": "strategy", "entity_id": 257, "asset": "ETH", "page_family": "strategy", "resolved_from": "page_context"},
            ],
            "analysis": {},
        },
    }

    result = asyncio.run(service.build_context_explain_response(30, "Welke strategie bekijk ik nu?", context))

    assert result["analysis"]["entity"]["id"] == 257
    assert result["analysis"]["context_entity_resolution"]["resolved_from"] == "recent_read_only_state"


def test_context_explain_reuses_recent_strategy_entity_even_when_dashboard_symbol_changed():
    service = _service()
    context = {
        "page": "/dashboard",
        "page_type": "Dashboard",
        "symbol": "BTC",
        "finn_state": {
            "current_flow": "general_help",
            "recent_context_entities": [
                {"entity_type": "strategy", "entity_id": 257, "asset": "ETH", "page_family": "strategy", "resolved_from": "page_context"},
            ],
            "analysis": {},
        },
    }

    result = asyncio.run(service.build_context_explain_response(30, "Welke strategie bekijk ik nu?", context))

    assert result["analysis"]["entity"]["id"] == 257
    assert result["analysis"]["context_confidence"]["level"] == "medium"
    assert result["analysis"]["context_entity_resolution"]["resolved_from"] == "recent_read_only_state"
    assert "geen zekere strategie-entiteit" not in result["response"]


def test_context_explain_reuses_last_strategy_entity_after_broad_read_only_turn(monkeypatch):
    _MemoryStateRepo.store = {}
    monkeypatch.setattr("backend.services.finn_plan_service.ConversationStateRepository", _MemoryStateRepo)

    class _StrategyRepo:
        def __init__(self, session):
            self.session = session

        async def get_raw_strategy_with_setup(self, strategy_id, user_id):
            return {
                "id": strategy_id,
                "name": "ETH Live QA Strategy 542357",
                "symbol": "ETH",
                "timeframe": "1W",
                "setup_id": 233,
                "setup_name": "ETH Weekly Breakout",
            }

    class _StrategySvc:
        def __init__(self, session):
            self.session = session

        def _format_strategy_row(self, row):
            return row

    monkeypatch.setattr("backend.services.finn_plan_service.StrategyRepository", _StrategyRepo)
    monkeypatch.setattr("backend.services.finn_plan_service.StrategyService", _StrategySvc)
    service = FinnPlanService(db_session=object())

    first_response = asyncio.run(service.build_context_explain_response(30, "Welke strategie bekijk ik nu?", {
        "page": "/strategy/257",
        "page_type": "Strategy",
        "symbol": "ETH",
        "strategy_id": 257,
    }))
    asyncio.run(service.persist_response_state(30, first_response))

    second_response = {
        "intent": "mission_control_explain",
        "flow": "mission_control_explain",
        "response": "Mission Control zegt nu in het kort:",
        "state": {
            "current_flow": "mission_control_explain",
            "analysis": {
                "mission_control_summary": {
                    "headline": "BTC live bots vragen review",
                },
                "context_confidence": {
                    "level": "high",
                    "entity_type": "mission_control",
                    "entity_id": "mission_control",
                    "reason": "mission control summary requested",
                    "why": "mission control summary requested",
                },
            },
        },
        "analysis": {
            "mission_control_summary": {
                "headline": "BTC live bots vragen review",
            },
            "context_confidence": {
                "level": "high",
                "entity_type": "mission_control",
                "entity_id": "mission_control",
                "reason": "mission control summary requested",
                "why": "mission control summary requested",
            },
        },
    }
    asyncio.run(service.persist_response_state(30, second_response))

    hydrated = asyncio.run(service.hydrate_context(30, {
        "page": "/dashboard",
        "page_type": "Dashboard",
        "symbol": "BTC",
    }))
    result = asyncio.run(service.build_context_explain_response(30, "Welke strategie bekijk ik nu?", hydrated))

    assert result["analysis"]["entity"]["id"] == 257
    assert result["analysis"]["context_confidence"]["level"] == "medium"
    assert result["analysis"]["context_entity_resolution"]["resolved_from"] == "recent_read_only_state"
    assert "geen zekere strategie-entiteit" not in result["response"]


def test_context_explain_stays_low_when_recent_strategy_has_no_entity_id():
    service = _service()
    context = {
        "page": "/dashboard",
        "page_type": "Dashboard",
        "symbol": "ETH",
        "finn_state": {
            "current_flow": "general_help",
            "recent_context_entities": [
                {"entity_type": "strategy", "entity_id": None, "asset": "ETH", "page_family": "strategy", "resolved_from": "page_context"},
            ],
            "analysis": {},
        },
    }

    result = asyncio.run(service.build_context_explain_response(30, "Welke strategie bekijk ik nu?", context))

    assert result["analysis"]["context_confidence"]["level"] == "low"
    assert "geen zekere strategie-entiteit" in result["response"]


def test_context_explain_reuses_recent_strategy_context_on_market_follow_up(monkeypatch):
    _MemoryStateRepo.store = {}
    monkeypatch.setattr("backend.services.finn_plan_service.ConversationStateRepository", _MemoryStateRepo)

    class _Repo:
        def __init__(self, session):
            self.session = session

        async def get_raw_strategy_with_setup(self, strategy_id, user_id):
            return {
                "id": strategy_id,
                "symbol": "ETH",
                "setup_id": 233,
                "name": "ETH Live QA Strategy 542357",
                "status": "active",
                "timeframe": "1W",
                "setup_name": "ETH Weekly Breakout",
            }

    class _StrategySvc:
        def __init__(self, session):
            self.session = session

        def _format_strategy_row(self, row):
            return row

    monkeypatch.setattr("backend.services.finn_plan_service.StrategyRepository", _Repo)
    monkeypatch.setattr("backend.services.finn_plan_service.StrategyService", _StrategySvc)
    service = FinnPlanService(db_session=object())

    first_response = asyncio.run(service.build_context_explain_response(30, "Welke strategie bekijk ik nu?", {
        "page": "/strategy/257",
        "page_type": "Strategy",
        "symbol": "ETH",
        "strategy_id": 257,
    }))
    asyncio.run(service.persist_response_state(30, first_response))

    hydrated = asyncio.run(service.hydrate_context(30, {
        "page": "/market/BTC",
        "page_type": "Market",
        "symbol": "BTC",
    }))
    result = asyncio.run(service.build_context_explain_response(30, "Welke strategie bekijk ik nu?", hydrated))

    assert result["analysis"]["entity"]["id"] == 257
    assert result["analysis"]["context_confidence"]["level"] == "medium"
    assert result["analysis"]["context_entity_resolution"]["resolved_from"] == "recent_read_only_state"
    assert "geen zekere strategie-entiteit" not in result["response"]


def test_context_explain_reuses_recent_setup_context_on_market_follow_up():
    service = _service()
    context = {
        "page": "/market/BTC",
        "page_type": "Market",
        "symbol": "BTC",
        "finn_state": {
            "current_flow": "general_help",
            "recent_context_entities": [
                {"entity_type": "setup", "entity_id": 62, "asset": "BTC", "page_family": "setup", "resolved_from": "page_context"},
            ],
            "analysis": {},
        },
    }

    result = asyncio.run(service.build_context_explain_response(30, "Welke setup heb ik nu open?", context))

    assert result["analysis"]["entity"]["id"] == 62
    assert result["analysis"]["context_confidence"]["level"] == "medium"
    assert result["analysis"]["context_entity_resolution"]["resolved_from"] == "recent_read_only_state"
    assert "geen zekere setup-entiteit" not in result["response"]


def test_context_explain_reuses_recent_strategy_context_on_assistant_follow_up(monkeypatch):
    class _Repo:
        def __init__(self, session):
            self.session = session

        async def get_raw_strategy_with_setup(self, strategy_id, user_id):
            return {
                "id": strategy_id,
                "symbol": "ETH",
                "setup_id": 233,
                "name": "ETH Live QA Strategy 542357",
                "status": "active",
                "timeframe": "1W",
                "setup_name": "ETH Weekly Breakout",
            }

    class _StrategySvc:
        def __init__(self, session):
            self.session = session

        def _format_strategy_row(self, row):
            return row

    monkeypatch.setattr("backend.services.finn_plan_service.StrategyRepository", _Repo)
    monkeypatch.setattr("backend.services.finn_plan_service.StrategyService", _StrategySvc)
    service = FinnPlanService(db_session=object())
    context = {
        "page": "/assistant",
        "page_type": "assistant",
        "symbol": "BTC",
        "finn_state": {
            "current_flow": "general_help",
            "recent_context_entities": [
                {"entity_type": "strategy", "entity_id": 257, "asset": "ETH", "page_family": "strategy", "resolved_from": "page_context"},
            ],
            "analysis": {},
        },
    }

    result = asyncio.run(service.build_context_explain_response(30, "Welke strategie bekijk ik nu?", context))

    assert result["analysis"]["entity"]["id"] == 257
    assert result["analysis"]["context_confidence"]["level"] == "medium"
    assert result["analysis"]["context_entity_resolution"]["resolved_from"] == "recent_read_only_state"
    assert "geen zekere strategie-entiteit" not in result["response"]


def test_build_context_explain_response_handles_report_which_report_question(monkeypatch):
    class _ReportRepo:
        def __init__(self, session):
            self.session = session

        async def get_latest_report(self, user_id, table_name, symbol=None):
            return {
                "report_date": "2026-06-02",
                "summary": "BTC bleef zwak, setups bleven selectief.",
                "recommended_action": "Gebruik dit rapport als startpunt voor Mission Control.",
            }

    monkeypatch.setattr("backend.services.finn_plan_service.ReportRepository", _ReportRepo)
    service = FinnPlanService(db_session=object())

    result = asyncio.run(service.build_context_explain_response(30, "Welk rapport zie ik nu?", {
        "page": "/report",
        "page_type": "report",
        "symbol": "BTC",
    }))

    assert result["intent"] == "context_explain"
    assert result["analysis"]["entity_type"] == "report"
    assert result["analysis"]["context_confidence"]["level"] in {"medium", "high"}
    assert "dagrapport" in result["response"].lower() or "rapport" in result["response"].lower()


def test_build_product_refresh_help_response_stays_read_only_and_explains_stale_scores():
    service = _service()

    result = asyncio.run(service.build_product_refresh_help_response(30, "Waarom zijn mijn scores oud?", {
        "page": "/dashboard",
        "page_type": "Dashboard",
        "symbol": "BTC",
    }))

    assert result["intent"] == "product_help"
    assert result["analysis"]["tool_intent_reason"] == "safe_read_only_explain"
    assert result["analysis"]["product_help"]["variant"] == "refresh_help"
    assert result["analysis"]["product_help"]["asset"] == "BTC"
    assert "daily scoredata" in result["response"]


def test_product_refresh_help_detection_catches_stale_score_question_without_triggering_refresh():
    service = _service()

    assert service.looks_like_product_refresh_help_request("Waarom zijn mijn scores oud?") is True
    assert service.looks_like_product_refresh_help_request("Waarom zie ik nog oude data?") is True
    assert service.looks_like_product_refresh_help_request("Ververs mijn daily scores voor BTC") is False


def test_build_daily_score_refresh_response_exposes_tool_intent_reason():
    service = _service()

    result = asyncio.run(service.build_daily_score_refresh_response(30, "Ververs mijn daily scores voor BTC"))

    assert result["intent"] == "daily_score_refresh"
    assert result["analysis"]["tool_intent_reason"] == "explicit_refresh_request"
    assert result["state"]["analysis"]["tool_intent_reason"] == "explicit_refresh_request"


def test_looks_like_daily_score_refresh_request_allows_natural_wording():
    service = _service()

    assert service.looks_like_daily_score_refresh_request("Ververs mijn daily scores voor BTC") is True
    assert service.looks_like_daily_score_refresh_request("Refresh even de daily scores van BTC") is True
    assert service.looks_like_daily_score_refresh_request("Waarom zijn mijn daily scores oud?") is False


def test_build_behavioral_intelligence_response_uses_plan_adherence_variant(monkeypatch):
    service = FinnPlanService(db_session=object())
    service._get_recent_finn_activity = AsyncMock(return_value=[])
    service._mission_day_log = lambda activity_feed: {"handled_count": 0, "skipped_count": 0, "snoozed_count": 0}
    service._build_behavioral_insight_from_activity = lambda activity_feed, day_log: {
        "status": "attention",
        "trend": {"summary": "Je wilt buiten je strategie om versnellen."},
        "coaching": {
            "primary_reflection": "Ik zie dat je van je plan wilt afwijken.",
            "safe_next_step": "Leg eerst je plan naast de huidige setup en check of je regels nog actief zijn.",
            "do_not_do": "Neem nu geen shortcut omdat je ongeduldig bent.",
        },
        "risk_flags": [{"id": "plan_deviation", "summary": "Plan-afwijking maakt impulsieve trades waarschijnlijker."}],
    }

    result = asyncio.run(service.build_behavioral_intelligence_response(30, "Ik wijk af van mijn strategie, wat moet ik doen?"))

    analysis = result["state"]["analysis"]
    assert analysis["variant"] == "plan_adherence_coach"
    assert analysis["risk_signal"] == "plan_deviation"
    assert analysis["behavioral_intelligence"]["variant"] == "plan_adherence_coach"
    assert analysis["plan_anchor"]
    assert result["response"].startswith("Stop hier even en laat je plan weer leiden.")


def test_build_behavioral_intelligence_response_uses_direct_coach_for_emotional_decision(monkeypatch):
    service = FinnPlanService(db_session=object())
    service._get_recent_finn_activity = AsyncMock(return_value=[])
    service._mission_day_log = lambda activity_feed: {"handled_count": 0, "skipped_count": 0, "snoozed_count": 0}
    service._build_behavioral_insight_from_activity = lambda activity_feed, day_log: {
        "status": "attention",
        "trend": {"summary": "Ik zie emotionele druk en twijfel rond een tradebeslissing."},
        "coaching": {
            "primary_reflection": "Je wilt nu beslissen terwijl je geen helder plananker voelt.",
            "safe_next_step": "Check eerst je setupcriteria en wacht tot je plan weer leidend is.",
            "do_not_do": "Klik nu niet uit spanning of onzekerheid.",
        },
        "risk_flags": [{"id": "acute_emotion", "summary": "Emotionele twijfel maakt overrides waarschijnlijker."}],
    }

    result = asyncio.run(service.build_behavioral_intelligence_response(30, "Dit voelt als een emotionele beslissing, wat moet ik doen?"))

    analysis = result["state"]["analysis"]
    assert analysis["variant"] == "direct_coach"
    assert analysis["behavioral_intelligence"]["variant"] == "direct_coach"
    assert result["response"].startswith("Stop even en vertraag direct.")
    assert "Doe nu niets nieuws" in result["response"]
    assert "emotionele" in result["response"].lower()


def test_behavioral_detection_catches_soft_emotional_risk_language():
    service = _service()

    assert service.looks_like_behavioral_intelligence_request("Ik heb er geen goed gevoel bij, wat nu?") is True
    assert service.looks_like_behavioral_intelligence_request("Dit voelt niet goed, moet ik dit doen?") is True


def test_behavioral_variant_uses_plan_adherence_for_deviation_language():
    service = _service()

    assert service._behavioral_variant_for_query("Ik wil buiten mijn plan handelen") == "plan_adherence_coach"
    assert service._behavioral_variant_for_query("Ik wil mijn regels loslaten en toch instappen") == "plan_adherence_coach"


def test_behavioral_variant_uses_direct_coach_for_soft_emotional_language():
    service = _service()

    assert service._behavioral_variant_for_query("Ik heb er geen goed gevoel bij, wat nu?") == "direct_coach"
    assert service._behavioral_variant_for_query("Dit voelt niet goed, moet ik dit doen?") == "direct_coach"


def test_behavioral_detection_catches_frustration_and_loss_chasing_language():
    service = _service()

    assert service.looks_like_behavioral_intelligence_request("Ik wil nu handelen omdat ik gefrustreerd ben na een gemiste move.") is True
    assert service.looks_like_behavioral_intelligence_request("Ik wil het terugpakken, wat moet ik doen?") is True


def test_behavioral_variant_uses_direct_coach_for_frustration_language():
    service = _service()

    assert service._behavioral_variant_for_query("Ik wil nu handelen omdat ik gefrustreerd ben na een gemiste move.") == "direct_coach"
    assert service._behavioral_variant_for_query("Ik wil het terugpakken, wat moet ik doen?") == "direct_coach"


def test_build_behavioral_intelligence_response_uses_direct_coach_for_frustration(monkeypatch):
    service = FinnPlanService(db_session=object())
    service._get_recent_finn_activity = AsyncMock(return_value=[])
    service._mission_day_log = lambda activity_feed: {"handled_count": 0, "skipped_count": 0, "snoozed_count": 0}
    service._build_behavioral_insight_from_activity = lambda activity_feed, day_log: {
        "status": "attention",
        "trend": {"summary": "Ik zie frustratie na een gemiste move."},
        "coaching": {
            "primary_reflection": "Je wilt nu iets terugpakken.",
            "safe_next_step": "Laat de gemiste move los en wacht op een nieuwe valide trigger.",
            "do_not_do": "Open nu geen hersteltrade uit frustratie.",
        },
        "risk_flags": [{"id": "acute_emotion", "summary": "Frustratie na een gemiste move maakt revenge-achtige trades waarschijnlijker."}],
    }

    result = asyncio.run(service.build_behavioral_intelligence_response(30, "Ik wil nu handelen omdat ik gefrustreerd ben na een gemiste move."))

    analysis = result["state"]["analysis"]
    assert analysis["variant"] == "direct_coach"
    assert analysis["behavioral_intelligence"]["variant"] == "direct_coach"
    assert "frustratie" in analysis["what_i_notice"].lower()
    assert result["response"].startswith("Stop even en vertraag direct.")


def test_behavioral_detection_catches_overtrading_language():
    service = _service()

    assert service.looks_like_behavioral_intelligence_request("Ik merk dat ik aan het overtraden ben, wat moet ik doen?") is True
    assert service.looks_like_behavioral_intelligence_request("Ik wil weer handelen terwijl ik al te veel trades heb gedaan.") is True
    assert service.looks_like_behavioral_intelligence_request("Ik wil alweer instappen na te veel trades, wat moet ik doen?") is True


def test_behavioral_variant_uses_direct_coach_for_overtrading_language():
    service = _service()

    assert service._behavioral_variant_for_query("Ik merk dat ik aan het overtraden ben, wat moet ik doen?") == "direct_coach"
    assert service._behavioral_variant_for_query("Ik wil weer handelen terwijl ik al te veel trades heb gedaan.") == "direct_coach"
    assert service._behavioral_variant_for_query("Ik wil alweer instappen na te veel trades, wat moet ik doen?") == "direct_coach"


def test_build_behavioral_intelligence_response_uses_direct_coach_for_overtrading(monkeypatch):
    service = FinnPlanService(db_session=object())
    service._get_recent_finn_activity = AsyncMock(return_value=[])
    service._mission_day_log = lambda activity_feed: {"handled_count": 0, "skipped_count": 0, "snoozed_count": 0}
    service._build_behavioral_insight_from_activity = lambda activity_feed, day_log: {
        "status": "attention",
        "trend": {"summary": "Ik zie actie-drang en veel open beslissingen."},
        "coaching": {
            "primary_reflection": "Je wilt weer handelen terwijl je dag nog niet rustig is afgerond.",
            "safe_next_step": "Neem tien minuten afstand en werk eerst je open beslissingen af.",
            "do_not_do": "Open nu geen extra trade uit onrust.",
        },
        "risk_flags": [{"id": "overtrading_pressure", "summary": "Te veel activiteit verhoogt de kans op planverlies."}],
    }

    result = asyncio.run(service.build_behavioral_intelligence_response(30, "Ik merk dat ik aan het overtraden ben, wat moet ik doen?"))

    analysis = result["state"]["analysis"]
    assert analysis["variant"] == "direct_coach"
    assert analysis["behavioral_intelligence"]["variant"] == "direct_coach"
    assert "overtrading" in analysis["why_this_is_risky"].lower()
    assert result["response"].startswith("Stop even en vertraag direct.")
    assert "werk eerst je open beslissingen af" in analysis["what_to_do_now"].lower()


def test_execute_issued_action_accepts_valid_refresh_fallback_action_without_pending_row():
    service = _service()
    service.session = object()
    action = {
        "id": "finn-maint-333adbe0336899de096f330a",
        "type": "refresh_daily_scores",
        "payload": {"assets": ["BTC"], "scope": "asset"},
    }
    service._maintenance_action_id = lambda action_type, parts: "finn-maint-333adbe0336899de096f330a"
    service._get_pending_action_row = AsyncMock(return_value=None)
    service.execute_action = AsyncMock(return_value={"ok": True, "message": "Daily scores ververst"})

    result = asyncio.run(
        service.execute_issued_action(
            30,
            "finn-maint-333adbe0336899de096f330a-u30",
            fallback_action=action,
        )
    )

    service.execute_action.assert_awaited_once_with(30, action)
    assert result["ok"] is True


def test_build_response_analysis_metadata_sets_route_family():
    service = _service()

    response = service._build_response_analysis_metadata(
        {"flow": "context_explain", "analysis": {}, "state": {"current_flow": "context_explain"}},
        {"page_type": "Setup", "setup_id": 62},
    )

    assert response["analysis"]["route_family"] == "explain"
    assert response["state"]["analysis"]["route_family"] == "explain"


def test_multi_turn_regression_pack_keeps_non_transactional_turns_out_of_create_flows(monkeypatch):
    _MemoryStateRepo.store = {}
    monkeypatch.setattr("backend.services.finn_plan_service.ConversationStateRepository", _MemoryStateRepo)
    service = FinnPlanService(db_session=object())

    first_response, first_context = asyncio.run(_route_turn(
        service,
        30,
        "Maak een bot voor strategie 257",
        {"page": "/strategy/257", "page_type": "Strategy", "symbol": "ETH", "strategy_id": 257},
    ))
    second_response, second_context = asyncio.run(_route_turn(
        service,
        30,
        "Hoi FINN, wat kun je voor mij doen?",
        {"page": "/dashboard", "page_type": "Dashboard", "symbol": "BTC"},
    ))

    assert first_response["intent"] == "bot_creation"
    assert first_context.get("finn_draft") is None
    assert second_response["intent"] == "general_help"
    assert second_context.get("finn_draft") is None
    assert _MemoryStateRepo.store[30]["current_flow"] == "general_help"
    assert _MemoryStateRepo.store[30]["slots"]["state_bucket"] == "read_only_state"

    third_response, third_context = asyncio.run(_route_turn(service, 30, "Wat is RSI in simpele taal?", {"page": "/market/BTC", "page_type": "Market", "symbol": "BTC"}))
    fourth_response, fourth_context = asyncio.run(_route_turn(service, 30, "Ik voel FOMO, wat moet ik doen?", {"page": "/dashboard", "page_type": "Dashboard", "symbol": "BTC"}))
    fifth_response, fifth_context = asyncio.run(_route_turn(service, 30, "Welke strategie bekijk ik nu?", {"page": "/strategy/257", "page_type": "Strategy", "symbol": "ETH", "strategy_id": 257}))

    assert third_response["intent"] == "education"
    assert fourth_response["intent"] == "behavioral_intelligence"
    assert fifth_response["intent"] == "context_explain"
    assert third_context.get("finn_draft") is None
    assert fourth_context.get("finn_draft") is None
    assert fifth_context.get("finn_draft") is None
    assert _MemoryStateRepo.store[30]["current_flow"] == "context_explain"
    assert _MemoryStateRepo.store[30]["slots"]["state_bucket"] == "explain_state"
    assert len(_MemoryStateRepo.store[30]["slots"]["intent_history"]) >= 4


def test_multi_turn_regression_pack_preserves_transactional_turns_without_hijacking_follow_up_explains(monkeypatch):
    _MemoryStateRepo.store = {}
    monkeypatch.setattr("backend.services.finn_plan_service.ConversationStateRepository", _MemoryStateRepo)
    service = FinnPlanService(db_session=object())

    first_response, first_context = asyncio.run(_route_turn(
        service,
        30,
        "Maak een wekelijkse BTC setup voor een breakout long",
        {"page": "/dashboard", "page_type": "Dashboard", "symbol": "BTC"},
    ))
    assert _MemoryStateRepo.store[30]["current_flow"] == "plan_creation"
    second_response, second_context = asyncio.run(_route_turn(
        service,
        30,
        "Leg mijn setup uit",
        {"page": "/setup/62", "page_type": "Setup", "symbol": "BTC", "setup_id": 62, "setup_name": "Breakout long test"},
    ))
    third_response, third_context = asyncio.run(_route_turn(
        service,
        30,
        "Welke score zie ik nu?",
        {"page": "/dashboard", "page_type": "Dashboard", "symbol": "BTC"},
    ))
    fourth_response, fourth_context = asyncio.run(_route_turn(
        service,
        30,
        "Wat kun je voor mij doen?",
        {"page": "/dashboard", "page_type": "Dashboard", "symbol": "BTC"},
    ))

    assert first_response["intent"] == "plan_creation"
    assert first_response["draft"]["asset"] == "BTC"
    assert second_response["intent"] == "context_explain"
    assert third_response["intent"] == "context_explain"
    assert fourth_response["intent"] == "general_help"
    assert second_context.get("finn_draft") is None
    assert third_context.get("finn_draft") is None
    assert fourth_context.get("finn_draft") is None
    assert _MemoryStateRepo.store[30]["current_flow"] == "general_help"
    assert _MemoryStateRepo.store[30]["slots"]["state_bucket"] == "read_only_state"


def test_bot_decision_ack_state_persists_and_hydrates_without_client_context(monkeypatch):
    saved = {}

    class Repo:
        def __init__(self, session):
            self.session = session

        async def get_state(self, user_id):
            return saved.get(user_id)

        async def save_state(self, user_id, current_flow, asset, slots):
            saved[user_id] = {
                "current_flow": current_flow,
                "asset": asset,
                "slots": slots,
            }

        async def clear_state(self, user_id):
            saved.pop(user_id, None)

    monkeypatch.setattr("backend.services.finn_plan_service.ConversationStateRepository", Repo)
    service = FinnPlanService(db_session=object())
    blocked = service._blocked_behavioral_memory_ack_response(
        "BTC",
        9,
        {"type": "decision_churn", "message": "memory friction"},
    )

    asyncio.run(service.persist_response_state(1, blocked))
    hydrated = asyncio.run(service.hydrate_context(1, {}))

    assert hydrated["current_flow"] == "bot_decision"
    assert hydrated["asset"] == "BTC"
    assert hydrated["bot_id"] == 9
    assert hydrated["pending_behavioral_memory_friction"]["type"] == "decision_churn"

    ready = {
        "intent": "bot_decision",
        "flow": "bot_decision",
        "can_confirm": True,
        "state": {"status": "ready_for_confirmation", "current_flow": "bot_decision"},
    }
    asyncio.run(service.persist_response_state(1, ready))

    assert saved == {}


def test_hydrate_context_clears_expired_transactional_state(monkeypatch):
    saved = {
        1: {
            "current_flow": "plan_creation",
            "asset": "BTC",
            "updated_at": _utc_now(),
            "slots": {
                "draft": {"plan_type": "trade", "asset": "BTC"},
                "updated_at": (_utc_now() - timedelta(minutes=90)).isoformat(),
            },
        }
    }

    class Repo:
        def __init__(self, session):
            self.session = session

        async def get_state(self, user_id):
            return saved.get(user_id)

        async def save_state(self, user_id, current_flow, asset, slots):
            saved[user_id] = {
                "current_flow": current_flow,
                "asset": asset,
                "slots": slots,
            }

        async def clear_state(self, user_id):
            saved.pop(user_id, None)

    monkeypatch.setattr("backend.services.finn_plan_service.ConversationStateRepository", Repo)
    service = FinnPlanService(db_session=object())

    hydrated = asyncio.run(service.hydrate_context(1, {"symbol": "BTC"}))

    assert "finn_draft" not in hydrated
    assert saved == {}


def test_hydrate_context_clears_conflicting_transactional_state(monkeypatch):
    saved = {
        1: {
            "current_flow": "strategy_creation",
            "asset": "ETH",
            "updated_at": _utc_now(),
            "slots": {
                "draft": {"draft_kind": "strategy", "asset": "ETH", "strategy_id": 257},
                "updated_at": _utc_now().isoformat(),
            },
        }
    }

    class Repo:
        def __init__(self, session):
            self.session = session

        async def get_state(self, user_id):
            return saved.get(user_id)

        async def save_state(self, user_id, current_flow, asset, slots):
            saved[user_id] = {
                "current_flow": current_flow,
                "asset": asset,
                "slots": slots,
            }

        async def clear_state(self, user_id):
            saved.pop(user_id, None)

    monkeypatch.setattr("backend.services.finn_plan_service.ConversationStateRepository", Repo)
    service = FinnPlanService(db_session=object())

    hydrated = asyncio.run(service.hydrate_context(1, {"symbol": "BTC"}))

    assert "finn_draft" not in hydrated
    assert saved == {}


def test_persist_response_state_clears_transactional_state_after_non_transactional_turn(monkeypatch):
    saved = {
        1: {
            "current_flow": "bot_creation",
            "asset": "BTC",
            "updated_at": _utc_now(),
            "slots": {
                "draft": {"draft_kind": "bot", "asset": "BTC", "strategy_id": 257},
                "updated_at": _utc_now().isoformat(),
            },
        }
    }

    class Repo:
        def __init__(self, session):
            self.session = session

        async def get_state(self, user_id):
            return saved.get(user_id)

        async def save_state(self, user_id, current_flow, asset, slots):
            saved[user_id] = {
                "current_flow": current_flow,
                "asset": asset,
                "slots": slots,
            }

        async def clear_state(self, user_id):
            saved.pop(user_id, None)

    monkeypatch.setattr("backend.services.finn_plan_service.ConversationStateRepository", Repo)
    service = FinnPlanService(db_session=object())

    asyncio.run(service.persist_response_state(1, {
        "intent": "context_explain",
        "flow": "context_explain",
        "response": "Je bekijkt strategie 257.",
        "state": {"current_flow": "context_explain", "strategy_id": 257},
    }))

    assert saved[1]["current_flow"] == "context_explain"
    assert saved[1]["slots"]["state_bucket"] == "explain_state"
    assert saved[1]["slots"]["intent_history"][-1]["intent"] == "context_explain"


def test_live_preflight_rechecks_freshness_when_action_was_already_executed(monkeypatch):
    class Repo:
        async def get_bot_config(self, user_id, bot_id):
            return {"id": bot_id, "is_live": True}

    class FakeBotService:
        def __init__(self, session):
            self.repository = Repo()

        async def require_fresh_live_decision_context(self, user_id, bot_id):
            raise HTTPException(409, {
                "code": "LIVE_EXECUTION_STALE_DATA",
                "freshness": {
                    "fresh": False,
                    "status": "stale",
                    "age_minutes": 92,
                    "decision_id": 38677,
                },
            })

    class FakeExchangeRepository:
        def __init__(self, session):
            pass

        async def get_active_keys(self, user_id):
            return {"id": 1}

    monkeypatch.setattr("backend.services.finn_plan_service.BotService", FakeBotService)
    monkeypatch.setattr("backend.services.finn_plan_service.ExchangeRepository", FakeExchangeRepository)

    service = FinnPlanService(db_session=object())
    service._try_create_pending_action = AsyncMock(return_value=False)
    service._wait_for_action_result = AsyncMock(return_value={
        "ok": True,
        "verified": {"fresh_decision_context": True},
        "freshness": {"status": "fresh", "age_minutes": 39},
    })
    service._upsert_action_audit = AsyncMock()

    result = asyncio.run(service._execute_live_preflight_bot_decision_action(
        30,
        {
            "id": "live-preflight-38677",
            "type": "live_preflight_bot_decision",
            "payload": {"bot_id": 17, "decision_id": 38677},
        },
    ))

    assert result["verified"]["live_preflight"] is False
    assert result["verified"]["fresh_decision_context"] is False
    assert result["freshness"]["status"] == "stale"
    assert result["stale_data_block"]["code"] == "LIVE_EXECUTION_STALE_DATA"
    service._wait_for_action_result.assert_not_awaited()


def test_mission_resolve_actions_include_operator_lanes_and_summaries():
    service = _service()

    actions = service._mission_resolve_actions(
        "blocked_plan:BTC:12",
        asset="BTC",
        reason="market blokkeert",
        source_ids={"setup_id": 12},
        include_waiting_for_data=True,
    )

    assert actions[0]["resolution"] == "waiting_for_data"
    assert actions[0]["lane"] == "data"
    assert any(action["lane"] == "monitor" for action in actions)
    assert any(action["lane"] == "later" for action in actions)
    assert all(action.get("summary") for action in actions)


def test_snooze_action_carries_follow_through_metadata():
    service = _service()

    action = service._mission_snooze_action("blocked_plan:BTC:12", asset="BTC")

    assert action["resolution"] == "snoozed"
    assert action["lane"] == "later"
    assert "tijdelijk" in action["summary"].lower()


def test_finn_report_request_is_separate_from_trading_report():
    service = _service()

    assert service.looks_like_finn_report_request("Geef mijn Finn rapport van vandaag")
    assert service.looks_like_finn_report_request("Wat heeft Finn vandaag geblokkeerd?")
    assert service.looks_like_finn_report_request("Wat heb ik vandaag met Finn gedaan?")
    assert service.looks_like_finn_report_request("Waar week ik af vandaag?")
    assert service.looks_like_finn_report_request("Waar week ik af met Finn?")
    assert not service.looks_like_finn_report_request("Geef mijn daily trading report")


def test_finn_reflection_report_summarizes_operator_activity():
    service = _service()
    now = _utc_now().isoformat()
    activity = [
        {
            "type": "create_plan",
            "status": "executed",
            "resolve_state": "resolved",
            "asset": "BTC",
            "created_at": now,
        },
        {
            "type": "generate_bot_decision",
            "status": "executed",
            "resolve_state": "resolved",
            "asset": "BTC",
            "created_at": now,
            "behavioral_event": {"type": "decision_churn", "severity": "medium"},
        },
        {
            "type": "snooze_mission_item",
            "status": "executed",
            "resolve_state": "snoozed",
            "asset": "BTC",
            "created_at": now,
        },
    ]
    behavioral = service._build_behavioral_insight_from_activity(activity)

    report = service._build_finn_reflection_report(activity, behavioral, "Geef mijn Finn rapport van vandaag")
    message = service._finn_reflection_report_message(report)

    assert report["report_type"] == "finn_reflection_report"
    assert report["separate_from"] == "daily_trading_report"
    assert report["source"]["primary"] == "ai_pending_actions"
    assert report["source"]["stores_new_report"] is False
    assert report["metrics"]["actions"] == 3
    assert report["metrics"]["decision_churn_events"] == 1
    assert report["metrics"]["snoozed"] == 1
    assert report["risk_officer_interventions"][0]["type"] == "decision_churn"
    assert report["sections"]["activity_journal"]["entries"]
    assert report["sections"]["blocked_summary"]["entries"]
    assert report["sections"]["plan_adherence"]["status"] == "attention"
    assert any(verdict["agent"] == "risk_agent" for verdict in report["agent_verdicts"])
    assert report["agent_controller"]["dominant_agent"]
    assert "los van je dagelijkse trading report" in message
    assert "Agent-verdicts:" in message
    assert "Wat heb ik gedaan?" in message
    assert "Wat heeft Finn geblokkeerd?" in message
    assert "Waar week ik af?" in message


def test_finn_day_close_report_summarizes_closeout_and_tomorrow_focus():
    service = _service()
    now = _utc_now().isoformat()
    activity = [
        {
            "type": "create_plan",
            "label": "Setup-flow uitgevoerd",
            "status": "executed",
            "resolve_state": "resolved",
            "asset": "BTC",
            "created_at": now,
        },
        {
            "type": "live_manual_order_blocked",
            "label": "Live order geblokkeerd",
            "status": "executed",
            "resolve_state": "resolved",
            "asset": "ETH",
            "created_at": now,
            "outcome": "Marktprijs voor ETH is te oud; live order wordt geblokkeerd.",
            "behavioral_event": {"type": "execution_pressure", "severity": "high"},
        },
        {
            "type": "generate_bot_decision",
            "label": "Bot-decision gemaakt",
            "status": "pending",
            "resolve_state": "needs_user_confirmation",
            "asset": "ETH",
            "created_at": now,
        },
        {
            "type": "resolve_mission_item",
            "label": "Mission Control item bijgewerkt",
            "status": "executed",
            "resolve_state": "monitor_today",
            "asset": "BTC",
            "created_at": now,
        },
    ]
    behavioral = service._build_behavioral_insight_from_activity(activity)

    report = service._build_finn_reflection_report(activity, behavioral, "Sluit mijn dag af")
    message = service._finn_reflection_report_message(report)

    assert report["report_mode"] == "day_close"
    assert report["period"]["key"] == "day_close"
    assert report["status"] == "day_close_attention"
    assert report["metrics"]["actions_today"] == 4
    assert report["metrics"]["live_order_blocks_today"] == 1
    assert report["day_close"]["status"] == "review_before_tomorrow"
    assert report["day_close"]["carryover_count"] == 1
    assert report["day_close"]["what_i_did_today"]["entries"]
    assert report["day_close"]["what_finn_blocked"]["entries"]
    assert report["day_close"]["where_i_deviated"]["status"] == "attention"
    assert any(verdict["agent"] == "execution_agent" for verdict in report["agent_verdicts"])
    assert any("live orders geblokkeerd" in item.lower() for item in report["day_close"]["tomorrow_focus"])
    assert "Dagafsluiting:" in message
    assert "Wat heb ik vandaag gedaan?" in message
    assert "Wat heeft Finn geblokkeerd?" in message
    assert "Waar week ik af?" in message
    assert "Meenemen naar morgen:" in message
    assert "los van je dagelijkse trading report" in message


def test_finn_day_close_carries_agent_rhythm_into_tomorrow_focus():
    service = _service()
    now = _utc_now().isoformat()
    activity = [
        {
            "type": "agent_controller_handoff",
            "label": "Volg Risk Agent",
            "status": "executed",
            "resolve_state": "resolved",
            "asset": "BTC",
            "created_at": now,
            "agent_accountability": {
                "dominant_agent": "risk_agent",
                "dominant_label": "Risk Agent",
                "primary_action_label": "Portfolio-risico bekijken",
            },
        },
        {
            "type": "agent_controller_handoff",
            "label": "Volg Execution Agent",
            "status": "executed",
            "resolve_state": "snoozed",
            "asset": "ETH",
            "created_at": now,
            "agent_accountability": {
                "dominant_agent": "execution_agent",
                "dominant_label": "Execution Agent",
                "primary_action_label": "Live preflight bekijken",
            },
        },
    ]
    behavioral = service._build_behavioral_insight_from_activity(activity)

    report = service._build_finn_reflection_report(activity, behavioral, "Sluit mijn dag af")
    message = service._finn_reflection_report_message(report)

    assert report["agent_rhythm"]["status"] == "ready"
    assert report["day_close"]["agent_rhythm"]["status"] == "ready"
    assert report["day_close"]["operating_rules"]["status"] == "ready"
    assert report["day_close"]["operating_rules"] == report["operating_rules"]
    assert any("agent-adviezen" in item for item in report["day_close"]["tomorrow_focus"])
    assert "Agent-ritme voor morgen:" in message


def test_finn_report_response_exposes_top_level_state_contract(monkeypatch):
    async def activity(user_id, limit=200):
        return []

    async def governance_events(user_id, event_types=None, limit=80):
        return []

    service = _service()
    monkeypatch.setattr(service, "_get_recent_finn_activity", activity)
    monkeypatch.setattr(service, "_fetch_recent_governance_events", governance_events)

    result = asyncio.run(service.build_finn_report_response(1, "Geef mijn Finn rapport van vandaag"))

    assert result["intent"] == "finn_report"
    assert result["state"]["report_type"] == "finn_reflection_report"
    assert result["state"]["report_family"] == "finn_reports"
    assert result["state"]["separate_from"] == "daily_trading_report"
    assert result["state"]["source"]["primary"] == "ai_pending_actions"
    assert result["state"]["source"] == result["state"]["analysis"]["source"]
    assert "priority_engine" in result["state"]
    assert "memory_v2" in result["state"]
    assert "portfolio_operating_system" in result["state"]
    assert result["analysis"]["governance_events_summary"]["decision_review_count"] == 0


def test_mission_control_exposes_richer_behavioral_surface(monkeypatch):
    service = _service()

    async def daily_response(user_id, query, context=None):
        return {
            "state": {
                "analysis": {
                    "assets": [],
                    "follow_up_actions": [],
                    "asset_count": 0,
                    "date": _utc_now().date().isoformat(),
                }
            }
        }

    async def activity(user_id, limit=40):
        return [
            service._mission_activity_item({
                "id": f"finn-review-{idx}",
                "status": "executed",
                "created_at": _utc_now() - timedelta(hours=idx),
                "payload": {
                    "action": {"type": "skip_bot_decision" if idx % 2 == 0 else "snooze_mission_item"},
                    "result": {"ok": True, "status": "skipped" if idx % 2 == 0 else "snoozed"},
                },
            })
            for idx in range(3)
        ]

    async def resolved_ids(user_id):
        return []

    monkeypatch.setattr(service, "build_portfolio_daily_coach_response", daily_response)
    monkeypatch.setattr(service, "_get_recent_finn_activity", activity)
    monkeypatch.setattr(service, "_get_today_resolved_mission_item_ids", resolved_ids)

    result = asyncio.run(service.build_mission_control_response(1))

    assert result["intent"] == "mission_control"
    assert result["behavioral_profile"]["type"] == "review_anchored"
    assert "summary" in result["trend"]
    assert isinstance(result["risk_flags"], list)
    assert isinstance(result["habit_cards"], list)


def test_mission_control_backfills_behavioral_balance_score_from_memory(monkeypatch):
    service = _service()

    async def daily_response(user_id, query, context=None):
        return {
            "state": {
                "analysis": {
                    "assets": [],
                    "follow_up_actions": [],
                    "asset_count": 0,
                    "date": _utc_now().date().isoformat(),
                }
            }
        }

    thin_activity = [
        service._mission_activity_item({
            "id": "thin-review-1",
            "status": "executed",
            "created_at": _utc_now() - timedelta(hours=1),
            "payload": {
                "action": {"type": "skip_bot_decision"},
                "result": {"ok": True, "status": "skipped"},
            },
        })
    ]

    rich_activity = [
        service._mission_activity_item({
            "id": f"memory-review-{idx}",
            "status": "executed",
            "created_at": _utc_now() - timedelta(days=min(idx, 12), hours=idx),
            "payload": {
                "action": {"type": "skip_bot_decision" if idx % 2 == 0 else "snooze_mission_item"},
                "result": {"ok": True, "status": "skipped" if idx % 2 == 0 else "snoozed"},
            },
        })
        for idx in range(8)
    ]

    async def activity(user_id, limit=40):
        return thin_activity if limit <= 40 else rich_activity

    async def resolved_ids(user_id):
        return []

    monkeypatch.setattr(service, "build_portfolio_daily_coach_response", daily_response)
    monkeypatch.setattr(service, "_get_recent_finn_activity", activity)
    monkeypatch.setattr(service, "_get_today_resolved_mission_item_ids", resolved_ids)

    result = asyncio.run(service.build_mission_control_response(1))

    assert result["behavioral_balance_score"] is not None


def test_one_shot_weekly_dca_is_confirmable_and_creates_bot_by_default():
    result = _service().build_response("Maak een wekelijkse BTC DCA van 100 euro")

    assert result["can_confirm"] is True
    assert result["missing_fields"] == []
    assert result["invalid_fields"] == []
    assert result["draft"]["plan_type"] == "dca"
    assert result["draft"]["asset"] == "BTC"
    assert result["draft"]["dca"]["frequency"] == "weekly"
    assert result["draft"]["dca"]["day"] == "monday"
    assert result["draft"]["strategy"]["base_amount_eur"] == 100
    assert result["draft"]["bot"]["create_bot"] is True
    assert result["actions"][0]["type"] == "create_plan"


def test_dca_follow_up_merges_missing_amount_into_existing_draft():
    service = _service()
    first = service.build_response("Maak een wekelijkse ETH DCA")

    assert first["can_confirm"] is False
    assert first["next_question"] == "strategy.base_amount_eur"

    second = service.build_response(
        "Doe maar 75 euro",
        {"finn_draft": first["draft"]},
    )

    assert second["can_confirm"] is True
    assert second["draft"]["asset"] == "ETH"
    assert second["draft"]["strategy"]["base_amount_eur"] == 75
    assert second["actions"][0]["payload"]["bot"]["create_bot"] is True


def test_trade_plan_with_entry_stop_and_targets_is_confirmable():
    result = _service().build_response(
        "Maak een SOL trade 4H met 100 euro entry 160 stop loss 145 targets 180, 200"
    )

    assert result["can_confirm"] is True
    assert result["draft"]["plan_type"] == "trade"
    assert result["draft"]["asset"] == "SOL"
    assert result["draft"]["setup"]["timeframe"] == "4H"
    assert result["draft"]["strategy"]["entry_type"] == "limit"
    assert result["draft"]["strategy"]["entry"] == 160
    assert result["draft"]["strategy"]["stop_loss"] == 145
    assert result["draft"]["strategy"]["targets"] == [180, 200]
    assert result["draft"]["bot"]["automation"] == "bot_assisted"


def test_trade_plan_understands_natural_breakout_language():
    result = _service().build_response(
        "Ik wil SOL kopen bij breakout boven 180 op 4H met stop 160 targets 210 en 240 voor 100 euro"
    )

    assert result["can_confirm"] is True
    assert result["draft"]["plan_type"] == "trade"
    assert result["draft"]["asset"] == "SOL"
    assert result["draft"]["setup"]["timeframe"] == "4H"
    assert result["draft"]["strategy"]["entry_type"] == "breakout"
    assert result["draft"]["strategy"]["entry"] == 180
    assert result["draft"]["strategy"]["stop_loss"] == 160
    assert result["draft"]["strategy"]["targets"] == [210, 240]
    assert result["actions"][0]["type"] == "create_plan"


def test_trade_plan_supports_market_execution_mode():
    result = _service().build_response(
        "Maak een market order ETH trade op 4H met entry 3000 stop 2800 target 3600 voor 100 euro"
    )

    assert result["can_confirm"] is True
    assert result["draft"]["plan_type"] == "trade"
    assert result["draft"]["strategy"]["entry_type"] == "market"
    assert result["actions"][0]["payload"]["strategy"]["entry_type"] == "market"


def test_trade_plan_supports_manual_only_without_bot():
    result = _service().build_response(
        "Maak een handmatige BTC trade zonder bot op 4H met entry 100 stop 90 targets 130 voor 100 euro"
    )

    assert result["can_confirm"] is True
    assert result["draft"]["bot"]["create_bot"] is False
    assert result["draft"]["bot"]["automation"] == "manual_only"
    assert "Bot:" not in result["response"]
    assert "Automatisering: manual_only" in result["response"]


def test_trade_plan_supports_bot_assisted_modes():
    result = _service().build_response(
        "Maak een BTC trade met bot semi-auto op 4H met entry 100 stop 90 targets 130 voor 100 euro"
    )

    assert result["can_confirm"] is True
    assert result["draft"]["bot"]["create_bot"] is True
    assert result["draft"]["bot"]["automation"] == "bot_assisted"
    assert result["draft"]["bot"]["mode"] == "semi-auto"


def test_trade_follow_up_completes_ambiguous_buy_intent():
    service = _service()
    first = service.build_response("Koop agressief ETH")

    assert first["can_confirm"] is False
    assert first["next_question"] == "plan_type"

    second = service.build_response(
        "Maak er een trade van op 4H met entry 3000 stop 2800 target 3600 voor 100 euro",
        {"finn_draft": first["draft"]},
    )

    assert second["can_confirm"] is True
    assert second["draft"]["plan_type"] == "trade"
    assert second["draft"]["asset"] == "ETH"
    assert second["draft"]["bot"]["risk_profile"] == "aggressive"
    assert second["draft"]["strategy"]["entry"] == 3000
    assert second["draft"]["strategy"]["stop_loss"] == 2800
    assert second["draft"]["strategy"]["targets"] == [3600]


def test_trade_rejects_stop_above_entry_and_targets_below_entry():
    result = _service().build_response(
        "Maak een BTC trade 4H met 100 euro entry 100 stop 110 targets 90 en 120"
    )

    assert result["can_confirm"] is False
    assert {"field": "strategy.stop_loss", "reason": "voor long trades moet stop-loss lager zijn dan entry"} in result["invalid_fields"]
    assert {"field": "strategy.targets", "reason": "voor long trades moeten targets boven entry liggen"} in result["invalid_fields"]
    assert result["actions"] == []


def test_trade_rejects_non_ascending_targets():
    result = _service().build_response(
        "Maak een BTC trade 4H met 100 euro entry 100 stop 90 targets 130 en 120"
    )

    assert result["can_confirm"] is False
    assert {"field": "strategy.targets", "reason": "targets moeten oplopend zijn"} in result["invalid_fields"]
    assert result["actions"] == []


def test_trade_rejects_weak_risk_reward():
    result = _service().build_response(
        "Maak een BTC trade 4H met 100 euro entry 100 stop 90 target 105"
    )

    assert result["can_confirm"] is False
    assert {"field": "strategy.risk_reward", "reason": "risk/reward moet minimaal 1:1 zijn"} in result["invalid_fields"]
    assert result["actions"] == []


def test_trade_rejects_short_until_supported():
    result = _service().build_response(
        "Maak een short BTC trade 4H met 100 euro entry 100 stop 110 targets 80"
    )

    assert result["can_confirm"] is False
    assert result["draft"]["strategy"]["direction"] == "short"
    assert {"field": "strategy.direction", "reason": "short trades worden nog niet ondersteund; kies long of annuleer deze trade"} in result["invalid_fields"]
    assert result["actions"] == []


def test_trade_invalid_draft_can_be_corrected_in_follow_up():
    service = _service()
    first = service.build_response(
        "Maak een BTC trade 4H met 100 euro entry 100 stop 110 targets 90 en 120"
    )

    assert first["can_confirm"] is False

    corrected = service.build_response(
        "Stop 90 en targets 130 en 150",
        {"finn_draft": first["draft"]},
    )

    assert corrected["can_confirm"] is True
    assert corrected["invalid_fields"] == []
    assert corrected["draft"]["strategy"]["stop_loss"] == 90
    assert corrected["draft"]["strategy"]["targets"] == [130, 150]
    assert corrected["actions"][0]["type"] == "create_plan"


def test_cancel_request_returns_clear_state_envelope_for_trade_draft():
    service = _service()
    first = service.build_response("Koop ETH bij 3000 stop 2800 target 3600 met 100 euro op 4H")

    cancelled = service.build_response("annuleer", {"finn_draft": first["draft"]})

    assert service.is_cancel_request("annuleer") is True
    assert cancelled["intent"] == "plan_creation_cancelled"
    assert cancelled["flow"] is None
    assert cancelled["can_confirm"] is False
    assert cancelled["actions"] == []
    assert cancelled["draft"]["plan_type"] is None


def test_monthly_dca_day_above_28_is_invalid():
    result = _service().build_response("Maak een maandelijkse BTC DCA op dag 31 van 100 euro")

    assert result["can_confirm"] is False
    assert result["invalid_fields"] == [
        {"field": "dca.month_day", "reason": "gebruik dag 1 t/m 28 voor maandelijkse DCA"}
    ]
    assert result["actions"] == []


def test_coaching_question_does_not_start_plan_creation():
    assert _service().looks_like_plan_request("Waarom koopt mijn bot niet vandaag?") is False


def test_mixed_dca_and_trade_language_asks_for_plan_type():
    result = _service().build_response("Maak een BTC DCA trade met entry 100 van 50 euro")

    assert result["can_confirm"] is False
    assert result["next_question"] == "plan_type"
    assert result["actions"] == []


def test_aggressive_eth_buy_enters_clarifying_plan_flow():
    service = _service()

    assert service.looks_like_plan_request("Koop agressief ETH") is True

    result = service.build_response("Koop agressief ETH")

    assert result["intent"] == "plan_creation"
    assert result["can_confirm"] is False
    assert result["draft"]["asset"] == "ETH"
    assert result["draft"]["bot"]["risk_profile"] == "aggressive"
    assert result["next_question"] == "plan_type"
    assert "plan_type" in result["missing_fields"]
    assert result["actions"] == []


def test_multiple_or_unsupported_assets_ask_for_asset_clarification():
    service = _service()

    assert service.looks_like_plan_request("Misschien BTC of DOGE") is True

    result = service.build_response("Misschien BTC of DOGE")

    assert result["can_confirm"] is False
    assert result["next_question"] == "asset"
    assert "asset" in result["missing_fields"]
    assert result["invalid_fields"] == [
        {"field": "asset", "reason": "kies één ondersteund asset: BTC, ETH of SOL"}
    ]
    assert "BTC, ETH en SOL" in result["response"]
    assert result["actions"] == []


def test_macro_indicator_config_request_is_transactional_intent():
    service = _service()

    assert service.looks_like_indicator_config_request("Voeg Bitcoin Dominance toe aan macro als contrarian weight 2") is True
    assert service._extract_indicator_name_hint("Voeg Bitcoin Dominance toe aan macro", "macro") == "btc_dominance"
    assert service._extract_indicator_score_mode("gebruik contrarian want ik wil tegen de markt in kopen") == "contrarian"
    assert service._extract_indicator_weight("weight naar 2") == 2
    assert service._extract_indicator_weight("weight 1.5") == 1.5
    assert service._extract_indicator_weight("weging 1,5") == 1.5


def test_macro_indicator_config_blocks_custom_without_bucket_rules():
    service = _service()
    draft = empty_indicator_config_draft()
    draft["indicator"] = "btc_dominance"
    draft["display_name"] = "Bitcoin Dominance"
    draft["score_mode"] = "custom"
    draft["weight"] = 1.0

    validation = service._validate_indicator_config_draft(draft)

    assert validation["can_confirm"] is False
    assert validation["next_question"] == "rules"
    assert "rules" in validation["missing_fields"]


def test_macro_indicator_config_accepts_existing_standard_or_contrarian_draft():
    service = _service()
    draft = empty_indicator_config_draft()
    draft["indicator"] = "btc_dominance"
    draft["display_name"] = "Bitcoin Dominance"
    draft["score_mode"] = "contrarian"
    draft["weight"] = 2.0
    draft["rules"] = [{"score": score} for score in [10, 25, 50, 75, 100]]

    validation = service._validate_indicator_config_draft(draft)

    assert validation["can_confirm"] is True
    assert validation["missing_fields"] == []
    assert validation["invalid_fields"] == []


def test_macro_indicator_custom_bucket_rules_are_parsed_and_confirmable():
    service = _service()
    draft = empty_indicator_config_draft()
    draft["indicator"] = "btc_dominance"
    draft["display_name"] = "Bitcoin Dominance"
    draft["score_mode"] = "custom"
    draft["weight"] = 1.0
    draft["rules"] = [
        {"range_min": 0, "range_max": 20, "score": 50},
        {"range_min": 20, "range_max": 40, "score": 50},
        {"range_min": 40, "range_max": 60, "score": 50},
        {"range_min": 60, "range_max": 80, "score": 50},
        {"range_min": 80, "range_max": 100, "score": 50},
    ]

    parsed = service._extract_indicator_custom_bucket_rules(
        "custom 0-20=10 20-40=25 40-60=50 60-80=75 80-100=100",
        draft["rules"],
    )
    draft["rules"] = parsed["rules"]
    draft["custom_rules_touched"] = True
    draft["custom_rule_buckets"] = parsed["provided_buckets"]
    draft["custom_rules_complete"] = len(parsed["provided_buckets"]) == 5

    validation = service._validate_indicator_config_draft(draft)

    assert parsed["provided_buckets"] == ["0-20", "20-40", "40-60", "60-80", "80-100"]
    assert [rule["score"] for rule in draft["rules"]] == [10, 25, 50, 75, 100]
    assert validation["can_confirm"] is True


def test_macro_indicator_custom_bucket_rules_can_be_collected_across_turns():
    service = _service()
    draft = empty_indicator_config_draft()
    draft["indicator"] = "btc_dominance"
    draft["display_name"] = "Bitcoin Dominance"
    draft["score_mode"] = "custom"
    draft["weight"] = 1.0
    draft["rules"] = [
        {"range_min": 0, "range_max": 20, "score": 50},
        {"range_min": 20, "range_max": 40, "score": 50},
        {"range_min": 40, "range_max": 60, "score": 50},
        {"range_min": 60, "range_max": 80, "score": 50},
        {"range_min": 80, "range_max": 100, "score": 50},
    ]

    first = service._extract_indicator_custom_bucket_rules("custom 0-20=10 20-40=25", draft["rules"])
    draft["rules"] = first["rules"]
    draft["custom_rules_touched"] = True
    draft["custom_rule_buckets"] = first["provided_buckets"]
    draft["custom_rules_complete"] = len(draft["custom_rule_buckets"]) == 5

    first_validation = service._validate_indicator_config_draft(draft)
    assert first_validation["can_confirm"] is False
    assert first_validation["next_question"] == "rules"

    second = service._extract_indicator_custom_bucket_rules("40-60=50 60-80=75 80-100=100", draft["rules"])
    draft["rules"] = second["rules"]
    draft["custom_rule_buckets"] = sorted(set(draft["custom_rule_buckets"]) | set(second["provided_buckets"]))
    draft["custom_rules_complete"] = len(draft["custom_rule_buckets"]) == 5

    final_validation = service._validate_indicator_config_draft(draft)
    assert [rule["score"] for rule in draft["rules"]] == [10, 25, 50, 75, 100]
    assert final_validation["can_confirm"] is True


def test_indicator_bucket_followup_is_not_treated_as_indicator_name():
    service = _service()

    assert service._extract_indicator_name_hint("40-60=50 60-80=75 80-100=100", "macro") is None


def test_indicator_name_hint_ignores_connector_words():
    service = _service()

    assert service._extract_indicator_name_hint("Voeg dominance toe aan macro als contrarian weight 2", "macro") == "dominance"


def test_indicator_config_changes_include_node_activation():
    service = _service()
    draft = empty_indicator_config_draft()
    draft["score_mode"] = "standard"
    draft["weight"] = 1.0
    draft["activate_node"] = True
    draft["existing_config_snapshot"] = {
        "score_mode": "standard",
        "weight": 1.0,
        "node_active": False,
        "rules": [],
    }

    changes = service._indicator_config_changes_from_snapshot(draft)

    assert {"field": "node_active", "from": False, "to": True} in changes


def test_indicator_reset_draft_does_not_require_score_mode_or_weight():
    service = _service()
    draft = empty_indicator_config_draft()
    draft["operation"] = "reset"
    draft["indicator"] = "btc_dominance"
    draft["display_name"] = "Bitcoin Dominance"
    draft["score_mode"] = None
    draft["weight"] = None

    validation = service._validate_indicator_config_draft(draft)

    assert validation["can_confirm"] is True
    assert validation["missing_fields"] == []


def test_indicator_reset_changes_use_existing_snapshot():
    service = _service()
    draft = empty_indicator_config_draft()
    draft["operation"] = "reset"
    draft["existing_config_snapshot"] = {
        "score_mode": "custom",
        "weight": 2.0,
        "has_user_override": True,
        "rules": [],
    }

    changes = service._indicator_reset_changes_from_snapshot(draft)

    assert {"field": "score_rules", "from": "user_override", "to": "template_default"} in changes
    assert {"field": "score_mode", "from": "custom", "to": "template"} in changes
    assert {"field": "weight", "from": 2.0, "to": "template"} in changes


def test_technical_indicator_config_requires_symbol_when_activated():
    service = _service()
    assert service._extract_indicator_name_hint("Voeg RSI toe aan technical voor BTC met standaard scoring weight 1", "technical") == "rsi"

    draft = empty_indicator_config_draft()
    draft["category"] = "technical"
    draft["indicator"] = "rsi"
    draft["display_name"] = "RSI"
    draft["score_mode"] = "standard"
    draft["weight"] = 1.0
    draft["symbol"] = None

    validation = service._validate_indicator_config_draft(draft)

    assert validation["can_confirm"] is False
    assert "symbol" in validation["missing_fields"]


def test_strategy_creation_for_active_dca_setup_is_confirmable():
    service = _service()
    context = {
        "setup_id": 12,
        "setup_type": "dca",
        "setup_symbol": "BTC",
        "setup_timeframe": "1W",
    }

    result = service.build_strategy_response("Maak een strategie met 100 euro", context)

    assert result["intent"] == "strategy_creation"
    assert result["can_confirm"] is True
    assert result["draft"]["draft_kind"] == "strategy"
    assert result["draft"]["setup_id"] == 12
    assert result["draft"]["setup_type"] == "dca"
    assert result["draft"]["asset"] == "BTC"
    assert result["draft"]["strategy"]["base_amount_eur"] == 100
    assert result["actions"][0]["type"] == "create_strategy"


def test_strategy_creation_for_trade_setup_requires_missing_timeframe_then_recovers():
    service = _service()
    context = {
        "setup_id": 55,
        "setup_type": "trade",
        "setup_symbol": "ETH",
    }

    first = service.build_strategy_response(
        "Maak een strategie entry 3000 stop 2800 target 3600 met 100 euro",
        context,
    )

    assert first["can_confirm"] is False
    assert first["next_question"] == "timeframe"

    second = service.build_strategy_response("4H", {"finn_draft": first["draft"]})

    assert second["can_confirm"] is True
    assert second["draft"]["timeframe"] == "4H"
    assert second["draft"]["strategy"]["entry"] == 3000
    assert second["actions"][0]["type"] == "create_strategy"


def test_strategy_creation_trade_invalid_values_can_be_corrected():
    service = _service()
    context = {
        "setup_id": 55,
        "setup_type": "trade",
        "setup_symbol": "ETH",
        "setup_timeframe": "4H",
    }
    first = service.build_strategy_response(
        "Maak een strategie met entry 3000 stop 3200 target 2800 en 100 euro",
        context,
    )

    assert first["can_confirm"] is False
    assert {"field": "strategy.stop_loss", "reason": "voor long trades moet stop-loss lager zijn dan entry"} in first["invalid_fields"]

    second = service.build_strategy_response("stop 2800 en target 3600", {"finn_draft": first["draft"]})

    assert second["can_confirm"] is True
    assert second["invalid_fields"] == []
    assert second["draft"]["strategy"]["stop_loss"] == 2800
    assert second["draft"]["strategy"]["targets"] == [3600]


def test_strategy_creation_cancel_returns_clear_state_envelope():
    service = _service()
    first = service.build_strategy_response(
        "Maak een strategie met 50 euro",
        {"setup_id": 12, "setup_type": "dca", "setup_symbol": "BTC", "setup_timeframe": "1W"},
    )

    cancelled = service.build_strategy_response("annuleer", {"finn_draft": first["draft"]})

    assert cancelled["intent"] == "strategy_creation_cancelled"
    assert cancelled["flow"] is None
    assert cancelled["actions"] == []
    assert cancelled["draft"]["draft_kind"] == "strategy"


def test_strategy_cancel_response_can_be_built_from_context_draft():
    service = _service()
    first = service.build_strategy_response(
        "Maak een strategie met 50 euro",
        {"setup_id": 12, "setup_type": "dca", "setup_symbol": "BTC", "setup_timeframe": "1W"},
    )

    cancelled = asyncio.run(service.build_cancel_response(1, {"finn_draft": first["draft"]}))

    assert cancelled["intent"] == "strategy_creation_cancelled"
    assert cancelled["flow"] is None
    assert cancelled["draft"] is None
    assert cancelled["actions"] == []


def test_cancel_response_returns_none_without_transactional_state():
    cancelled = asyncio.run(_service().build_cancel_response(1, {}))

    assert cancelled is None


def test_strategy_update_intent_requires_strategy_id_when_no_existing_context():
    result = _service().build_strategy_response(
        "Pas de strategie aan met 150 euro",
        {"setup_id": 12, "setup_type": "dca", "setup_symbol": "BTC", "setup_timeframe": "1W"},
    )

    assert result["draft"]["operation"] == "update"
    assert result["can_confirm"] is False
    assert result["next_question"] == "strategy_id"
    assert "strategy_id" in result["missing_fields"]
    assert result["actions"] == []


def test_strategy_update_context_is_confirmable():
    result = _service().build_strategy_response(
        "Pas strategie 91 aan naar 150 euro",
        {
            "setup_id": 12,
            "setup_type": "dca",
            "setup_symbol": "BTC",
            "setup_timeframe": "1W",
        },
    )

    assert result["can_confirm"] is True
    assert result["draft"]["operation"] == "update"
    assert result["draft"]["strategy_id"] == 91
    assert result["draft"]["strategy"]["base_amount_eur"] == 150
    assert result["actions"][0]["label"] == "Strategie bijwerken"


def test_strategy_update_intent_detector_accepts_wijzig_with_strategy_id():
    service = _service()

    assert service.looks_like_strategy_request("Wijzig strategie 228 naar 150 euro", {}) is True
    assert service.looks_like_strategy_request("Pas strategie 228 aan naar 150 euro", {}) is True


def test_legacy_action_engine_uses_naive_utc_timestamps_for_existing_db_schema():
    ts = _utc_db_timestamp()

    assert ts.tzinfo is None


def test_strategy_create_intent_after_duplicate_warning_does_not_become_update():
    service = _service()
    duplicate_draft = service.build_strategy_response(
        "Maak een strategie met 100 euro",
        {
            "finn_draft": {
                "draft_kind": "strategy",
                "operation": "create",
                "setup_id": 12,
                "existing_strategy_id": 91,
                "setup_type": "dca",
                "asset": "BTC",
                "timeframe": "1W",
            }
        },
    )["draft"]

    result = service.build_strategy_response("Maak een tweede strategie met 101 euro", {"finn_draft": duplicate_draft})

    assert result["draft"]["operation"] == "create"
    assert result["draft"]["strategy_id"] is None
    assert result["draft"]["existing_strategy_id"] == 91
    assert result["draft"]["strategy"]["base_amount_eur"] == 101


def test_strategy_update_intent_reuses_duplicate_reference_id():
    result = _service().build_strategy_response(
        "Pas de strategie aan naar 150 euro",
        {
            "finn_draft": {
                "draft_kind": "strategy",
                "operation": "create",
                "setup_id": 12,
                "existing_strategy_id": 91,
                "setup_type": "dca",
                "asset": "BTC",
                "timeframe": "1W",
            }
        },
    )

    assert result["draft"]["operation"] == "update"
    assert result["draft"]["strategy_id"] == 91
    assert result["draft"]["strategy"]["base_amount_eur"] == 150


def test_strategy_setup_options_are_rendered_in_missing_setup_question():
    service = _service()
    message = service._build_strategy_message(
        service.build_strategy_response("Maak een strategie met 100 euro")["draft"],
        {
            "missing_fields": ["setup_id"],
            "invalid_fields": [],
            "next_question": "setup_id",
            "can_confirm": False,
        },
        setup_options=[
            {"id": 10, "name": "BTC DCA", "symbol": "BTC", "setup_type": "dca", "timeframe": "1W"},
            {"id": 11, "name": "ETH Trade", "symbol": "ETH", "setup_type": "trade", "timeframe": "4H"},
        ],
    )

    assert "setup 10" in message
    assert "BTC DCA" in message
    assert "setup 11" in message


def test_strategy_update_changes_are_summarized():
    service = _service()
    draft = service.build_strategy_response(
        "Pas strategie 91 aan naar 150 euro",
        {"setup_id": 12, "setup_type": "dca", "setup_symbol": "BTC", "setup_timeframe": "1W"},
    )["draft"]
    existing = {
        "id": 91,
        "setup_id": 12,
        "setup_type": "dca",
        "symbol": "BTC",
        "timeframe": "1W",
        "base_amount": 100,
        "execution_mode": "fixed",
        "automation": "manual_only",
        "risk_profile": "balanced",
    }

    changes = service._strategy_changes(existing, draft)

    assert {"field": "base_amount_eur", "from": 100, "to": 150} in changes


def test_strategy_update_changes_use_real_existing_values_without_default_noise():
    service = _service()
    draft = service.build_strategy_response(
        "Pas strategie 91 aan naar 150 euro",
        {"setup_id": 12, "setup_type": "dca", "setup_symbol": "BTC", "setup_timeframe": "1W"},
    )["draft"]
    draft["strategy"]["automation"] = "manual_only"
    existing = {
        "id": 91,
        "setup_id": 12,
        "setup_type": "dca",
        "symbol": "BTC",
        "timeframe": "1W",
        "base_amount": 100,
        "execution_mode": "fixed",
        "automation": "",
        "risk_profile": "",
    }

    changes = service._strategy_changes(existing, draft)

    assert changes == [{"field": "base_amount_eur", "from": 100, "to": 150}]


def test_strategy_update_changes_fall_back_to_existing_data_json():
    service = _service()
    draft = service.build_strategy_response(
        "Pas strategie 91 aan naar 150 euro",
        {"setup_id": 12, "setup_type": "dca", "setup_symbol": "BTC", "setup_timeframe": "1W"},
    )["draft"]
    existing = {
        "id": 91,
        "setup_id": 12,
        "setup_type": "dca",
        "symbol": "BTC",
        "timeframe": "1W",
        "base_amount": None,
        "execution_mode": "fixed",
        "data": '{"base_amount": 100, "automation": "manual_only"}',
    }

    changes = service._strategy_changes(existing, draft)

    assert changes == [{"field": "base_amount_eur", "from": 100, "to": 150}]


def test_strategy_formatter_reads_base_amount_from_data_when_column_is_empty():
    formatted = StrategyService(db_session=None)._format_strategy_row({
        "id": 91,
        "setup_id": 12,
        "setup_type": "dca",
        "execution_mode": "fixed",
        "base_amount": None,
        "data": {"base_amount": 100, "symbol": "BTC", "timeframe": "1W"},
    })

    assert formatted["base_amount"] == 100


def test_strategy_formatter_keeps_decimal_database_values_for_diff():
    formatted = StrategyService(db_session=None)._format_strategy_row({
        "id": 114,
        "setup_id": 89,
        "setup_type": "dca",
        "execution_mode": "fixed",
        "base_amount": Decimal("100"),
        "data": {"base_amount": 100, "symbol": "BTC", "timeframe": "1W"},
    })

    assert formatted["base_amount"] == 100


def test_strategy_update_changes_skip_empty_target_noise():
    service = _service()
    draft = service.build_strategy_response(
        "Pas strategie 114 aan naar 150 euro",
        {"setup_id": 89, "setup_type": "dca", "setup_symbol": "BTC", "setup_timeframe": "1W"},
    )["draft"]
    existing = {
        "id": 114,
        "setup_id": 89,
        "setup_type": "dca",
        "symbol": "BTC",
        "timeframe": "1W",
        "base_amount": Decimal("100"),
        "execution_mode": "fixed",
        "targets": [],
    }

    changes = service._strategy_changes(existing, draft)

    assert changes == [{"field": "base_amount_eur", "from": Decimal("100"), "to": 150}]


def test_strategy_rejects_absurd_amount_and_price_levels():
    result = _service().build_strategy_response(
        "Maak een strategie entry 30000000 stop 2800 target 3600 met 2000000 euro",
        {"setup_id": 55, "setup_type": "trade", "setup_symbol": "ETH", "setup_timeframe": "4H"},
    )

    assert result["can_confirm"] is False
    assert {"field": "strategy.base_amount_eur", "reason": "bedrag is onrealistisch hoog; gebruik maximaal 1.000.000 euro"} in result["invalid_fields"]
    assert {"field": "strategy.entry", "reason": "prijs moet groter dan 0 en realistisch zijn"} in result["invalid_fields"]


def test_strategy_market_execution_requires_explicit_ack():
    service = _service()
    first = service.build_strategy_response(
        "Maak een market order strategie entry 3000 stop 2800 target 3600 met 100 euro",
        {"setup_id": 55, "setup_type": "trade", "setup_symbol": "ETH", "setup_timeframe": "4H"},
    )

    assert first["can_confirm"] is False
    assert first["next_question"] == "strategy.market_execution_ack"
    assert "strategy.market_execution_ack" in first["missing_fields"]

    second = service.build_strategy_response("market akkoord", {"finn_draft": first["draft"]})

    assert second["can_confirm"] is True
    assert second["draft"]["strategy"]["market_execution_ack"] is True


def test_read_after_write_marks_absent_bot_as_not_verified_but_valid():
    result = asyncio.run(_service()._verify_created_objects(
        user_id=1,
        setup_id=None,
        strategy_id=None,
        bot_id=None,
    ))

    assert result == {
        "setup": True,
        "strategy": True,
        "bot": False,
    }


def test_finn_bot_creation_with_strategy_reference_is_confirmable():
    result = _service().build_bot_response("Maak een paper bot voor strategie 114")

    assert result["intent"] == "bot_creation"
    assert result["can_confirm"] is True
    assert result["draft"]["draft_kind"] == "bot"
    assert result["draft"]["strategy_id"] == 114
    assert result["draft"]["bot"]["is_live"] is False
    assert result["draft"]["bot"]["mode"] == "manual"
    assert result["actions"][0]["type"] == "create_bot"


def test_finn_bot_creation_requires_budget_for_auto_mode():
    result = _service().build_bot_response("Maak een auto bot voor strategie 114")

    assert result["can_confirm"] is False
    assert "bot.budget_total_eur" in result["missing_fields"]
    assert "bot.budget_daily_limit_eur" in result["missing_fields"]
    assert result["actions"] == []


def test_finn_bot_follow_up_completes_auto_budget_limits():
    service = _service()
    first = service.build_bot_response("Maak een auto bot voor strategie 114")

    second = service.build_bot_response(
        "budget 1000 daglimiet 100 min order 10 max order 50",
        {"finn_draft": first["draft"]},
    )

    assert second["can_confirm"] is True
    assert second["draft"]["bot"]["budget_total_eur"] == 1000
    assert second["draft"]["bot"]["budget_daily_limit_eur"] == 100
    assert second["draft"]["bot"]["budget_min_order_eur"] == 10
    assert second["draft"]["bot"]["budget_max_order_eur"] == 50


def test_vague_btc_intent_asks_for_plan_type():
    service = _service()

    assert service.looks_like_plan_request("Ik wil iets met BTC doen") is True

    result = service.build_response("Ik wil iets met BTC doen")

    assert result["can_confirm"] is False
    assert result["draft"]["asset"] == "BTC"
    assert result["next_question"] == "plan_type"
    assert result["actions"] == []


def test_open_plan_state_restores_pre_plan_clarifying_drafts():
    service = _service()
    cases = [
        ("Koop agressief ETH", "plan_type", "ETH"),
        ("Misschien BTC of DOGE", "asset", None),
        ("Ik wil iets met BTC doen", "plan_type", "BTC"),
    ]

    async def hydrate_context(_user_id, _context):
        return {"finn_draft": current_draft}

    service.hydrate_context = hydrate_context

    for prompt, next_question, asset in cases:
        current_draft = service.build_response(prompt)["draft"]

        state = asyncio.run(service.get_open_plan_state(1))

        assert state["has_draft"] is True
        assert state["can_confirm"] is False
        assert state["next_question"] == next_question
        assert state["draft"]["asset"] == asset
        assert state["actions"] == []


def test_user_can_correct_asset_and_amount_in_follow_up():
    service = _service()
    first = service.build_response("Maak een wekelijkse BTC DCA van 100 euro")

    corrected = service.build_response("Nee toch ETH en 50 euro", {"finn_draft": first["draft"]})

    assert corrected["can_confirm"] is True
    assert corrected["draft"]["asset"] == "ETH"
    assert corrected["draft"]["strategy"]["base_amount_eur"] == 50


def test_user_can_disable_bot_explicitly():
    service = _service()

    assert service.looks_like_bot_request("Maak een wekelijkse BTC DCA van 100 euro zonder bot") is False

    result = service.build_response("Maak een wekelijkse BTC DCA van 100 euro zonder bot")

    assert result["can_confirm"] is True
    assert result["draft"]["bot"]["create_bot"] is False
    assert "Bot:" not in result["response"]


def test_bot_strategy_switch_resets_previous_bot_state():
    service = _service()
    first = service.build_bot_response("Maak een paper bot voor strategie 121")
    first["draft"]["existing_bot_id"] = 38
    first["draft"]["asset"] = "BTC"
    first["draft"]["setup_type"] = "dca"
    first["draft"]["timeframe"] = "1W"

    second = service.build_bot_response("Maak een auto bot voor strategie 122", {"finn_draft": first["draft"]})

    assert second["draft"]["strategy_id"] == 122
    assert second["draft"]["existing_bot_id"] is None
    assert second["draft"]["asset"] is None
    assert second["draft"]["setup_type"] is None
    assert second["draft"]["timeframe"] is None
    assert second["draft"]["bot"]["mode"] == "auto"
    assert second["draft"]["bot"]["name"] == "Finn Strategy 122 Auto Bot"


def test_bot_strategy_selection_only_asks_for_strategy_first():
    result = _service().build_bot_response("Maak een paper bot")

    assert result["can_confirm"] is False
    assert result["missing_fields"] == ["strategy_id"]
    assert result["next_question"] == "strategy_id"


def test_new_generic_bot_start_resets_open_bot_draft_to_strategy_selection():
    service = _service()
    first = service.build_bot_response("Maak een auto bot voor strategie 126")

    restarted = service.build_bot_response("Maak een paper bot", {"finn_draft": first["draft"]})

    assert restarted["can_confirm"] is False
    assert restarted["draft"]["strategy_id"] is None
    assert restarted["draft"]["existing_bot_id"] is None
    assert restarted["draft"]["bot"]["mode"] == "manual"
    assert restarted["draft"]["bot"]["is_live"] is False
    assert restarted["missing_fields"] == ["strategy_id"]
    assert restarted["next_question"] == "strategy_id"


def test_budget_follow_up_keeps_existing_open_bot_draft():
    service = _service()
    first = service.build_bot_response("Maak een auto bot voor strategie 126")

    completed = service.build_bot_response(
        "budget 1000 daglimiet 100 min order 10 max order 50",
        {"finn_draft": first["draft"]},
    )

    assert completed["draft"]["strategy_id"] == 126
    assert completed["draft"]["bot"]["mode"] == "auto"
    assert completed["draft"]["bot"]["budget_total_eur"] == 1000


def test_bot_update_intent_with_bot_id_builds_update_draft():
    result = _service().build_bot_response("Pas bot 38 aan naar auto budget 1000 daglimiet 100 min order 10 max order 50")

    assert result["draft"]["operation"] == "update"
    assert result["draft"]["bot_id"] == 38
    assert result["draft"]["bot"]["mode"] == "auto"
    assert result["draft"]["bot"]["budget_total_eur"] == 1000


def test_bot_budget_update_parses_total_budget_with_aan_naar():
    result = _service().build_bot_response("Pas bot 38 budget aan naar 1500 daglimiet 150 min order 15 max order 60")

    assert result["draft"]["operation"] == "update"
    assert result["draft"]["bot"]["budget_total_eur"] == 1500
    assert result["draft"]["bot"]["budget_daily_limit_eur"] == 150
    assert result["draft"]["bot"]["budget_min_order_eur"] == 15
    assert result["draft"]["bot"]["budget_max_order_eur"] == 60


def test_live_bot_requires_explicit_live_ack():
    result = _service().build_bot_response(
        "Maak een live auto bot voor strategie 114 budget 1000 daglimiet 100 min order 10 max order 50"
    )

    assert result["can_confirm"] is False
    assert "bot.live_trading_ack" in result["missing_fields"]

    acknowledged = _service().build_bot_response("live akkoord", {"finn_draft": result["draft"]})

    assert acknowledged["draft"]["bot"]["live_trading_ack"] is True


def test_status_request_is_detected_without_starting_plan_creation():
    service = _service()

    assert service.looks_like_status_request("Is mijn BTC setup actief?") is True
    assert service.looks_like_plan_request("Is mijn BTC setup actief?") is False


def test_draft_status_analysis_explains_score_ranges():
    service = _service()
    draft = service.build_response("Maak een wekelijkse BTC DCA van 100 euro")["draft"]

    analysis = service._evaluate_draft_against_scores(
        draft,
        {
            "macro_score": 50,
            "technical_score": 90,
            "market_score": 40,
        },
    )

    assert analysis["is_active"] is False
    assert analysis["checks"]["macro"]["pass"] is True
    assert analysis["checks"]["technical"]["pass"] is False
    assert analysis["checks"]["market"]["pass"] is True


def test_plan_response_includes_state_reasoning_and_guardrails():
    result = _service().build_response("Maak een wekelijkse BTC DCA van 100 euro")

    assert result["state"]["status"] == "ready_for_confirmation"
    assert result["state"]["autonomy_level"] == "confirm_required"
    assert result["reasoning"]["confidence_score"] == 0.9
    assert result["actions"][0]["guardrails"]["can_execute_without_user"] is False
    assert result["actions"][0]["risk_level"] == "low"


def test_live_bot_action_is_high_risk():
    result = _service().build_response("Maak een live BTC trade 4H met 100 euro entry 100 stop loss 90 targets 120")

    assert result["can_confirm"] is True
    assert result["actions"][0]["risk_level"] == "high"
    assert result["actions"][0]["guardrails"]["live_trading"] is True
    assert result["reasoning"]["risk_detected"] is True


def test_draft_status_analysis_keeps_top_contributors():
    service = _service()
    draft = service.build_response("Maak een wekelijkse BTC DCA van 100 euro")["draft"]

    analysis = service._evaluate_draft_against_scores(
        draft,
        {
            "macro_score": 50,
            "technical_score": 60,
            "market_score": 40,
            "macro_top_contributors": '["DXY", "Liquidity"]',
        },
    )

    assert analysis["is_active"] is True
    assert analysis["checks"]["macro"]["top_contributors"] == ["DXY", "Liquidity"]
    assert "macro: 50.0 is binnen range" in service._analysis_reasons(analysis)


def test_saved_setup_status_uses_setup_score_ranges_for_blockers():
    service = _service()

    analysis = service._evaluate_setup_row(
        {
            "id": 12,
            "name": "BTC Plan",
            "setup_type": "dca",
            "timeframe": "1W",
            "score": 55,
            "is_active": True,
            "min_macro_score": 30,
            "max_macro_score": 70,
            "min_technical_score": 40,
            "max_technical_score": 60,
            "min_market_score": 20,
            "max_market_score": 80,
        },
        {
            "macro_score": 50,
            "technical_score": 90,
            "market_score": 40,
        },
    )

    assert analysis["is_active"] is False
    assert analysis["match_percentage"] == 66.7
    assert analysis["blockers"][0]["category"] == "technical"
    assert analysis["blockers"][0]["score"] == 90.0
    assert analysis["setup"]["stored_is_active"] is True


def test_saved_setup_status_is_active_when_all_ranges_match():
    service = _service()

    analysis = service._evaluate_setup_row(
        {
            "id": 13,
            "name": "ETH Plan",
            "setup_type": "trade",
            "timeframe": "4H",
            "score": 72,
            "is_active": False,
            "min_macro_score": 30,
            "max_macro_score": 70,
            "min_technical_score": 40,
            "max_technical_score": 80,
            "min_market_score": 20,
            "max_market_score": 80,
        },
        {
            "macro_score": 50,
            "technical_score": 65,
            "market_score": 40,
        },
    )

    assert analysis["is_active"] is True
    assert analysis["blockers"] == []
    assert analysis["match_percentage"] == 100.0
    assert analysis["setup"]["stored_is_active"] is False


def test_status_message_lists_blocking_scores_for_saved_setup():
    service = _service()
    analysis = service._evaluate_setup_row(
        {
            "id": 12,
            "name": "BTC Plan",
            "setup_type": "dca",
            "timeframe": "1W",
            "score": 55,
            "is_active": False,
            "min_macro_score": 30,
            "max_macro_score": 70,
            "min_technical_score": 40,
            "max_technical_score": 60,
            "min_market_score": 20,
            "max_market_score": 80,
        },
        {
            "macro_score": 50,
            "technical_score": 90,
            "market_score": 40,
        },
    )

    message = service._status_message("BTC", analysis, source="saved_setup")

    assert "Blokkeert nu:" in message
    assert "technical: score 90.0 moet binnen [40.0, 60.0] vallen" in message
    assert "Gebruik dit als plan-check" in message


def test_plan_status_agent_verdicts_explain_blocking_layer():
    service = _service()
    analysis = service._evaluate_setup_row(
        {
            "id": 12,
            "name": "BTC Plan",
            "setup_type": "dca",
            "timeframe": "1W",
            "score": 55,
            "is_active": False,
            "min_macro_score": 30,
            "max_macro_score": 70,
            "min_technical_score": 40,
            "max_technical_score": 60,
            "min_market_score": 20,
            "max_market_score": 80,
        },
        {"macro_score": 50, "technical_score": 90, "market_score": 40},
    )
    analysis["agent_verdicts"] = service._build_plan_status_agent_verdicts("BTC", analysis, source="saved_setup")

    message = service._status_message("BTC", analysis, source="saved_setup")

    assert any(verdict["agent"] == "technical_agent" and verdict["status"] == "blocks_plan" for verdict in analysis["agent_verdicts"])
    assert any(verdict["agent"] == "risk_agent" and verdict["status"] == "blocked" for verdict in analysis["agent_verdicts"])
    assert "Agent-verdicts:" in message


def test_plan_status_execution_review_explains_blocker_and_next_steps():
    service = _service()
    analysis = {
        "has_scores": True,
        "is_active": False,
        "match_percentage": 67,
        "blockers": [{"category": "market", "score": 42, "range": "60-100"}],
        "setup": {"id": 14, "score": 73},
    }

    review = service._build_plan_status_execution_review("BTC", analysis, source="saved_setup")

    assert review["topic"] == "plan_status"
    assert review["status"] == "blocked"
    assert "market" in review["why_now"].lower()
    assert any(action["handoff"] == "indicator_insight" for action in review["actions"])
    assert any(item["label"] == "Match" for item in review["evidence"])
    assert "niet" in review["do_not_do"].lower()


def test_issue_response_actions_issues_nested_mission_control_actions():
    service = FinnPlanService(db_session=object(), trace_id="trdm-test")
    service._issue_pending_action = AsyncMock()

    response = {
        "summary": {"posture": "action_required"},
        "workqueue": [
            {
                "id": "blocked_plan:BTC:61",
                "resolve_action": {
                    "id": "finn-maint-resolve-blocked-plan",
                    "type": "resolve_mission_item",
                    "label": "Vandaag monitoren",
                    "payload": {
                        "source_item_id": "blocked_plan:BTC:61",
                        "resolution": "monitor_today",
                    },
                },
                "resolve_actions": [
                    {
                        "id": "finn-maint-resolve-blocked-plan-done",
                        "type": "resolve_mission_item",
                        "label": "Markeer klaar",
                        "payload": {
                            "source_item_id": "blocked_plan:BTC:61",
                            "resolution": "resolved",
                        },
                    },
                    {
                        "id": "finn-maint-snooze-blocked-plan",
                        "type": "snooze_mission_item",
                        "label": "Later opnieuw bekijken",
                        "payload": {
                            "source_item_id": "blocked_plan:BTC:61",
                            "resolution": "snoozed",
                        },
                    },
                ],
                "next_best_action": {
                    "type": "chat_prompt",
                    "label": "BTC risk stack uitleg",
                    "prompt": "Welke bots en plannen stapelen risico voor BTC?",
                },
            }
        ],
    }

    issued = asyncio.run(service.issue_response_actions(30, response))

    primary = issued["workqueue"][0]["resolve_action"]
    alternatives = issued["workqueue"][0]["resolve_actions"]

    assert primary["action_id"] == "finn-maint-resolve-blocked-plan-u30"
    assert alternatives[0]["action_id"] == "finn-maint-resolve-blocked-plan-done-u30"
    assert alternatives[1]["action_id"] == "finn-maint-snooze-blocked-plan-u30"
    assert "action_id" not in issued["workqueue"][0]["next_best_action"]
    assert service._issue_pending_action.await_count == 3


def test_issue_response_actions_skips_pending_write_for_refresh_daily_scores():
    service = FinnPlanService(db_session=object(), trace_id="trdm-test")
    service._issue_pending_action = AsyncMock()

    response = {
        "actions": [
            {
                "id": "finn-maint-refresh-daily-scores-btc",
                "type": "refresh_daily_scores",
                "label": "Daily scores verversen",
                "payload": {"assets": ["BTC"], "scope": "asset"},
            }
        ]
    }

    issued = asyncio.run(service.issue_response_actions(30, response))

    assert issued["actions"][0]["action_id"] == "finn-maint-refresh-daily-scores-btc-u30"
    service._issue_pending_action.assert_not_awaited()


def test_indicator_insight_request_is_detected_but_config_stays_separate():
    service = _service()

    assert service.looks_like_indicator_insight_request("Waarom is mijn macro score laag?") is True
    assert service.looks_like_indicator_insight_request("Welke technical indicators gebruikt BTC nu?") is True
    assert service.looks_like_indicator_insight_request("Voeg RSI toe aan technical voor BTC") is False
    assert service.looks_like_status_request("Welke score blokkeert mijn BTC setup?") is True
    assert service.looks_like_indicator_insight_request("Welke score blokkeert mijn BTC setup?") is False


def test_indicator_insight_analysis_uses_real_rows_weights_and_unused_options():
    service = _service()
    analysis = service._build_indicator_insight_analysis(
        asset="BTC",
        categories=["macro"],
        daily_scores={
            "macro_score": 35,
            "macro_interpretation": "Zwak",
            "macro_top_contributors": '["btc_dominance"]',
        },
        macro_rows=[
            {
                "name": "btc_dominance",
                "value": 58.2,
                "score": 25,
                "trend": "laag",
                "interpretation": "Dominance drukt macro.",
                "action": "Wacht op betere macro.",
                "timestamp": "2026-05-20T10:00:00",
            }
        ],
        technical_rows=[],
        market_rows=[],
        market_snapshot=None,
        available={
            "macro": [
                {"name": "btc_dominance", "display_name": "Bitcoin Dominance"},
                {"name": "fear_greed", "display_name": "Fear & Greed"},
            ],
            "technical": [],
            "market": [],
        },
        configs={
            "macro:btc_dominance": {
                "score_mode": "contrarian",
                "weight": 2.0,
                "rules_count": 5,
            }
        },
    )

    macro = analysis["categories"]["macro"]
    assert macro["score"] == 35.0
    assert macro["active_count"] == 1
    assert macro["weak_indicators"][0]["name"] == "btc_dominance"
    assert macro["heavy_weight_indicators"][0]["weight"] == 2.0
    assert macro["unused_options"][0]["name"] == "fear_greed"
    assert "Je macro-laag is dun" in " ".join(analysis["suggestions"])


def test_indicator_insight_message_is_advice_only_and_mentions_missing_data():
    service = _service()
    analysis = service._build_indicator_insight_analysis(
        asset="BTC",
        categories=["technical"],
        daily_scores=None,
        macro_rows=[],
        technical_rows=[],
        market_rows=[],
        market_snapshot=None,
        available={"macro": [], "technical": [{"name": "rsi", "display_name": "RSI"}], "market": []},
        configs={},
    )

    message = service._indicator_insight_message("BTC", analysis)

    assert "geen daily score van vandaag" in message
    assert "Geen actieve indicator-data" in message
    assert "Ik pas niets automatisch aan" in message


def test_indicator_execution_review_uses_indicator_analysis_contract():
    service = _service()
    analysis = service._build_indicator_insight_analysis(
        asset="BTC",
        categories=["technical"],
        daily_scores={"technical_score": 41},
        macro_rows=[],
        technical_rows=[],
        market_rows=[],
        market_snapshot=None,
        available={"macro": [], "technical": [{"name": "rsi", "display_name": "RSI"}], "market": []},
        configs={},
    )

    review = service._build_indicator_execution_review("BTC", analysis)

    assert review["topic"] == "indicator_insight"
    assert review["title"].startswith("Waarom bewegen je indicatoren")
    assert review["actions"][0]["handoff"] == "plan_status"
    assert review["evidence"][0]["value"] == "BTC"


def test_daily_coach_request_detection_is_separate_from_status_and_plan_creation():
    service = _service()

    assert service.looks_like_daily_coach_request("Wat moet ik vandaag doen met mijn BTC setup?") is True
    assert service.looks_like_daily_coach_request("Moet ik vandaag kopen?") is True
    assert service.looks_like_daily_coach_request("Geef mijn daily brief") is True
    assert service.looks_like_daily_coach_request("Wat zijn mijn prioriteiten vandaag?") is True
    assert service.looks_like_daily_coach_request("Start mijn dag") is True
    assert service.looks_like_plan_request("Wat moet ik vandaag doen met mijn BTC setup?") is False
    assert service.looks_like_plan_request("Geef mijn daily brief") is False
    assert service.looks_like_status_request("Welke score blokkeert mijn BTC setup?") is True
    assert service.looks_like_daily_coach_request("Welke score blokkeert mijn BTC setup?") is False
    assert service.looks_like_daily_score_refresh_request("Ververs daily scores voor BTC") is True
    assert service.looks_like_bot_decision_request("Maak bot-decision voor BTC") is True


def test_daily_coach_portfolio_scope_only_for_generic_briefing_prompts():
    service = _service()

    assert service._should_build_portfolio_daily_coach("Geef mijn daily brief", {"symbol": "BTC"}) is True
    assert service._should_build_portfolio_daily_coach("Wat zijn mijn prioriteiten vandaag?", {"symbol": "BTC"}) is True
    assert service._should_build_portfolio_daily_coach("Wat moet ik vandaag doen?", {"symbol": "BTC"}) is True
    assert service.looks_like_daily_coach_request("Waar zit mijn grootste portfolio risico?") is True
    assert service._should_build_portfolio_daily_coach("Waar zit mijn grootste portfolio risico?", {"symbol": "BTC"}) is True
    assert service.looks_like_daily_coach_request("Welke asset vraagt vandaag aandacht?") is True
    assert service.looks_like_daily_coach_request("Heb ik te veel exposure?") is True
    assert service.looks_like_daily_coach_request("Welke assets moet ik vandaag negeren?") is True
    assert service._should_build_portfolio_daily_coach("Welke assets moet ik vandaag negeren?", {"symbol": "BTC"}) is True
    assert service.looks_like_daily_coach_request("Welke live bots vragen vandaag review?") is True
    assert service._should_build_portfolio_daily_coach("Welke live bots vragen vandaag review?", {"symbol": "BTC"}) is True
    assert service.looks_like_daily_coach_request("Welke bots en plannen stapelen risico?") is True
    assert service._should_build_portfolio_daily_coach("Welke bots en plannen stapelen risico?", {}) is True
    assert service.looks_like_daily_coach_request("Welke setups conflicteren?") is True
    assert service._should_build_portfolio_daily_coach("Bots met overlappende budgetten", {}) is True
    assert service._portfolio_question_focus("Welke assets moet ik vandaag negeren?") == "ignore_today"
    assert service._portfolio_question_focus("Welke setups conflicteren?") == "setup_conflicts"
    assert service._portfolio_question_focus("Bots met overlappende budgetten") == "budget_overlap"
    assert service._portfolio_question_focus("DCA en trade") == "setup_conflicts"
    assert service._portfolio_question_focus("Heb ik te veel exposure?") == "exposure"
    assert service._should_build_portfolio_daily_coach("Wat moet ik vandaag doen met mijn BTC setup?", {}) is False
    assert service._should_build_portfolio_daily_coach("Geef mijn ETH daily brief", {"symbol": "BTC"}) is False


def test_portfolio_daily_coach_prioritizes_active_blocked_and_scoreless_assets():
    service = _service()
    active = {
        "asset": "ETH",
        "stance": "plan_is_active",
        "has_scores": True,
        "setup": {"id": 1, "name": "ETH DCA"},
        "blockers": [],
        "bot_today": {"decision_count": 1},
        "indicator_summary": {"warnings": []},
    }
    blocked = {
        "asset": "BTC",
        "stance": "wait_for_plan",
        "has_scores": True,
        "setup": {"id": 2, "name": "BTC Trade"},
        "blockers": [{"category": "macro", "score": 10, "range": [30, 70]}],
        "bot_today": {"decision_count": 0},
        "indicator_summary": {"warnings": ["macro-laag is dun"]},
    }
    scoreless = {
        "asset": "SOL",
        "stance": "wait_for_scores",
        "has_scores": False,
        "setup": {"id": 3, "name": "SOL DCA"},
        "blockers": [],
        "bot_today": {"decision_count": 0},
        "indicator_summary": {"warnings": []},
        "data_readiness": {
            "status": "onboarding_incomplete",
            "message": "De daily score ontbreekt omdat je onboarding nog niet volledig is voor: macro.",
            "onboarding_gaps": ["macro"],
            "config_gaps": ["macro"],
            "suggested_actions": ["Rond eerst deze onboarding-stap af: macro."],
        },
    }

    analysis = service._build_portfolio_daily_coach_analysis([blocked, scoreless, active])
    message = service._portfolio_daily_coach_message(analysis)

    assert analysis["scope"] == "portfolio"
    assert analysis["asset_count"] == 3
    assert analysis["top_priorities"][0]["asset"] == "ETH"
    assert len(analysis["blocked_assets"]) == 1
    assert len(analysis["scoreless_assets"]) == 1
    assert analysis["data_readiness"]["status"] == "onboarding_incomplete"
    assert analysis["portfolio_risk"]["status"] == "needs_data"
    assert analysis["portfolio_risk"]["top_asset"] == "BTC"
    assert any(verdict["agent"] == "macro_agent" for verdict in analysis["agent_verdicts"])
    assert any(verdict["agent"] == "risk_agent" and verdict["status"] == "needs_data" for verdict in analysis["agent_verdicts"])
    assert analysis["top_priorities"][2]["data_readiness"]["status"] == "onboarding_incomplete"
    assert "Portfolio daily brief" in message
    assert "ETH: nu doen" in message
    assert "BTC: niet forceren" in message
    assert "Datakwaliteit" in message
    assert "Portfolio-risico" in message
    assert "Agent-verdicts:" in message
    assert analysis["agent_controller"]["dominant_agent"] in {"macro_agent", "risk_agent"}
    assert analysis["agent_controller"]["primary_action"]["prompt"]
    assert analysis["agent_controller"]["primary_action"]["source"] == "agent_controller"
    assert "Finn Controller:" in message
    assert "advies-only" in message


def test_portfolio_risk_detects_concentration_and_bot_conflicts():
    service = _service()
    blocked_btc = {
        "asset": "BTC",
        "stance": "wait_for_plan",
        "has_scores": True,
        "setup": {"id": 2, "name": "BTC DCA"},
        "blockers": [{"category": "macro", "score": 10, "range": [30, 70]}],
        "bot_today": {"decision_count": 0},
        "indicator_summary": {"warnings": ["macro-laag is dun"]},
        "data_readiness": {"status": "ready", "config_gaps": []},
    }
    active_eth = {
        "asset": "ETH",
        "stance": "plan_is_active",
        "has_scores": True,
        "setup": {"id": 3, "name": "ETH DCA"},
        "blockers": [],
        "bot_today": {"decision_count": 0},
        "indicator_summary": {"warnings": []},
        "data_readiness": {"status": "ready", "config_gaps": []},
    }
    portfolio_context = {
        "global": {
            "total_equity": 1000,
            "current_position_value": 1000,
            "cash_balance": 0,
            "allocations_pct": {"BTC": 80.0, "ETH": 20.0},
        },
        "bots": [
            {"bot_id": 1, "symbol": "BTC", "position_value": 500, "budget_total": 1000, "is_active": True, "is_live": True},
            {"bot_id": 2, "symbol": "BTC", "position_value": 300, "budget_total": 500, "is_active": True, "is_live": False},
            {"bot_id": 3, "symbol": "ETH", "position_value": 200, "budget_total": 500, "is_active": True, "is_live": False},
        ],
    }

    analysis = service._build_portfolio_daily_coach_analysis([active_eth, blocked_btc], portfolio_context)
    risk = analysis["portfolio_risk"]

    assert risk["status"] == "high_attention"
    assert risk["top_asset"] == "BTC"
    btc = risk["asset_risk"][0]
    assert btc["asset"] == "BTC"
    assert btc["risk_level"] == "high"
    assert btc["allocation_pct"] == 80.0
    assert btc["bot_count"] == 2
    assert btc["live_bot_count"] == 1
    assert "blocked_setup" in btc["risk_flags"]
    assert "high_exposure" in btc["risk_flags"]
    assert "multiple_bots" in btc["risk_flags"]
    assert any(conflict["type"] == "blocked_setup_with_bot" for conflict in risk["conflicts"])
    assert risk["ranked_conflicts"][0]["asset"] == "BTC"
    assert risk["ranked_conflicts"][0]["live_bot_count"] == 1
    assert risk["live_bot_hotspots"][0]["asset"] == "BTC"
    assert risk["live_bot_hotspots"][0]["live_bot_count"] == 1
    assert any(verdict["agent"] == "execution_agent" for verdict in analysis["agent_verdicts"])
    assert any(verdict["agent"] == "risk_agent" and verdict["status"] == "high_attention" for verdict in analysis["agent_verdicts"])
    assert any(warning["asset"] == "BTC" for warning in risk["concentration_warnings"])
    assert risk["asset_priority"][0]["asset"] == "BTC"
    assert risk["asset_priority"][0]["priority"] == "eerst oplossen"
    assert risk["ignore_today_assets"][0]["asset"] == "BTC"
    assert risk["ignore_today_assets"][0]["reason"] == "setup blokkeert nog"
    assert risk["risk_stacks"][0]["asset"] == "BTC"
    assert "setup geblokkeerd" in risk["risk_stacks"][0]["factors"]
    assert "hoge exposure" in risk["risk_stacks"][0]["factors"]
    assert "meerdere bots" in risk["risk_stacks"][0]["factors"]
    message = service._portfolio_daily_coach_message(analysis)
    assert "Risk stack: BTC stapelt risico" in message
    assert "Risk Agent: high_attention" in message


def test_mission_control_adds_portfolio_risk_stack_to_workqueue():
    service = _service()
    daily_analysis = service._build_portfolio_daily_coach_analysis(
        [
            {
                "asset": "BTC",
                "stance": "wait_for_plan",
                "has_scores": True,
                "setup": {"id": 12, "name": "BTC DCA"},
                "setup_match_percentage": 33,
                "blockers": [{"category": "macro", "score": 10, "range": [30, 70]}],
                "active_strategy": {"active": False},
                "bot_today": {"decision_count": 0, "decisions": []},
                "indicator_summary": {"warnings": []},
                "data_readiness": {"status": "ready", "config_gaps": []},
                "follow_up_actions": [],
            }
        ],
        {
            "global": {
                "total_equity": 1000,
                "current_position_value": 800,
                "cash_balance": 200,
                "allocations_pct": {"Cash": 20.0, "BTC": 80.0},
            },
            "bots": [
                {"bot_id": 1, "symbol": "BTC", "position_value": 500, "budget_total": 1000, "is_active": True, "is_live": False},
                {"bot_id": 2, "symbol": "BTC", "position_value": 300, "budget_total": 500, "is_active": True, "is_live": False},
            ],
        },
    )

    mission = service._build_mission_control_from_daily_analysis(daily_analysis)
    stack_item = next(item for item in mission["workqueue"] if item["type"] == "portfolio_risk_stack")

    assert stack_item["asset"] == "BTC"
    assert stack_item["priority"] == "high"
    assert stack_item["resolve_state"] == "monitor_today"
    assert stack_item["risk_score"] >= 75
    assert "hoge exposure" in stack_item["risk_factors"]
    assert stack_item["next_best_action"]["prompt"] == "Welke bots en plannen stapelen risico voor BTC?"
    assert mission["workqueue_groups"][0]["key"] == "review"
    assert mission["summary"]["portfolio_ignore_today_count"] == 1
    assert mission["summary"]["portfolio_live_hotspot_count"] == 0


def test_portfolio_risk_detects_setup_conflicts_and_budget_overlap():
    service = _service()
    active_btc = {
        "asset": "BTC",
        "stance": "plan_is_active",
        "has_scores": True,
        "setup": {"id": 12, "name": "BTC DCA"},
        "blockers": [],
        "bot_today": {"decision_count": 0},
        "indicator_summary": {"warnings": []},
        "data_readiness": {"status": "ready", "config_gaps": []},
    }

    analysis = service._build_portfolio_daily_coach_analysis(
        [active_btc],
        {
            "global": {
                "total_equity": 1000,
                "current_position_value": 700,
                "cash_balance": 300,
                "allocations_pct": {"Cash": 30.0, "BTC": 70.0},
            },
            "bots": [
                {"bot_id": 1, "symbol": "BTC", "position_value": 350, "budget_total": 900, "is_active": True, "is_live": False},
                {"bot_id": 2, "symbol": "BTC", "position_value": 350, "budget_total": 800, "is_active": True, "is_live": False},
            ],
        },
        {
            "BTC": {
                "setup_count": 2,
                "setup_ids": [12, 13],
                "setup_names": ["BTC DCA", "BTC Breakout"],
                "setup_types": ["dca", "trade"],
                "timeframes": ["1W", "4H"],
                "mixed_setup_types": True,
            }
        },
    )
    risk = analysis["portfolio_risk"]
    btc = risk["asset_risk"][0]
    conflict_types = {conflict["type"] for conflict in risk["conflicts"]}

    assert risk["status"] == "high_attention"
    assert btc["asset"] == "BTC"
    assert "mixed_setup_types" in btc["risk_flags"]
    assert "multiple_setups" in btc["risk_flags"]
    assert "budget_overlap" in btc["risk_flags"]
    assert "multiple_setups_same_asset" in conflict_types
    assert "mixed_setup_types_same_asset" in conflict_types
    assert "bot_budget_overlap" in conflict_types
    assert "active_plan_high_exposure" in conflict_types
    assert risk["ignore_today_assets"][0]["asset"] == "BTC"
    assert risk["ignore_today_assets"][0]["reason"] in {
        "botbudgetten stapelen boven portfolio-equity",
        "DCA en trade-intentie lopen door elkaar",
    }
    assert "DCA en trade tegelijk" in risk["risk_stacks"][0]["factors"]
    assert "botbudget boven equity" in risk["risk_stacks"][0]["factors"]
    assert risk["ranked_conflicts"][0]["priority_rank"] >= risk["ranked_conflicts"][-1]["priority_rank"]


def test_portfolio_risk_detects_live_bot_and_strategy_conflicts():
    service = _service()
    blocked_btc = {
        "asset": "BTC",
        "stance": "wait_for_plan",
        "has_scores": True,
        "setup": {"id": 12, "name": "BTC DCA"},
        "blockers": [{"category": "macro", "score": 10, "range": [30, 70]}],
        "bot_today": {"decision_count": 1},
        "indicator_summary": {"warnings": []},
        "data_readiness": {"status": "ready", "config_gaps": []},
        "active_strategy": {"active": True, "strategy": {"id": 88, "name": "BTC Active Ladder"}},
    }

    analysis = service._build_portfolio_daily_coach_analysis(
        [blocked_btc],
        {
            "global": {
                "total_equity": 1000,
                "current_position_value": 800,
                "cash_balance": 200,
                "allocations_pct": {"Cash": 20.0, "BTC": 80.0},
            },
            "bots": [
                {"bot_id": 1, "symbol": "BTC", "position_value": 400, "budget_total": 500, "is_active": True, "is_live": True},
                {"bot_id": 2, "symbol": "BTC", "position_value": 400, "budget_total": 500, "is_active": True, "is_live": True},
            ],
        },
    )
    risk = analysis["portfolio_risk"]
    conflict_types = {conflict["type"] for conflict in risk["conflicts"]}
    prompts = {action["prompt"] for action in analysis["follow_up_actions"]}

    assert "multiple_live_bots" in risk["asset_risk"][0]["risk_flags"]
    assert "live_strategy_conflict" in risk["asset_risk"][0]["risk_flags"]
    assert "multiple_live_bots_same_asset" in conflict_types
    assert "live_strategy_conflict" in conflict_types
    assert risk["live_bot_hotspots"][0]["asset"] == "BTC"
    assert "meerdere live bots" in risk["live_bot_hotspots"][0]["summary"]
    assert risk["ignore_today_assets"][0]["reason"] == "meerdere live bots sturen op dezelfde asset"
    assert "Welke live bots vragen vandaag review voor BTC?" in prompts
    assert "Welke bots en plannen stapelen risico voor BTC?" in prompts

    mission = service._build_mission_control_from_daily_analysis(analysis)
    hotspot_item = next(item for item in mission["workqueue"] if item["type"] == "portfolio_live_hotspot")
    assert hotspot_item["asset"] == "BTC"
    assert hotspot_item["resolve_state"] == "monitor_today"
    assert mission["summary"]["portfolio_live_hotspot_count"] == 1


def test_portfolio_budget_overlap_is_flagged_when_equity_is_zero():
    service = _service()
    blocked_btc = {
        "asset": "BTC",
        "stance": "wait_for_plan",
        "has_scores": True,
        "setup": {"id": 12, "name": "BTC DCA"},
        "blockers": [{"category": "macro", "score": 10, "range": [30, 70]}],
        "bot_today": {"decision_count": 0},
        "indicator_summary": {"warnings": []},
        "data_readiness": {"status": "ready", "config_gaps": []},
    }

    analysis = service._build_portfolio_daily_coach_analysis(
        [blocked_btc],
        {
            "global": {
                "total_equity": 0,
                "current_position_value": 0,
                "cash_balance": 0,
                "allocations_pct": {"Cash": 100.0},
            },
            "bots": [
                {"bot_id": 1, "symbol": "BTC", "position_value": 0, "budget_total": 1200, "is_active": True, "is_live": False},
                {"bot_id": 2, "symbol": "BTC", "position_value": 0, "budget_total": 1500, "is_active": True, "is_live": False},
            ],
        },
    )
    risk = analysis["portfolio_risk"]
    btc = risk["asset_risk"][0]
    budget_conflict = next(conflict for conflict in risk["conflicts"] if conflict["type"] == "bot_budget_overlap")

    assert btc["budget_eur"] == 2700
    assert "budget_overlap" in btc["risk_flags"]
    assert budget_conflict["severity"] == "high"
    assert "onbekende of nul portfolio equity" in budget_conflict["reason"]


def test_portfolio_exposure_question_answers_cash_before_blocked_plan_risk():
    service = _service()
    blocked_btc = {
        "asset": "BTC",
        "stance": "wait_for_plan",
        "has_scores": True,
        "setup": {"id": 2, "name": "BTC DCA"},
        "blockers": [{"category": "macro", "score": 10, "range": [30, 70]}],
        "bot_today": {"decision_count": 0},
        "indicator_summary": {"warnings": []},
        "data_readiness": {"status": "ready", "config_gaps": []},
    }
    analysis = service._build_portfolio_daily_coach_analysis(
        [blocked_btc],
        {
            "global": {
                "total_equity": 1000,
                "current_position_value": 0,
                "cash_balance": 1000,
                "allocations_pct": {"Cash": 100.0},
            },
            "bots": [],
        },
    )
    analysis["question_focus"] = "exposure"

    message = service._portfolio_daily_coach_message(analysis)

    assert "Exposure-check: nee" in message
    assert "praktisch in cash" in message
    assert "grootste aandachtspunt is BTC: macro blokkeert" in message


def test_portfolio_exposure_question_explains_overallocated_negative_cash():
    service = _service()
    blocked_btc = {
        "asset": "BTC",
        "stance": "wait_for_plan",
        "has_scores": True,
        "setup": {"id": 2, "name": "BTC DCA"},
        "blockers": [{"category": "market", "score": 10, "range": [20, 60]}],
        "bot_today": {"decision_count": 0},
        "indicator_summary": {"warnings": []},
        "data_readiness": {"status": "ready", "config_gaps": []},
    }
    analysis = service._build_portfolio_daily_coach_analysis(
        [blocked_btc],
        {
            "global": {
                "total_equity": 1000,
                "current_position_value": 1667.5,
                "cash_balance": -667.5,
                "allocations_pct": {"Cash": -66.75, "BTC": 166.75},
            },
            "bots": [
                {"bot_id": 1, "symbol": "BTC", "position_value": 1667.5, "budget_total": 1000, "is_active": True, "is_live": False},
            ],
        },
    )
    analysis["question_focus"] = "exposure"

    message = service._portfolio_daily_coach_message(analysis)

    assert "boven portfolio-equity" in message
    assert "negatief" in message
    assert "overallocatie" in message
    assert "overlappende botbudgetten" in message


def test_portfolio_ignore_today_question_lists_assets_and_reentry_condition():
    service = _service()
    blocked_btc = {
        "asset": "BTC",
        "stance": "wait_for_plan",
        "has_scores": True,
        "setup": {"id": 2, "name": "BTC DCA"},
        "blockers": [{"category": "macro", "score": 10, "range": [30, 70]}],
        "bot_today": {"decision_count": 0},
        "indicator_summary": {"warnings": []},
        "data_readiness": {"status": "ready", "config_gaps": []},
    }
    scoreless_sol = {
        "asset": "SOL",
        "stance": "wait_for_scores",
        "has_scores": False,
        "setup": {"id": 3, "name": "SOL DCA"},
        "blockers": [],
        "bot_today": {"decision_count": 0},
        "indicator_summary": {"warnings": []},
        "data_readiness": {"status": "onboarding_incomplete", "config_gaps": ["macro"]},
    }

    analysis = service._build_portfolio_daily_coach_analysis(
        [blocked_btc, scoreless_sol],
        {
            "global": {
                "total_equity": 1000,
                "current_position_value": 400,
                "cash_balance": 600,
                "allocations_pct": {"Cash": 60.0, "BTC": 40.0},
            },
            "bots": [
                {"bot_id": 1, "symbol": "BTC", "position_value": 400, "budget_total": 500, "is_active": True, "is_live": False},
            ],
        },
    )
    analysis["question_focus"] = "ignore_today"

    message = service._portfolio_daily_coach_message(analysis)

    assert analysis["portfolio_risk"]["ignore_today_assets"][0]["asset"] == "BTC"
    assert any(item["asset"] == "SOL" for item in analysis["portfolio_risk"]["ignore_today_assets"])
    assert "Vandaag liever negeren:" in message
    assert "BTC: setup blokkeert nog." in message
    assert "SOL: daily score of datalaag is nog niet betrouwbaar." in message
    assert "Opnieuw oppakken als:" in message


def test_daily_score_fetch_uses_runtime_refresh_when_raw_scores_are_missing(monkeypatch):
    service = FinnPlanService(db_session=object())
    fetch_scores = AsyncMock(side_effect=[None, {"macro_score": 10, "technical_score": 20, "market_score": 30}])
    refresh_scores = AsyncMock()

    class Repo:
        def __init__(self, session):
            self.session = session
        fetch_daily_scores = fetch_scores

    class RuntimeScoreService:
        def __init__(self, repo):
            self.repo = repo
        get_daily_scores = refresh_scores

    monkeypatch.setattr("backend.services.finn_plan_service.ScoreRepository", Repo)
    monkeypatch.setattr("backend.services.finn_plan_service.ScoreService", RuntimeScoreService)

    result = asyncio.run(service._fetch_daily_scores_with_runtime_refresh(7, "BTC"))

    assert result["macro_score"] == 10
    assert fetch_scores.await_count == 2
    refresh_scores.assert_awaited_once_with(7, "BTC")


def test_daily_data_readiness_separates_onboarding_from_score_generation():
    service = _service()
    indicator_analysis = {
        "categories": {
            "macro": {"active_count": 0},
            "technical": {"active_count": 1},
            "market": {"active_count": 0},
        }
    }

    readiness = service._build_daily_data_readiness(
        daily_scores=None,
        indicator_analysis=indicator_analysis,
        onboarding_status={
            "has_macro": False,
            "has_technical": True,
            "has_market": False,
        },
    )

    assert readiness["status"] == "onboarding_incomplete"
    assert readiness["onboarding_gaps"] == ["macro", "market"]
    assert "Rond eerst" in readiness["suggested_actions"][0]
    assert any("macro-indicator" in action for action in readiness["suggested_actions"])


def test_daily_data_readiness_marks_score_generation_gap_when_config_exists():
    service = _service()
    indicator_analysis = {
        "categories": {
            "macro": {"active_count": 1},
            "technical": {"active_count": 1},
            "market": {"active_count": 1},
        }
    }

    readiness = service._build_daily_data_readiness(
        daily_scores=None,
        indicator_analysis=indicator_analysis,
        onboarding_status={
            "has_macro": True,
            "has_technical": True,
            "has_market": True,
        },
    )

    assert readiness["status"] == "score_generation_missing"
    assert readiness["config_gaps"] == []
    assert "Genereer daily scores opnieuw" in readiness["suggested_actions"][0]


def test_daily_data_readiness_explains_config_gaps_even_when_scores_exist():
    service = _service()
    indicator_analysis = {
        "categories": {
            "macro": {"active_count": 1},
            "technical": {"active_count": 1},
            "market": {"active_count": 0},
        }
    }

    readiness = service._build_daily_data_readiness(
        daily_scores={"macro_score": 50, "technical_score": 25, "market_score": 10},
        indicator_analysis=indicator_analysis,
        onboarding_status={
            "has_macro": True,
            "has_technical": True,
            "has_market": False,
        },
    )

    assert readiness["status"] == "ready_with_gaps"
    assert readiness["config_gaps"] == ["market"]
    assert "Daily scores zijn beschikbaar" in readiness["message"]
    assert "market" in readiness["message"]


def test_daily_follow_up_actions_handoff_to_existing_flows():
    service = _service()

    actions = service._daily_follow_up_actions(
        "BTC",
        {"status": "ready_with_gaps", "config_gaps": ["macro", "technical"]},
        [{"category": "macro"}],
        [],
    )

    handoffs = [action["handoff"] for action in actions]
    assert "indicator_config" in handoffs
    assert "daily_score_refresh" in handoffs
    assert "indicator_insight" in handoffs
    assert "bot_decision" in handoffs
    assert any(action["prompt"] == "Voeg Bitcoin Dominance toe aan macro" for action in actions)


def test_portfolio_follow_up_actions_include_guided_briefing_handoffs():
    service = _service()

    actions = service._portfolio_follow_up_actions(
        [{"asset": "BTC"}],
        {"config_gap_assets": ["BTC"]},
    )

    prompts = [action["prompt"] for action in actions]
    assert "Voeg Bitcoin Dominance toe aan macro" in prompts
    assert "Ververs daily scores" in prompts
    assert "Waarom blokkeert macro mijn BTC setup?" in prompts
    assert "Maak bot-decision voor BTC" in prompts


def test_mission_control_builds_open_actions_and_plan_health_from_daily_analysis():
    service = _service()
    daily_analysis = service._build_portfolio_daily_coach_analysis([
        {
            "asset": "BTC",
            "stance": "wait_for_plan",
            "has_scores": True,
            "setup": {"id": 12, "name": "BTC DCA"},
            "setup_match_percentage": 33,
            "blockers": [{"category": "macro", "score": 10, "range": [30, 70]}],
            "active_strategy": {
                "active": False,
                "strategy_exists": True,
                "strategy": {"id": 91, "name": "BTC DCA Strategy"},
            },
            "bot_today": {"decision_count": 0, "decisions": []},
            "indicator_summary": {"warnings": ["macro-laag is dun"]},
            "data_readiness": {"status": "ready_with_gaps", "config_gaps": ["macro"]},
            "follow_up_actions": service._daily_follow_up_actions(
                "BTC",
                {"status": "ready_with_gaps", "config_gaps": ["macro"]},
                [{"category": "macro"}],
                [],
            ),
        },
        {
            "asset": "ETH",
            "stance": "plan_is_active",
            "has_scores": True,
            "setup": {"id": 13, "name": "ETH DCA"},
            "setup_match_percentage": 100,
            "blockers": [],
            "bot_today": {"decision_count": 1, "decisions": [{"id": 7, "bot_id": 3, "action": "buy", "status": "proposed"}]},
            "indicator_summary": {"warnings": []},
            "data_readiness": {"status": "ready", "config_gaps": []},
            "follow_up_actions": [],
        },
    ])

    mission = service._build_mission_control_from_daily_analysis(daily_analysis)

    assert mission["summary"]["asset_count"] == 2
    assert mission["summary"]["active_count"] == 1
    assert mission["summary"]["blocked_count"] == 1
    assert mission["summary"]["open_action_count"] >= 1
    assert mission["summary"]["workqueue_count"] >= 2
    assert mission["workqueue"][0]["type"] == "bot_decision"
    assert mission["workqueue"][0]["priority"] == "high"
    assert mission["workqueue"][0]["status"] == "review_ready"
    assert mission["workqueue"][0]["resolve_state"] == "needs_user_confirmation"
    assert mission["workqueue_labels"]["first"] == "Eerst dit"
    assert [group["key"] for group in mission["workqueue_groups"]] == ["first", "review"]
    first_group = mission["workqueue_groups"][0]
    assert first_group["label"] == "Eerst dit"
    assert first_group["count"] >= 3
    assert first_group["items"][0]["type"] == "bot_decision"
    review_group = mission["workqueue_groups"][1]
    assert review_group["label"] == "Daarna reviewen"
    assert any(item["type"] == "blocked_plan" for item in review_group["items"])
    assert any(item["type"] == "blocked_plan" and item["asset"] == "BTC" for item in mission["workqueue"])
    assert any(item["type"] == "score_refresh" for item in mission["workqueue"])
    assert any(item["type"] == "indicator_gap" for item in mission["workqueue"])
    blocked_item = next(item for item in mission["workqueue"] if item["type"] == "blocked_plan" and item["asset"] == "BTC")
    assert blocked_item["resolve_state"] == "monitor_today"
    assert blocked_item["resolve_action"]["type"] == "resolve_mission_item"
    assert blocked_item["resolve_action"]["payload"]["resolution"] == "monitor_today"
    assert mission["workqueue"] == [
        item
        for group in mission["workqueue_groups"]
        for item in group["items"]
    ]
    assert mission["plan_health"][0]["asset"] == "ETH"
    btc_health = next(item for item in mission["plan_health"] if item["asset"] == "BTC")
    assert btc_health["status"] == "blocked"
    assert btc_health["health_score"] == 23
    assert btc_health["health_grade"] == "blocked"
    assert btc_health["category_checks"][0]["category"] == "macro"
    assert btc_health["category_checks"][0]["status"] == "blocked"
    assert btc_health["lifecycle"]["setup"]["status"] == "configured"
    assert btc_health["lifecycle"]["strategy"]["status"] == "configured_not_active_today"
    assert btc_health["lifecycle"]["strategy"]["id"] == 91
    assert btc_health["lifecycle"]["data"]["status"] == "ready_with_gaps"
    assert btc_health["next_best_action"]["handoff"] == "indicator_insight"
    assert any(action["handoff"] == "indicator_config" for action in mission["open_actions"])
    assert any(action["handoff"] == "daily_score_refresh" for action in mission["open_actions"])
    review = mission["bot_review_queue"][0]
    assert review["decision_id"] == 7
    assert review["review_status"] == "needs_review"
    assert review["risk_level"] == "medium"
    assert review["review_actions"][0]["handoff"] == "bot_decision_review"


def test_mission_control_builds_coaching_loop_from_workqueue_behavior_and_risk():
    service = _service()
    daily_analysis = service._build_portfolio_daily_coach_analysis([
        {
            "asset": "BTC",
            "stance": "wait_for_plan",
            "has_scores": True,
            "setup": {"id": 12, "name": "BTC DCA"},
            "setup_match_percentage": 33,
            "blockers": [{"category": "macro", "score": 10, "range": [30, 70]}],
            "active_strategy": {
                "active": False,
                "strategy_exists": True,
                "strategy": {"id": 91, "name": "BTC DCA Strategy"},
            },
            "bot_today": {"decision_count": 0, "decisions": []},
            "indicator_summary": {"warnings": ["macro-laag is dun"]},
            "data_readiness": {"status": "ready_with_gaps", "config_gaps": ["macro"]},
            "follow_up_actions": service._daily_follow_up_actions(
                "BTC",
                {"status": "ready_with_gaps", "config_gaps": ["macro"]},
                [{"category": "macro"}],
                [],
            ),
        },
        {
            "asset": "ETH",
            "stance": "plan_is_active",
            "has_scores": True,
            "setup": {"id": 13, "name": "ETH DCA"},
            "setup_match_percentage": 100,
            "blockers": [],
            "bot_today": {"decision_count": 1, "decisions": [{"id": 7, "bot_id": 3, "action": "buy", "status": "proposed"}]},
            "indicator_summary": {"warnings": []},
            "data_readiness": {"status": "ready", "config_gaps": []},
            "follow_up_actions": [],
        },
    ])
    daily_analysis["portfolio_risk"] = {
        "ignore_today_assets": [
            {"asset": "BTC", "reason": "setup blokkeert nog", "unblock_condition": "Wacht tot setup niet meer blokkeert."}
        ],
        "live_bot_hotspots": [
            {"asset": "ETH", "summary": "live bot vraagt review", "risk_score": 82, "live_bot_count": 1}
        ],
    }
    mission = service._build_mission_control_from_daily_analysis(daily_analysis)
    coaching_loop = service._build_mission_coaching_loop(
        mission,
        daily_analysis,
        {
            "coaching": {
                "focus_now": "Beperk je tot de bovenste werkqueue-items.",
                "do_not_do": "Forceer geen nieuwe overrides buiten je topprioriteiten.",
            }
        },
    )

    assert coaching_loop["status"] in {"action_required", "watchful"}
    assert coaching_loop["headline"]
    assert coaching_loop["daily_priority_stack"]
    assert any(item["lane"] == "act_now" for item in coaching_loop["daily_priority_stack"])
    assert any(item["title"] == "BTC vandaag laten liggen" for item in coaching_loop["suppressed_items"])
    assert coaching_loop["operator_handoffs"]
    assert coaching_loop["do_not_do"] == "Forceer geen nieuwe overrides buiten je topprioriteiten."


def test_mission_agent_verdicts_add_memory_agent():
    service = _service()
    verdicts = service._merge_mission_agent_verdicts(
        [{"agent": "risk_agent", "status": "high_attention"}],
        {
            "status": "attention",
            "patterns": ["decision_churn"],
            "metrics": {"decision_churn_events_today": 1},
        },
    )

    assert verdicts[0]["agent"] == "risk_agent"
    memory = verdicts[-1]
    assert memory["agent"] == "memory_agent"
    assert memory["status"] == "attention"
    assert memory["priority"] == "medium"


def test_agent_controller_ranks_verdicts_and_biases_mission_queue():
    service = _service()
    mission = {
        "summary": {"workqueue_count": 2},
        "workqueue": [
            {
                "id": "blocked_plan:BTC:1",
                "type": "blocked_plan",
                "priority_rank": 9,
                "sort_rank": 9,
                "status": "blocked",
                "resolve_state": "monitor_today",
                "asset": "BTC",
                "title": "BTC plan aandacht",
                "reason": "macro score blokkeert.",
            },
            {
                "id": "bot_decision_request:BTC",
                "type": "bot_decision_request",
                "priority_rank": 40,
                "sort_rank": 40,
                "status": "needs_user_confirmation",
                "resolve_state": "needs_user_confirmation",
                "asset": "BTC",
                "title": "Bot-decision maken",
                "reason": "Aanbevolen volgende stap.",
            },
        ],
        "workqueue_groups": [],
    }
    controller = service._build_agent_controller([
        {
            "agent": "risk_agent",
            "label": "Risk Agent",
            "status": "blocked",
            "priority": "high",
            "reason": "Risk Agent blokkeert eerst.",
            "next_action": "Los de blocker op.",
            "evidence": {"blocker_count": 3},
        },
        {
            "agent": "execution_agent",
            "label": "Execution Agent",
            "status": "review_ready",
            "priority": "medium",
            "reason": "Execution kan wachten.",
            "evidence": {"decision_count": 1},
        },
    ], context="mission_control")

    activity_feed = [{
        "type": "agent_controller_handoff",
        "status": "executed",
        "resolve_state": "resolved",
        "agent_accountability": {
            "dominant_agent": "risk_agent",
            "dominant_label": "Risk Agent",
        },
    }]
    updated = service._apply_agent_controller_to_mission(mission, controller, activity_feed=activity_feed)

    assert controller["dominant_agent"] == "risk_agent"
    assert controller.get("primary_action") is None
    assert controller["ranked_verdicts"][0]["controller_rank"] == 1
    assert updated["summary"]["dominant_agent"] == "risk_agent"
    assert updated["agent_controller"]["primary_action"]["prompt"]
    assert updated["agent_controller"]["primary_item_id"] == updated["workqueue"][0]["id"]
    assert updated["agent_accountability"]["dominant_agent"] == "risk_agent"
    assert updated["agent_accountability"]["followed_count"] == 1
    assert updated["agent_learning"]["status"] == "ready"
    assert updated["agent_learning"]["agents"][0]["agent"] == "risk_agent"
    assert updated["operating_rules"]["status"] == "ready"
    assert any(rule["id"] == "risk_agent_first" for rule in updated["operating_rules"]["rules"])
    assert updated["agent_accountability"]["performance_light"]["agents"][0]["agent"] == "risk_agent"
    assert updated["agent_accountability"]["performance_light"]["agents"][0]["followed"] == 1
    assert updated["agent_accountability"]["performance_light"]["policy"]["uses_pnl"] is False
    assert updated["agent_accountability"]["influenced_items"][0]["id"] == "blocked_plan:BTC:1"
    assert updated["workqueue_groups"][0]["key"] == "first"
    assert updated["workqueue"][0]["type"] == "blocked_plan"
    assert updated["workqueue"][0]["controller_rank_boost"] > 0
    assert updated["workqueue"][0]["dominant_agent"] == "risk_agent"


def test_build_mission_control_response_exposes_coaching_loop(monkeypatch):
    service = _service()

    async def daily_response(user_id, query, context=None):
        return {
            "state": {
                "analysis": {
                    "assets": [
                        {
                            "asset": "BTC",
                            "stance": "wait_for_plan",
                            "has_scores": True,
                            "setup": {"id": 12, "name": "BTC DCA"},
                            "setup_match_percentage": 33,
                            "blockers": [{"category": "macro", "score": 10, "range": [30, 70]}],
                            "bot_today": {"decision_count": 1, "decisions": [{"id": 7, "bot_id": 3, "action": "buy", "status": "proposed"}]},
                            "indicator_summary": {"warnings": ["macro-laag is dun"]},
                            "data_readiness": {"status": "ready_with_gaps", "config_gaps": ["macro"]},
                            "follow_up_actions": service._daily_follow_up_actions(
                                "BTC",
                                {"status": "ready_with_gaps", "config_gaps": ["macro"]},
                                [{"category": "macro"}],
                                [],
                            ),
                        }
                    ],
                    "portfolio_risk": {
                        "ignore_today_assets": [
                            {"asset": "BTC", "reason": "setup blokkeert nog", "unblock_condition": "Wacht tot setup niet meer blokkeert."}
                        ],
                        "live_bot_hotspots": [
                            {"asset": "BTC", "summary": "live bot vraagt review", "risk_score": 82, "live_bot_count": 1}
                        ],
                    },
                    "follow_up_actions": [],
                    "asset_count": 1,
                    "date": _utc_now().date().isoformat(),
                }
            }
        }

    async def activity(user_id, limit=40):
        return [
            service._mission_activity_item({
                "id": "finn-review-1",
                "status": "executed",
                "created_at": _utc_now() - timedelta(hours=1),
                "payload": {
                    "action": {"type": "snooze_mission_item"},
                    "result": {"ok": True, "status": "snoozed"},
                },
            })
        ]

    async def resolved_ids(user_id):
        return []

    monkeypatch.setattr(service, "build_portfolio_daily_coach_response", daily_response)
    monkeypatch.setattr(service, "_get_recent_finn_activity", activity)
    monkeypatch.setattr(service, "_get_today_resolved_mission_item_ids", resolved_ids)

    result = asyncio.run(service.build_mission_control_response(1))

    assert result["coaching_loop"]["daily_priority_stack"]
    assert result["coaching_loop"]["operator_handoffs"]
    assert result["summary"]["daily_priority_count"] >= 1
    assert result["summary"]["suppressed_count"] >= 1


def test_build_mission_control_response_uses_fast_context_and_single_activity_fetch(monkeypatch):
    service = _service()
    seen_contexts = []
    seen_limits = []

    async def daily_response(user_id, query, context=None):
        seen_contexts.append(context or {})
        return {
            "state": {
                "analysis": {
                    "assets": [],
                    "follow_up_actions": [],
                    "asset_count": 0,
                    "date": _utc_now().date().isoformat(),
                }
            }
        }

    async def activity(user_id, limit=40):
        seen_limits.append(limit)
        return [
            service._mission_activity_item({
                "id": f"finn-review-{idx}",
                "status": "executed",
                "created_at": _utc_now() - timedelta(hours=idx),
                "payload": {
                    "action": {"type": "skip_bot_decision" if idx % 2 == 0 else "snooze_mission_item"},
                    "result": {"ok": True, "status": "skipped" if idx % 2 == 0 else "snoozed"},
                },
            })
            for idx in range(8)
        ]

    async def resolved_ids(user_id):
        return []

    monkeypatch.setattr(service, "build_portfolio_daily_coach_response", daily_response)
    monkeypatch.setattr(service, "_get_recent_finn_activity", activity)
    monkeypatch.setattr(service, "_get_today_resolved_mission_item_ids", resolved_ids)

    result = asyncio.run(service.build_mission_control_response(1, {"page": "assistant", "scope": "mission_control"}))

    assert result["intent"] == "mission_control"
    assert seen_contexts
    assert seen_contexts[0]["mission_control_fast"] is True
    assert seen_limits == [180]


def test_build_mission_control_explain_response_uses_daily_preview_fast_path(monkeypatch):
    service = _service()
    seen_contexts = []

    async def daily_response(user_id, query, context=None):
        seen_contexts.append(context or {})
        return {
            "state": {
                "analysis": {
                    "asset_count": 1,
                    "date": _utc_now().date().isoformat(),
                    "assets": [
                        {
                            "asset": "BTC",
                            "stance": "wait_for_plan",
                            "blockers": [{"category": "market"}],
                            "bot_today": {"decision_count": 2},
                            "follow_up_actions": [],
                            "indicator_summary": {"warnings": ["market weak"]},
                            "portfolio_risk": {
                                "ignore_today_assets": [{"asset": "ETH", "reason": "setup blokkeert"}],
                            },
                        }
                    ],
                    "follow_up_actions": [],
                    "portfolio_risk": {
                        "ignore_today_assets": [{"asset": "ETH", "reason": "setup blokkeert"}],
                    },
                }
            }
        }

    monkeypatch.setattr(service, "build_portfolio_daily_coach_response", daily_response)

    result = asyncio.run(service.build_mission_control_explain_response(1, "Wat zegt Mission Control?", {"page": "dashboard"}))

    assert result["intent"] == "mission_control_explain"
    assert seen_contexts
    assert seen_contexts[0]["mission_control_fast"] is True
    assert seen_contexts[0]["mission_control_preview_only"] is True
    assert result["analysis"]["mission_control_source"] == "daily_coach_preview"
    assert "Mission Control zegt nu in het kort" in result["response"]
    summary = result["analysis"]["mission_control_summary"]
    titles = [item["title"] for item in summary["top_3"]]
    assert len(titles) == len(set(titles))
    assert all(item["title"] != "None" for item in summary["avoid_today"])


def test_build_mission_control_explain_response_prefers_operator_priority_over_refresh(monkeypatch):
    service = FinnPlanService(db_session=object())
    monkeypatch.setattr(service, "build_portfolio_daily_coach_response", AsyncMock(return_value={"state": {"analysis": {"portfolio_risk": {}}}}))
    monkeypatch.setattr(service, "_fetch_recent_governance_events", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_build_mission_control_from_daily_analysis", lambda analysis: {
        "workqueue": [
            {
                "title": "Daily scores verversen",
                "type": "score_refresh",
                "priority": "high",
                "priority_rank": 10,
                "reason": "Data loopt achter",
            },
            {
                "title": "BTC live bots vragen review",
                "type": "portfolio_live_hotspot",
                "priority": "high",
                "priority_rank": 6,
                "reason": "Er staat live reviewdruk op BTC bots",
            },
            {
                "title": "ETH risico stapelt",
                "type": "portfolio_risk_stack",
                "priority": "high",
                "priority_rank": 7,
                "reason": "ETH setups en bots stapelen risico",
            },
        ],
        "summary": {"workqueue_count": 3, "open_action_count": 2},
    })

    result = asyncio.run(service.build_mission_control_explain_response(1, "Vat Mission Control samen in drie bullets", {"page": "dashboard"}))

    summary = result["analysis"]["mission_control_summary"]
    assert summary["top_3"][0]["title"] == "BTC live bots vragen review"
    assert not summary["headline"].startswith("Belangrijkste focus nu: Daily scores verversen")


def test_build_mission_control_response_exposes_v3_surfaces(monkeypatch):
    service = FinnPlanService(db_session=object())
    monkeypatch.setattr(service, "build_portfolio_daily_coach_response", AsyncMock(return_value={
        "state": {
            "analysis": {
                "portfolio_risk": {
                    "status": "high_attention",
                    "message": "BTC exposure en live bots vragen aandacht.",
                    "top_asset": "BTC",
                    "top_reason": "BTC exposure is te dominant.",
                    "ignore_today_assets": [{"asset": "ETH", "reason": "setup blokkeert"}],
                    "live_bot_hotspots": [{"asset": "BTC"}],
                },
                "agent_verdicts": [],
                "data_readiness": {},
            }
        }
    }))
    monkeypatch.setattr(service, "_build_mission_control_from_daily_analysis", lambda analysis: {
        "summary": {"open_action_count": 3, "blocked_count": 1, "workqueue_count": 1},
        "plan_health": [{"asset": "BTC", "status": "blocked"}],
        "portfolio_risk": analysis.get("portfolio_risk") or {},
        "open_actions": [],
        "bot_review_queue": [],
        "workqueue": [
            {
                "id": "review",
                "title": "BTC live bots vragen review",
                "type": "portfolio_live_hotspot",
                "priority": "high",
                "priority_rank": 6,
                "reason": "Er staat live reviewdruk op BTC bots",
                "asset": "BTC",
            }
        ],
        "workqueue_groups": [],
        "workqueue_labels": {},
        "agent_verdicts": [],
    })
    monkeypatch.setattr(service, "_get_recent_finn_activity", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_get_today_resolved_mission_item_ids", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_fetch_recent_governance_events", AsyncMock(return_value=[
        {
            "type": "finn_decision_review",
            "symbol": "BTC",
            "description": "Mijn review blokkeert dit nu.",
            "payload": {"asset": "BTC", "decision_status": "block", "top_blockers": ["BTC exposure te hoog."]},
        },
        {
            "type": "finn_plan_adherence_review",
            "symbol": "BTC",
            "description": "Je probeert een plan- of strategiegrens te overrulen.",
            "payload": {"asset": "BTC", "adherence_status": "forced_override", "threatened_rule": "Planoverride"},
        },
    ]))

    result = asyncio.run(service.build_mission_control_response(1, {"page": "assistant", "scope": "mission_control"}))

    assert result["priority_engine"]["headline"]
    assert result["memory_v2"]["memory_pattern"]
    assert result["portfolio_operating_system"]["control_plane"]["headline"]
    assert result["governance_events_summary"]["decision_review_count"] == 1


def test_build_portfolio_daily_coach_response_preview_only_skips_strategy_bot_and_indicator_reads(monkeypatch):
    service = FinnPlanService(db_session=object())
    calls = {"strategy": 0, "bot_today": 0, "indicator_fast": 0}

    class _ScoreRepo:
        def __init__(self, session):
            self.session = session

        async def fetch_active_setups(self, user_id):
            return [{"id": 62, "symbol": "BTC", "name": "Breakout long test", "is_active": True}]

    class _StrategyRepo:
        async def get_strategy_by_setup(self, setup_id, user_id):
            calls["strategy"] += 1
            return {"id": 257, "name": "Should not be loaded"}

    class _StrategySvc:
        def __init__(self, session):
            self.repository = _StrategyRepo()

        def _format_strategy_row(self, row):
            return row

    class _BotSvc:
        def __init__(self, session):
            self.session = session

        async def get_bot_today(self, user_id, symbol=None, lean=False):
            calls["bot_today"] += 1
            return {"decisions": [{"id": 121110}]}

    async def fake_scores(user_id, asset, allow_refresh=True):
        return {"macro_score": 50, "technical_score": 42, "market_score": 18, "setup_score": 73}

    async def fake_onboarding(user_id):
        return {}

    async def fake_indicator_fast(user_id, asset, daily_scores):
        calls["indicator_fast"] += 1
        return {"asset": asset, "warnings": ["should not run"]}

    def fake_eval_setup(setup, daily_scores):
        return {
            "setup": {"id": setup["id"], "name": setup["name"]},
            "is_active": True,
            "match_percentage": 100,
            "blockers": [],
            "passed_checks": [],
        }

    def fake_setup_context(setups_by_asset):
        return {"BTC": {"setup_count": 1}}

    def fake_daily_analysis(**kwargs):
        return {
            "asset": kwargs["asset"],
            "setup": kwargs["setup_analysis"]["setup"],
            "stance": "plan_is_active",
            "has_scores": True,
            "setup_active": True,
            "setup_match_percentage": 100,
            "blockers": [],
            "passed_checks": [],
            "active_strategy": kwargs["active_strategy"],
            "bot_today": kwargs["bot_today"],
            "indicator_summary": kwargs["indicator_analysis"],
            "indicator_analysis": kwargs["indicator_analysis"],
            "data_readiness": {"status": "ready", "config_gaps": []},
            "follow_up_actions": [],
            "agent_verdicts": [],
        }

    def fake_portfolio_analysis(asset_analyses, portfolio_context, setup_context_by_asset):
        return {
            "asset_count": len(asset_analyses),
            "assets": asset_analyses,
            "follow_up_actions": [],
            "portfolio_risk": {"status": "balanced", "ignore_today_assets": [], "live_bot_hotspots": [], "risk_stacks": []},
            "suggested_actions": [],
            "has_any_scores": True,
            "reasons": [],
        }

    monkeypatch.setattr(finn_plan_module, "ScoreRepository", _ScoreRepo)
    monkeypatch.setattr(finn_plan_module, "StrategyService", _StrategySvc)
    monkeypatch.setattr(finn_plan_module, "BotService", _BotSvc)
    monkeypatch.setattr(service, "_fetch_daily_scores_with_runtime_refresh", fake_scores)
    monkeypatch.setattr(service, "_fetch_onboarding_status", fake_onboarding)
    monkeypatch.setattr(service, "_build_indicator_analysis_fast", fake_indicator_fast)
    monkeypatch.setattr(service, "_evaluate_setup_row", fake_eval_setup)
    monkeypatch.setattr(service, "_portfolio_setup_context", fake_setup_context)
    monkeypatch.setattr(service, "_build_daily_coach_analysis", fake_daily_analysis)
    monkeypatch.setattr(service, "_build_portfolio_daily_coach_analysis", fake_portfolio_analysis)

    result = asyncio.run(
        service.build_portfolio_daily_coach_response(
            1,
            "Geef mijn daily brief",
            {"scope": "mission_control", "mission_control_fast": True, "mission_control_preview_only": True},
        )
    )

    analysis = result["state"]["analysis"]
    asset = analysis["assets"][0]
    assert result["intent"] == "daily_coach"
    assert calls == {"strategy": 0, "bot_today": 0, "indicator_fast": 0}
    assert asset["active_strategy"]["preview_only"] is True
    assert asset["bot_today"]["preview_only"] is True
    assert asset["indicator_summary"]["preview_only"] is True


def test_agent_controller_handoff_activity_counts_in_finn_report():
    service = _service()
    now = _utc_now().isoformat()
    activity = [
        {
            "type": "agent_controller_handoff",
            "label": "Agent-handoff gevolgd",
            "status": "executed",
            "resolve_state": "resolved",
            "asset": "BTC",
            "created_at": now,
            "agent_accountability": {
                "dominant_agent": "risk_agent",
                "dominant_label": "Risk Agent",
                "primary_action_label": "Portfolio-risico bekijken",
                "primary_action_handoff": "daily_coach",
            },
        }
    ]
    behavioral = service._build_behavioral_insight_from_activity(activity)

    report = service._build_finn_reflection_report(activity, behavioral, "Geef mijn Finn rapport van vandaag")
    message = service._finn_reflection_report_message(report)

    assert report["metrics"]["agent_controller_handoffs"] == 1
    assert report["metrics"]["agent_accountability_events"] == 1
    assert report["metrics"]["agent_accountability_by_agent"]["risk_agent"] == 1
    assert report["metrics"]["agent_performance_light"]["agents"][0]["agent"] == "risk_agent"
    assert report["metrics"]["agent_performance_light"]["policy"]["claims_performance"] is False
    assert report["agent_accountability"]["by_agent"]["risk_agent"] == 1
    assert report["agent_learning"]["agents"][0]["agent"] == "risk_agent"
    assert report["agent_learning"]["policy"]["uses_pnl"] is False
    assert report["operating_rules"]["policy"]["stores_new_preferences"] is False
    assert any(rule["id"] == "risk_agent_first" for rule in report["operating_rules"]["rules"])
    assert report["agent_accountability"]["performance_light"]["agents"][0]["followed"] == 1
    assert any(item["type"] == "agent_controller_handoff" for item in report["risk_officer_interventions"])
    assert "Agent accountability:" in message
    assert "Learning light:" in message


def test_recent_finn_activity_query_includes_agent_controller_handoffs():
    service = _service()
    query = service._get_recent_finn_activity.__code__.co_consts[1]

    assert "payload->'action'->>'type' = 'agent_controller_handoff'" in query
    assert "payload->'result'->>'type' = 'agent_controller_handoff'" in query


def test_bot_decision_review_items_escalate_guardrail_risk():
    service = _service()

    review = service._mission_bot_review_item(
        {
            "id": 22,
            "bot_id": 9,
            "symbol": "BTC",
            "action": "buy",
            "confidence": 0.48,
            "status": "planned",
            "amount_eur": 100,
            "guardrails_result": False,
            "guardrail_reason": "Daglimiet overschreden",
            "reasons": ["macro is actief"],
            "setup_match": {"status": "partial", "score": 67},
            "trade_plan": {"targets": [{"price": 120}]},
        },
        {"asset": "BTC", "setup": {"id": 12}},
    )

    assert review["risk_level"] == "high"
    assert review["review_status"] == "needs_review"
    assert review["summary"] == "BTC: buy voor EUR 100 - guardrail aandacht"
    assert review["trade_plan_present"] is True
    assert review["review_actions"][0]["prompt"] == "Leg bot-decision 22 uit"
    assert any(action["handoff"] == "bot_execution_decision" and "paper" in action["label"].lower() for action in review["review_actions"])
    assert any(action["handoff"] == "bot_execution_decision" and "overslaan" in action["label"].lower() for action in review["review_actions"])


def test_bot_decision_review_copy_handles_hold_without_raw_none_or_zero_amount():
    service = _service()
    review = service._mission_bot_review_item(
        {
            "id": 23,
            "bot_id": 9,
            "symbol": "BTC",
            "action": "hold",
            "confidence": None,
            "status": "planned",
            "amount_eur": 0,
        },
        {"asset": "BTC", "setup": {"id": 12}},
    )
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
    response = "\n".join(lines)

    assert "Confidence: onbekend" in response
    assert "geen orderbedrag" in response
    assert "EUR 0" not in response
    assert "None" not in response


def test_bot_decision_review_summary_handles_hold_without_zero_amount():
    service = _service()
    review = service._mission_bot_review_item(
        {
            "id": 24,
            "bot_id": 9,
            "symbol": "BTC",
            "action": "hold",
            "status": "planned",
            "amount_eur": 0,
        },
        {"asset": "BTC", "setup": {"id": 12}},
    )

    assert review["summary"] == "BTC: hold - geen orderbedrag"
    assert "EUR 0" not in review["summary"]


def test_bot_decision_execution_review_explains_why_and_next_actions():
    service = _service()
    review = {
        "decision_id": 108032,
        "asset": "BTC",
        "summary": "BTC: buy voor EUR 150 - guardrail aandacht",
        "risk_level": "high",
        "review_status": "needs_review",
        "guardrail_reason": "Daglimiet overschreden",
        "reasons": ["Macro setup is nog zwak", "Confidence is laag"],
        "review_actions": [
            {"label": "Decision uitleg", "prompt": "Leg bot-decision 108032 uit", "handoff": "bot_decision_review"},
            {"label": "Paper uitvoeren", "prompt": "Voer bot-decision 108032 paper uit", "handoff": "bot_execution_decision", "requires_confirmation": True},
        ],
        "confidence": 0.48,
        "amount_eur": 150,
        "action": "buy",
    }

    card = service._build_bot_decision_execution_review(review)

    assert card["topic"] == "bot_decision_review"
    assert card["status"] == "needs_review"
    assert "Daglimiet overschreden" in card["why_now"]
    assert any(action["handoff"] == "bot_execution_decision" for action in card["actions"])
    assert any(item["label"] == "Confidence" for item in card["evidence"])


def test_mission_control_excludes_handled_bot_decisions():
    service = _service()
    daily_analysis = {
        "assets": [
            {
                "asset": "BTC",
                "stance": "plan_is_active",
                "has_scores": True,
                "setup": {"id": 12, "name": "BTC DCA"},
                "blockers": [],
                "bot_today": {
                    "decisions": [
                        {"id": 21, "bot_id": 9, "symbol": "BTC", "action": "hold", "status": "skipped"},
                        {"id": 22, "bot_id": 9, "symbol": "BTC", "action": "buy", "status": "planned"},
                    ]
                },
                "indicator_summary": {"warnings": []},
                "data_readiness": {"status": "ready", "config_gaps": []},
                "follow_up_actions": [],
            }
        ],
        "follow_up_actions": [],
    }

    mission = service._build_mission_control_from_daily_analysis(daily_analysis)

    assert [item["decision_id"] for item in mission["bot_review_queue"]] == [22]
    handled = service._mission_bot_review_item(
        {"id": 21, "bot_id": 9, "symbol": "BTC", "action": "buy", "status": "skipped"},
        {"asset": "BTC", "setup": {"id": 12}},
    )
    assert handled["review_status"] == "handled"
    assert not any(action["handoff"] == "bot_execution_decision" for action in handled["review_actions"])


def test_mission_workqueue_dedupes_actions_and_preserves_priority_order():
    service = _service()
    action = {
        "label": "Daily scores verversen",
        "prompt": "Ververs daily scores",
        "handoff": "daily_score_refresh",
        "requires_confirmation": True,
        "asset": "BTC",
        "setup_id": 12,
        "priority_rank": 10,
    }
    low_action = {
        "label": "Macro uitleg",
        "prompt": "Waarom blokkeert macro mijn BTC setup?",
        "handoff": "indicator_insight",
        "requires_confirmation": False,
        "asset": "BTC",
        "priority_rank": 30,
    }

    queue = service._dedupe_workqueue([
        service._mission_workqueue_from_action(low_action),
        service._mission_workqueue_from_action(action),
        service._mission_workqueue_from_action(action),
    ])

    assert len(queue) == 2
    assert queue[0]["type"] == "score_refresh"
    assert queue[0]["status"] == "needs_user_confirmation"
    assert queue[0]["resolve_state"] == "needs_user_confirmation"
    assert queue[0]["next_best_action"]["handoff"] == "daily_score_refresh"
    assert queue[0]["sort_rank"] == queue[0]["priority_rank"]
    assert queue[1]["priority"] == "low"
    assert queue[1]["resolve_state"] == "monitor_today"
    assert queue[1]["freshness"]["status"] == "unknown"


def test_mission_workqueue_freshness_marks_fresh_bot_decision():
    service = _service()
    fresh_timestamp = (_utc_now() - timedelta(minutes=30)).isoformat()
    review = service._mission_bot_review_item(
        {
            "id": 30,
            "bot_id": 9,
            "symbol": "BTC",
            "action": "buy",
            "status": "planned",
            "created_at": fresh_timestamp,
        },
        {"asset": "BTC", "setup": {"id": 12}},
    )

    item = service._mission_workqueue_from_bot_review(review)

    assert item["priority"] == "high"
    assert item["status"] == "review_ready"
    assert item["resolve_state"] == "needs_user_confirmation"
    assert item["priority_rank"] == 8
    assert item["sort_rank"] == 8
    assert item["freshness"]["status"] == "fresh"
    assert 25 <= item["freshness"]["age_minutes"] <= 35


def test_mission_workqueue_freshness_marks_aging_bot_decision():
    service = _service()
    aging_timestamp = (_utc_now() - timedelta(hours=3)).isoformat().replace("+00:00", "Z")
    review = service._mission_bot_review_item(
        {
            "id": 31,
            "bot_id": 9,
            "symbol": "BTC",
            "action": "buy",
            "status": "planned",
            "updated_at": aging_timestamp,
        },
        {"asset": "BTC", "setup": {"id": 12}},
    )

    item = service._mission_workqueue_from_bot_review(review)

    assert item["status"] == "review_ready"
    assert item["resolve_state"] == "needs_user_confirmation"
    assert item["priority_rank"] == 8
    assert item["sort_rank"] == 8
    assert item["freshness"]["status"] == "aging"
    assert item["freshness"]["age_minutes"] >= 180


def test_mission_workqueue_freshness_marks_stale_bot_decision():
    service = _service()
    old_timestamp = (_utc_now() - timedelta(hours=7)).isoformat()
    review = service._mission_bot_review_item(
        {
            "id": 30,
            "bot_id": 9,
            "symbol": "BTC",
            "action": "buy",
            "status": "planned",
            "created_at": old_timestamp,
        },
        {"asset": "BTC", "setup": {"id": 12}},
    )

    item = service._mission_workqueue_from_bot_review(review)

    assert item["priority"] == "high"
    assert item["status"] == "stale"
    assert item["resolve_state"] == "needs_user_confirmation"
    assert item["priority_rank"] == 5
    assert item["sort_rank"] == 5
    assert item["freshness"]["status"] == "stale"
    assert item["freshness"]["age_minutes"] >= 420


def test_mission_activity_item_summarizes_executed_action():
    service = _service()
    item = service._mission_activity_item({
        "id": "finn-maint-123-u7",
        "status": "executed",
        "created_at": datetime(2026, 5, 21, 12, 0, 0),
        "payload": {
            "updated_at": "2026-05-21T12:01:00+00:00",
            "action": {
                "type": "skip_bot_decision",
                "label": "Bot-decision overslaan",
                "requires_confirmation": True,
                "payload": {"bot_id": 9, "decision_id": 22},
            },
            "result": {
                "ok": True,
                "message": "Bot-decision #22 is overgeslagen.",
                "status": "skipped",
                "bot_id": 9,
                "decision_id": 22,
                "verified": {"bot_decision_skipped": True},
            },
        },
    })

    assert item["type"] == "skip_bot_decision"
    assert item["label"] == "Bot-decision overslaan"
    assert item["status"] == "executed"
    assert item["result_status"] == "skipped"
    assert item["resolve_state"] == "skipped"
    assert item["outcome"] == "Bot-decision #22 is overgeslagen."
    assert item["entity_ids"]["bot_id"] == 9
    assert item["entity_ids"]["decision_id"] == 22
    assert item["verified"]["bot_decision_skipped"] is True


def test_mission_activity_item_marks_pending_and_executed_resolve_states():
    service = _service()
    pending = service._mission_activity_item({
        "id": "finn-pending-1",
        "status": "pending",
        "created_at": datetime(2026, 5, 21, 12, 0, 0),
        "payload": {
            "action": {
                "type": "refresh_daily_scores",
                "label": "Daily scores verversen",
                "requires_confirmation": True,
            }
        },
    })
    executed = service._mission_activity_item({
        "id": "finn-executed-1",
        "status": "executed",
        "created_at": datetime(2026, 5, 21, 12, 0, 0),
        "payload": {
            "action": {"type": "configure_indicator"},
            "result": {"ok": True, "message": "Indicator opgeslagen."},
        },
    })

    assert pending["resolve_state"] == "needs_user_confirmation"
    assert executed["resolve_state"] == "resolved"


def test_mission_workqueue_data_gap_waits_for_data():
    service = _service()
    item = service._mission_workqueue_from_plan({
        "asset": "BTC",
        "status": "data_missing",
        "reason": "Daily scores ontbreken.",
        "setup": {"id": 12},
        "lifecycle": {"strategy": {"id": 91}},
    })

    assert item["type"] == "data_gap"
    assert item["status"] == "blocked_by_data"
    assert item["resolve_state"] == "waiting_for_data"
    assert item["resolve_action"]["payload"]["resolution"] == "waiting_for_data"
    assert [action["payload"]["resolution"] for action in item["resolve_actions"]] == [
        "waiting_for_data",
        "resolved",
        "monitor_today",
        "snoozed",
    ]
    assert item["freshness"]["status"] == "stale"


def test_mission_control_filters_resolved_workqueue_items():
    service = _service()
    mission = {
        "summary": {"workqueue_count": 2},
        "workqueue": [
            {"id": "blocked_plan:BTC:12", "type": "blocked_plan", "resolve_state": "monitor_today"},
            {"id": "score_refresh:daily_score_refresh:BTC:abc", "type": "score_refresh", "resolve_state": "needs_user_confirmation"},
        ],
    }

    filtered = service._filter_resolved_mission_items(mission, {"blocked_plan:BTC:12"})

    assert filtered["summary"]["workqueue_count"] == 1
    assert filtered["workqueue"][0]["type"] == "score_refresh"
    assert filtered["workqueue_groups"][0]["key"] == "first"


def test_mission_activity_item_marks_resolve_action_states():
    service = _service()
    item = service._mission_activity_item({
        "id": "finn-resolve-1",
        "status": "executed",
        "created_at": datetime(2026, 5, 21, 12, 0, 0),
        "payload": {
            "action": {
                "type": "resolve_mission_item",
                "label": "Vandaag monitoren",
                "payload": {"source_item_id": "blocked_plan:BTC:12"},
            },
            "result": {
                "ok": True,
                "message": "Mission Control item staat op monitoren voor vandaag.",
                "status": "monitor_today",
                "source_item_id": "blocked_plan:BTC:12",
                "verified": {"mission_item_resolved": True},
            },
        },
    })

    assert item["type"] == "resolve_mission_item"
    assert item["resolve_state"] == "monitor_today"
    assert item["verified"]["mission_item_resolved"] is True


def test_mission_activity_item_marks_snooze_and_day_log_counts():
    service = _service()
    snoozed = service._mission_activity_item({
        "id": "finn-snooze-1",
        "status": "executed",
        "created_at": datetime(2026, 5, 21, 12, 0, 0),
        "payload": {
            "action": {
                "type": "snooze_mission_item",
                "label": "Later opnieuw bekijken",
                "payload": {"source_item_id": "blocked_plan:BTC:12"},
            },
            "result": {
                "ok": True,
                "message": "Mission Control item is uitgesteld.",
                "status": "snoozed",
                "source_item_id": "blocked_plan:BTC:12",
                "verified": {"mission_item_resolved": True},
            },
        },
    })
    resolved = service._mission_activity_item({
        "id": "finn-resolve-2",
        "status": "executed",
        "created_at": datetime(2026, 5, 21, 12, 0, 0),
        "payload": {
            "action": {"type": "resolve_mission_item", "label": "Markeer klaar"},
            "result": {"ok": True, "status": "resolved", "verified": {"mission_item_resolved": True}},
        },
    })

    day_log = service._mission_day_log([snoozed, resolved])

    assert snoozed["resolve_state"] == "snoozed"
    assert resolved["resolve_state"] == "resolved"
    assert day_log["handled_count"] == 2
    assert day_log["snoozed_count"] == 1
    assert day_log["resolved_count"] == 1


def test_behavioral_intelligence_request_detection_is_read_only():
    service = _service()

    assert service.looks_like_behavioral_intelligence_request("Hoe is mijn trading discipline vandaag?") is True
    assert service.looks_like_behavioral_intelligence_request("Zie je FOMO of impulsief gedrag?") is True
    assert service.looks_like_behavioral_intelligence_request("Wijk ik af van mijn plan?") is True
    assert service.looks_like_behavioral_intelligence_request("Dit voelt als een emotionele beslissing, wat moet ik doen?") is True
    assert service.looks_like_behavioral_intelligence_request("Ik heb er geen goed gevoel bij, wat nu?") is True
    assert service.looks_like_behavioral_intelligence_request("Geef mijn daily brief") is False
    assert service.looks_like_behavioral_intelligence_request("Maak een wekelijkse BTC DCA") is False


def test_weekly_reflection_request_detection_is_separate_from_daily_behavior():
    service = _service()

    assert service.looks_like_weekly_reflection_request("Geef mijn weekreflectie") is True
    assert service.looks_like_weekly_reflection_request("Maak een week review van mijn discipline") is True
    assert service.looks_like_weekly_reflection_request("Hoe was mijn gedrag de laatste 7 dagen?") is True
    assert service.looks_like_weekly_reflection_request("Hoe is mijn trading discipline vandaag?") is False
    assert service.looks_like_weekly_reflection_request("Geef mijn daily brief") is False


def test_behavioral_memory_request_detection_is_separate_from_weekly_reflection():
    service = _service()

    assert service.looks_like_behavioral_memory_request("Geef mijn gedragsrapport van de laatste 30 dagen") is True
    assert service.looks_like_behavioral_memory_request("Wat onthoudt Finn van mijn trading discipline?") is True
    assert service.looks_like_behavioral_memory_request("Maak mijn lange termijn gedragsprofiel") is True
    assert service.looks_like_behavioral_memory_request("Geef mijn weekreflectie") is False
    assert service.looks_like_behavioral_memory_request("Geef mijn daily brief") is False


def test_decision_review_request_detection_is_read_only():
    service = _service()

    assert service.looks_like_decision_review_request("Beoordeel deze trade", {"symbol": "BTC"}) is True
    assert service.looks_like_decision_review_request("Past dit bij mijn strategie?", {"strategy_id": 257, "symbol": "ETH"}) is True
    assert service.looks_like_decision_review_request(
        "Wat vind je van deze trade?",
        {"page": "/dashboard", "page_type": "dashboard", "symbol": "BTC"},
    ) is True
    assert service.looks_like_decision_review_request(
        "Zou jij dit doen?",
        {"page": "/setup", "page_type": "setup", "setup_id": 62, "strategy_id": 257, "symbol": "BTC"},
    ) is True
    assert service.looks_like_decision_review_request("Maak een bot voor BTC", {"symbol": "BTC"}) is False


def test_plan_adherence_review_request_detection_is_separate():
    service = _service()

    assert service.looks_like_plan_adherence_review_request("Wijk ik af van mijn plan?") is True
    assert service.looks_like_plan_adherence_review_request("Handel ik buiten mijn strategie?") is True
    assert service.looks_like_plan_adherence_review_request("Mijn plan zegt wachten maar ik wil kopen") is True
    assert service.looks_like_plan_adherence_review_request("Ik wil mijn stop-loss verwijderen") is True
    assert service.looks_like_plan_adherence_review_request("Beoordeel deze trade") is False


def test_outcome_tracking_request_detection_is_read_only():
    service = _service()

    assert service.looks_like_outcome_tracking_request("Hoe pakte dat uit?") is True
    assert service.looks_like_outcome_tracking_request("Wat leert Finn van mijn uitkomsten?") is True
    assert service.looks_like_outcome_tracking_request("De laatste 8 FOMO trades: 6 verlies, 2 winst. Wat zegt dat?") is True
    assert service.looks_like_outcome_tracking_request("Maak een nieuwe strategie") is False


def test_portfolio_intelligence_request_detection_is_read_only():
    service = _service()

    assert service.looks_like_portfolio_intelligence_request("Heb ik te veel exposure?", {"symbol": "BTC"}) is True
    assert service.looks_like_portfolio_intelligence_request("Wat is mijn grootste portfolio risico?", {"page": "/dashboard"}) is True
    assert service.looks_like_portfolio_intelligence_request(
        "Mag ik extra BTC risico toevoegen?",
        {"page": "/dashboard", "symbol": "BTC"},
    ) is True
    assert service.looks_like_portfolio_intelligence_request(
        "Ik heb 70% BTC / 20% ETH / 10% cash, kan ik nog een BTC long openen?",
        {"page": "/dashboard", "symbol": "BTC"},
    ) is True
    assert service.looks_like_portfolio_intelligence_request("Maak een BTC setup", {"symbol": "BTC"}) is False


def test_priority_engine_request_detection_is_read_only():
    service = _service()

    assert service.looks_like_priority_engine_request("Wat is vandaag mijn hoogste prioriteit?", {"scope": "mission_control"}) is True
    assert service.looks_like_priority_engine_request("Wat moet ik nu eerst doen in Mission Control?", {"page": "mission_control"}) is True
    assert service.looks_like_priority_engine_request("Wat moet ik nu eerst doen?", {"page": "/dashboard"}) is True
    assert service.looks_like_priority_engine_request("Wat kan vandaag wachten?", {"page": "/dashboard"}) is True
    assert service.looks_like_priority_engine_request("Waar moet ik vandaag op focussen?", {"page": "/dashboard"}) is True
    assert service.looks_like_priority_engine_request("Wat zijn vandaag mijn 3 belangrijkste acties?", {"page": "/dashboard"}) is True
    assert service.looks_like_priority_engine_request("Waar moet ik mee beginnen?", {"page": "/dashboard"}) is True
    assert service.looks_like_priority_engine_request("Wat moet ik juist niet doen?", {"page": "/dashboard"}) is True
    assert service.looks_like_priority_engine_request("Help me even kiezen wat ik nu moet doen.", {"page": "/dashboard"}) is True
    assert service.looks_like_priority_engine_request("Maak een BTC setup", {"page": "/dashboard"}) is False


def test_portfolio_operating_system_request_detection_is_read_only():
    service = _service()

    assert service.looks_like_portfolio_operating_system_request("Geef mijn portfolio operating system") is True
    assert service.looks_like_portfolio_operating_system_request("Hoe staat mijn portfolio control plane ervoor?") is True
    assert service.looks_like_portfolio_operating_system_request("Maak een nieuwe strategie") is False


def test_build_decision_review_response_can_approve_contextual_trade():
    service = _service()

    result = asyncio.run(service.build_decision_review_response(30, "Beoordeel deze trade", {
        "page": "/setup",
        "page_type": "setup",
        "symbol": "BTC",
        "setup_id": 62,
        "strategy_id": 257,
        "portfolio_intelligence": {
            "global": {
                "allocations_pct": {"BTC": 24.0, "Cash": 76.0},
            }
        },
    }))

    assert result["intent"] == "decision_review"
    assert result["flow"] == "decision_review"
    assert result["analysis"]["decision_status"] == "approve"
    assert result["analysis"]["review_type"] == "trade_intent_review"
    assert result["analysis"]["snapshot"]["asset"] == "BTC"


def test_build_decision_review_response_blocks_extreme_risk_and_exposure():
    service = _service()

    result = asyncio.run(service.build_decision_review_response(30, "Kan ik deze trade openen met 8% risico?", {
        "page": "/dashboard",
        "page_type": "dashboard",
        "symbol": "BTC",
        "strategy_id": 257,
        "portfolio_intelligence": {
            "global": {
                "allocations_pct": {"BTC": 72.0, "Cash": 28.0},
            }
        },
    }))

    assert result["analysis"]["decision_status"] == "block"
    assert any("72.0%" in item or "8.0%" in item for item in result["analysis"]["top_blockers"])


def test_build_decision_review_response_returns_insufficient_context_when_too_thin():
    service = _service()

    result = asyncio.run(service.build_decision_review_response(30, "Beoordeel deze trade", {}))

    assert result["analysis"]["decision_status"] == "insufficient_context"
    assert result["missing_fields"] == ["context"]


def test_build_plan_adherence_review_response_marks_forced_override():
    service = _service()

    result = asyncio.run(service.build_plan_adherence_review_response(30, "Ik wil toch buiten mijn plan handelen", {
        "page": "/strategy",
        "page_type": "strategy",
        "symbol": "ETH",
        "strategy_id": 257,
    }))

    assert result["intent"] == "plan_adherence_review"
    assert result["analysis"]["adherence_status"] == "forced_override"
    assert result["analysis"]["override_detected"] is True
    assert "overrulen" in (result["analysis"]["threatened_rule"] or "").lower()


def test_build_plan_adherence_review_response_flags_stop_loss_removal_as_rule_break():
    service = _service()

    result = asyncio.run(service.build_plan_adherence_review_response(30, "Ik wil mijn stop-loss verwijderen", {
        "page": "/strategy",
        "page_type": "strategy",
        "symbol": "BTC",
        "strategy_id": 257,
    }))

    assert result["analysis"]["adherence_status"] == "forced_override"
    assert "exit-grens" in (result["analysis"]["threatened_rule"] or "").lower()
    assert "stop-loss" in (result["analysis"]["suggested_recovery_step"] or "").lower()


def test_build_plan_adherence_review_response_can_stay_in_plan():
    service = _service()

    result = asyncio.run(service.build_plan_adherence_review_response(30, "Past dit nog bij mijn plan?", {
        "page": "/setup",
        "page_type": "setup",
        "symbol": "BTC",
        "setup_id": 62,
        "strategy_id": 257,
        "portfolio_intelligence": {
            "global": {
                "allocations_pct": {"BTC": 18.0, "Cash": 82.0},
            }
        },
    }))

    assert result["analysis"]["adherence_status"] == "in_plan"


def test_outcome_tracking_message_stays_low_confidence_without_samples():
    service = _service()

    result = asyncio.run(service.build_outcome_tracking_response(30, "Wat leert Finn van mijn uitkomsten?", {}))

    assert result["intent"] == "outcome_tracking"
    assert result["analysis"]["sample_size"] == 0
    assert "te weinig" in result["analysis"]["historical_result_summary"].lower()


def test_outcome_tracking_response_summarizes_follow_through(monkeypatch):
    service = _service()

    async def _fake_events(user_id, *, event_types, limit=40):
        return [
            {
                "type": "finn_plan_adherence_review",
                "symbol": "BTC",
                "created_at": (_utc_now() - timedelta(days=2)).isoformat(),
                "payload": {
                    "adherence_status": "forced_override",
                    "subject": {"type": "strategy", "id": 257},
                    "asset": "BTC",
                },
            },
            {
                "type": "finn_plan_adherence_review",
                "symbol": "BTC",
                "created_at": (_utc_now() - timedelta(days=1)).isoformat(),
                "payload": {
                    "adherence_status": "outside_plan",
                    "subject": {"type": "strategy", "id": 257},
                    "asset": "BTC",
                },
            },
        ]

    async def _fake_activity(user_id, limit=200):
        return [
            {
                "type": "skip_bot_decision",
                "asset": "BTC",
                "created_at": (_utc_now() - timedelta(days=1, hours=12)).isoformat(),
                "resolve_state": "skipped",
                "entity_ids": {"strategy_id": 257},
            },
            {
                "type": "paper_execute_bot_decision",
                "asset": "BTC",
                "created_at": (_utc_now() - timedelta(hours=18)).isoformat(),
                "resolve_state": "executed",
                "entity_ids": {"strategy_id": 257},
            },
        ]

    monkeypatch.setattr(service, "_fetch_recent_governance_events", _fake_events)
    monkeypatch.setattr(service, "_get_recent_finn_activity", _fake_activity)
    monkeypatch.setattr(service, "_record_governance_event", AsyncMock())

    result = asyncio.run(service.build_outcome_tracking_response(30, "Hoe eindigen mijn planafwijkingen?", {"symbol": "BTC"}))

    assert result["analysis"]["sample_size"] == 2
    assert "2 relevante momenten" in result["analysis"]["historical_result_summary"]
    assert result["analysis"]["behavior_pattern"] == "plan_adherence_outcomes"


def test_outcome_tracking_response_uses_explicit_history_from_query():
    service = _service()
    service._fetch_recent_governance_events = AsyncMock(return_value=[])
    service._get_recent_finn_activity = AsyncMock(return_value=[])
    service._record_governance_event = AsyncMock()

    result = asyncio.run(service.build_outcome_tracking_response(
        30,
        "De laatste 8 FOMO trades: 6 verlies, 2 winst. Gemiddeld resultaat: -4,2%. Wat zegt dat?",
        {"symbol": "BTC"},
    ))

    assert result["analysis"]["sample_size"] == 8
    assert result["analysis"]["behavior_pattern"] == "fomo_outcomes"
    assert "6 verliestrades" in result["analysis"]["historical_result_summary"]
    assert "-4.2%" in result["analysis"]["historical_result_summary"]
    assert "negatief" in result["analysis"]["net_effect"].lower()


def test_build_portfolio_intelligence_response_exposes_contract(monkeypatch):
    service = _service()
    monkeypatch.setattr(service, "build_portfolio_daily_coach_response", AsyncMock(return_value={
        "state": {
            "analysis": {
                "portfolio_risk": {
                    "status": "high_attention",
                    "message": "Er zijn portfolio-risico's die vandaag aandacht vragen.",
                    "asset_risk": [
                        {
                            "asset": "BTC",
                            "risk_level": "high",
                            "risk_score": 84,
                            "allocation_pct": 72.0,
                            "next_best_action": "Voeg geen extra BTC exposure toe.",
                        }
                    ],
                    "concentration_warnings": [
                        {"reason": "BTC draagt 72.0% van de portfolio equity."}
                    ],
                    "risk_stacks": [
                        {"asset": "BTC", "reason": "BTC stapelt risico: hoge exposure, meerdere bots."}
                    ],
                    "ranked_conflicts": [
                        {"asset": "BTC", "reason": "BTC heeft meerdere live bots tegelijk."}
                    ],
                    "asset_priority": [
                        {"asset": "BTC", "risk_score": 84, "reason": "high_exposure"}
                    ],
                }
            }
        }
    }))
    monkeypatch.setattr(service, "_record_governance_event", AsyncMock())

    result = asyncio.run(service.build_portfolio_intelligence_response(30, "Heb ik te veel exposure?", {"symbol": "BTC"}))

    assert result["intent"] == "portfolio_intelligence"
    assert result["analysis"]["portfolio_impact"]["focus_asset"] == "BTC"
    assert "72.0%" in (result["analysis"]["exposure_delta"] or "")
    assert result["analysis"]["portfolio_blockers"][0] == "BTC heeft meerdere live bots tegelijk."


def test_build_portfolio_intelligence_response_uses_explicit_query_mix(monkeypatch):
    service = _service()
    monkeypatch.setattr(service, "build_portfolio_daily_coach_response", AsyncMock(return_value={
        "state": {"analysis": {"portfolio_risk": {}}}
    }))
    monkeypatch.setattr(service, "_record_governance_event", AsyncMock())

    result = asyncio.run(service.build_portfolio_intelligence_response(
        30,
        "Ik heb 70% BTC / 20% ETH / 10% cash, kan ik nog een BTC long openen?",
        {"page": "/dashboard", "symbol": "BTC"},
    ))

    assert result["analysis"]["portfolio_impact"]["status"] == "concentrated"
    assert "70%" in (result["analysis"]["concentration_warning"] or "")
    assert "BTC 70%" in (result["analysis"]["exposure_delta"] or "")
    assert "geen extra risico" in (result["analysis"]["portfolio_safe_alternative"] or "").lower()
    assert result["analysis"]["portfolio_impact"]["focus_asset"] == "BTC"
    assert "BTC" in (result["analysis"]["stacked_risk_warning"] or "")


def test_build_portfolio_intelligence_response_explicit_mix_overrides_live_asset_bias(monkeypatch):
    service = _service()
    monkeypatch.setattr(service, "build_portfolio_daily_coach_response", AsyncMock(return_value={
        "state": {
            "analysis": {
                "portfolio_risk": {
                    "status": "watch",
                    "message": "ETH exposure vraagt aandacht.",
                    "asset_risk": [
                        {"asset": "ETH", "risk_level": "high", "risk_score": 74, "allocation_pct": 62.0},
                    ],
                    "concentration_warnings": [{"reason": "ETH zit zwaar in je portfolio."}],
                    "risk_stacks": [{"asset": "ETH", "reason": "ETH stapelt risico."}],
                    "ranked_conflicts": [{"asset": "ETH", "reason": "ETH heeft meerdere live conflicts."}],
                }
            }
        }
    }))
    monkeypatch.setattr(service, "_record_governance_event", AsyncMock())

    result = asyncio.run(service.build_portfolio_intelligence_response(
        30,
        "Ik heb 70% BTC / 20% ETH / 10% cash en wil een nieuwe BTC long openen. Mag dat?",
        {"page": "/dashboard", "page_type": "dashboard", "symbol": "ETH"},
    ))

    assert result["analysis"]["portfolio_impact"]["focus_asset"] == "BTC"
    assert "BTC 70%" in (result["analysis"]["exposure_delta"] or "")
    assert "BTC" in (result["analysis"]["concentration_warning"] or "")
    assert result["analysis"]["portfolio_status"] == "concentrated"


def test_portfolio_intelligence_detection_stays_secondary_to_explicit_trade_review():
    service = _service()

    assert service.looks_like_portfolio_intelligence_request(
        "Zou jij dit doen?",
        {"page": "/setup", "page_type": "setup", "setup_id": 62, "strategy_id": 257, "symbol": "BTC"},
    ) is False
    assert service.looks_like_portfolio_intelligence_request(
        "Wat vind je van deze trade?",
        {"page": "/dashboard", "page_type": "dashboard", "symbol": "BTC"},
    ) is False
    assert service.looks_like_decision_review_request(
        "Zou jij dit doen?",
        {"page": "/setup", "page_type": "setup", "setup_id": 62, "strategy_id": 257, "symbol": "BTC"},
    ) is True
    assert service.looks_like_decision_review_request(
        "Wat vind je van deze trade?",
        {"page": "/dashboard", "page_type": "dashboard", "symbol": "BTC"},
    ) is True


def test_build_portfolio_intelligence_response_parses_asset_before_percent_mix(monkeypatch):
    service = _service()
    monkeypatch.setattr(service, "build_portfolio_daily_coach_response", AsyncMock(return_value={
        "state": {
            "analysis": {
                "portfolio_risk": {
                    "status": "watch",
                    "message": "ETH exposure vraagt aandacht.",
                    "asset_risk": [
                        {"asset": "ETH", "risk_level": "high", "risk_score": 74, "allocation_pct": 62.0},
                    ],
                    "concentration_warnings": [{"reason": "ETH zit zwaar in je portfolio."}],
                    "risk_stacks": [{"asset": "ETH", "reason": "ETH stapelt risico."}],
                    "ranked_conflicts": [{"asset": "ETH", "reason": "ETH heeft meerdere live conflicts."}],
                }
            }
        }
    }))
    monkeypatch.setattr(service, "_record_governance_event", AsyncMock())

    result = asyncio.run(service.build_portfolio_intelligence_response(
        30,
        "Portfolio: BTC 70% ETH 20% Cash 10%. Nieuwe trade: BTC Long. Mag dat?",
        {"page": "/dashboard", "page_type": "dashboard", "symbol": "ETH"},
    ))

    assert result["analysis"]["portfolio_impact"]["focus_asset"] == "BTC"
    assert "BTC 70%" in (result["analysis"]["exposure_delta"] or "")
    assert "BTC" in (result["analysis"]["concentration_warning"] or "")
    assert result["analysis"]["portfolio_status"] == "concentrated"


def test_decision_review_includes_portfolio_intelligence_contract():
    service = _service()

    result = asyncio.run(service.build_decision_review_response(30, "Kan ik deze trade openen met 3% risico?", {
        "page": "/dashboard",
        "page_type": "dashboard",
        "symbol": "BTC",
        "strategy_id": 257,
        "portfolio_intelligence": {
            "global": {
                "allocations_pct": {"BTC": 55.0, "Cash": 45.0},
            }
        },
    }))

    assert result["analysis"]["portfolio_impact"]["focus_asset"] == "BTC"
    assert result["analysis"]["portfolio_safe_alternative"]


def test_build_priority_engine_response_prefers_governance_weighted_risk_over_refresh(monkeypatch):
    service = FinnPlanService(db_session=object())
    monkeypatch.setattr(service, "build_portfolio_daily_coach_response", AsyncMock(return_value={"state": {"analysis": {"portfolio_risk": {}}}}))
    monkeypatch.setattr(service, "_build_mission_control_from_daily_analysis", lambda analysis: {
        "workqueue": [
            {
                "id": "refresh",
                "title": "Daily scores verversen",
                "type": "score_refresh",
                "priority": "high",
                "priority_rank": 10,
                "reason": "Data loopt achter",
            },
            {
                "id": "btc-risk",
                "title": "BTC exposure terugbrengen",
                "type": "portfolio_risk_stack",
                "priority": "medium",
                "priority_rank": 18,
                "reason": "BTC risico stapelt",
                "asset": "BTC",
            },
        ],
        "summary": {"workqueue_count": 2, "open_action_count": 1},
    })
    monkeypatch.setattr(service, "_fetch_recent_governance_events", AsyncMock(return_value=[
        {
            "type": "finn_plan_adherence_review",
            "symbol": "BTC",
            "description": "Je probeert een plan- of strategiegrens te overrulen.",
            "payload": {
                "asset": "BTC",
                "adherence_status": "forced_override",
                "threatened_rule": "Je probeert een plan- of strategiegrens te overrulen.",
            },
        }
    ]))
    monkeypatch.setattr(service, "_record_governance_event", AsyncMock())

    result = asyncio.run(service.build_priority_engine_response(1, "Wat is vandaag mijn hoogste prioriteit?", {"page": "mission_control"}))

    assert result["intent"] == "priority_engine"
    assert result["analysis"]["top_priorities"][0]["title"] == "BTC exposure terugbrengen"
    assert "overrulen" in str(result["analysis"]["why_now"]).lower()


def test_build_priority_engine_response_handles_generic_what_now_prompt(monkeypatch):
    service = FinnPlanService(db_session=object())
    monkeypatch.setattr(service, "build_portfolio_daily_coach_response", AsyncMock(return_value={"state": {"analysis": {"portfolio_risk": {}}}}))
    monkeypatch.setattr(service, "_build_mission_control_from_daily_analysis", lambda analysis: {
        "workqueue": [
            {
                "id": "review-btc",
                "title": "BTC bot review eerst doen",
                "type": "bot_decision",
                "priority": "high",
                "priority_rank": 9,
                "reason": "Open review beïnvloedt je live uitvoering.",
                "asset": "BTC",
            }
        ],
        "summary": {"workqueue_count": 1, "open_action_count": 1},
    })
    monkeypatch.setattr(service, "_fetch_recent_governance_events", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_record_governance_event", AsyncMock())

    result = asyncio.run(service.build_priority_engine_response(1, "Wat moet ik nu eerst doen?", {"page": "/dashboard"}))

    assert result["intent"] == "priority_engine"
    assert result["analysis"]["top_priorities"][0]["title"] == "BTC bot review eerst doen"
    assert "eerst" in result["response"].lower()


def test_build_priority_engine_response_handles_focus_prompt(monkeypatch):
    service = FinnPlanService(db_session=object())
    monkeypatch.setattr(service, "build_portfolio_daily_coach_response", AsyncMock(return_value={"state": {"analysis": {"portfolio_risk": {}}}}))
    monkeypatch.setattr(service, "_build_mission_control_from_daily_analysis", lambda analysis: {
        "workqueue": [
            {
                "id": "focus-btc",
                "title": "BTC exposure reviewen",
                "type": "portfolio_risk_stack",
                "priority": "high",
                "priority_rank": 5,
                "reason": "Concentratierisico vraagt nu aandacht.",
                "asset": "BTC",
            },
            {
                "id": "wait-eth",
                "title": "ETH setup laten rusten",
                "type": "score_refresh",
                "priority": "low",
                "priority_rank": 60,
                "reason": "Nog geen harde actienoodzaak.",
                "asset": "ETH",
            },
        ],
        "summary": {"workqueue_count": 2, "open_action_count": 1},
    })
    monkeypatch.setattr(service, "_fetch_recent_governance_events", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_record_governance_event", AsyncMock())

    result = asyncio.run(service.build_priority_engine_response(1, "Waar moet ik vandaag op focussen?", {"page": "/dashboard"}))

    assert result["intent"] == "priority_engine"
    assert result["analysis"]["top_priorities"][0]["title"] == "BTC exposure reviewen"
    assert "hierna reviewen" in result["response"].lower()


def test_build_priority_engine_response_handles_top3_and_do_not_do_prompts(monkeypatch):
    service = FinnPlanService(db_session=object())
    monkeypatch.setattr(service, "build_portfolio_daily_coach_response", AsyncMock(return_value={"state": {"analysis": {"portfolio_risk": {}}}}))
    monkeypatch.setattr(service, "_build_mission_control_from_daily_analysis", lambda analysis: {
        "workqueue": [
            {
                "id": "review-btc",
                "title": "BTC bot review eerst doen",
                "type": "bot_decision",
                "priority": "high",
                "priority_rank": 4,
                "reason": "Open review beïnvloedt je live uitvoering.",
                "asset": "BTC",
            },
            {
                "id": "skip-eth",
                "title": "ETH vandaag laten liggen",
                "type": "data_gap",
                "priority": "low",
                "priority_rank": 75,
                "reason": "Nog geen harde actienoodzaak.",
                "asset": "ETH",
            },
        ],
        "summary": {"workqueue_count": 2, "open_action_count": 1},
    })
    monkeypatch.setattr(service, "_fetch_recent_governance_events", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_record_governance_event", AsyncMock())

    top3 = asyncio.run(service.build_priority_engine_response(1, "Wat zijn vandaag mijn 3 belangrijkste acties?", {"page": "/dashboard"}))
    avoid = asyncio.run(service.build_priority_engine_response(1, "Wat moet ik juist niet doen?", {"page": "/dashboard"}))

    assert top3["intent"] == "priority_engine"
    assert avoid["intent"] == "priority_engine"
    assert "dit moet je vandaag juist niet doen" in avoid["response"].lower()


def test_build_priority_engine_response_varies_copy_by_question_focus(monkeypatch):
    service = FinnPlanService(db_session=object())
    monkeypatch.setattr(service, "build_portfolio_daily_coach_response", AsyncMock(return_value={"state": {"analysis": {"portfolio_risk": {}}}}))
    monkeypatch.setattr(service, "_build_mission_control_from_daily_analysis", lambda analysis: {
        "workqueue": [
            {
                "id": "review-btc",
                "title": "BTC bot review eerst doen",
                "type": "bot_decision",
                "priority": "high",
                "priority_rank": 4,
                "reason": "Open review beïnvloedt je live uitvoering.",
                "asset": "BTC",
            },
            {
                "id": "skip-eth",
                "title": "ETH vandaag laten liggen",
                "type": "data_gap",
                "priority": "low",
                "priority_rank": 75,
                "reason": "Nog geen harde actienoodzaak.",
                "asset": "ETH",
            },
        ],
        "summary": {"workqueue_count": 2, "open_action_count": 1},
    })
    monkeypatch.setattr(service, "_fetch_recent_governance_events", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_record_governance_event", AsyncMock())

    start = asyncio.run(service.build_priority_engine_response(1, "Waar moet ik mee beginnen?", {"page": "/dashboard"}))
    wait = asyncio.run(service.build_priority_engine_response(1, "Wat kan wachten?", {"page": "/dashboard"}))
    avoid = asyncio.run(service.build_priority_engine_response(1, "Wat moet ik juist niet doen?", {"page": "/dashboard"}))

    assert start["analysis"]["question_focus"] == "start_now"
    assert wait["analysis"]["question_focus"] == "wait"
    assert avoid["analysis"]["question_focus"] == "ignore_today"
    assert "begin hier nu mee" in start["response"].lower()
    assert "dit kan vandaag wachten" in wait["response"].lower()
    assert "dit moet je vandaag juist niet doen" in avoid["response"].lower()


def test_build_mission_control_explain_response_exposes_priority_engine_contract(monkeypatch):
    service = FinnPlanService(db_session=object())
    monkeypatch.setattr(service, "build_portfolio_daily_coach_response", AsyncMock(return_value={"state": {"analysis": {"portfolio_risk": {}}}}))
    monkeypatch.setattr(service, "_build_mission_control_from_daily_analysis", lambda analysis: {
        "workqueue": [
            {
                "id": "review",
                "title": "BTC live bots vragen review",
                "type": "portfolio_live_hotspot",
                "priority": "high",
                "priority_rank": 6,
                "reason": "Er staat live reviewdruk op BTC bots",
                "asset": "BTC",
            },
            {
                "id": "refresh",
                "title": "Daily scores verversen",
                "type": "score_refresh",
                "priority": "high",
                "priority_rank": 10,
                "reason": "Data loopt achter",
            },
        ],
        "summary": {"workqueue_count": 2, "open_action_count": 1},
    })
    monkeypatch.setattr(service, "_fetch_recent_governance_events", AsyncMock(return_value=[]))

    result = asyncio.run(service.build_mission_control_explain_response(1, "Wat zegt Mission Control?", {"page": "dashboard"}))

    assert result["analysis"]["priority_engine"]["top_priorities"][0]["title"] == "BTC live bots vragen review"
    assert result["analysis"]["mission_control_summary"]["top_3"][0]["title"] == "BTC live bots vragen review"


def test_build_portfolio_operating_system_response_exposes_control_plane(monkeypatch):
    service = FinnPlanService(db_session=object())
    monkeypatch.setattr(service, "build_portfolio_daily_coach_response", AsyncMock(return_value={
        "state": {
            "analysis": {
                "portfolio_risk": {
                    "status": "high_attention",
                    "message": "BTC exposure en live bots vragen aandacht.",
                    "top_asset": "BTC",
                    "top_reason": "BTC exposure is te dominant.",
                    "ignore_today_assets": [{"asset": "ETH", "reason": "setup blokkeert"}],
                    "live_bot_hotspots": [{"asset": "BTC"}],
                }
            }
        }
    }))
    monkeypatch.setattr(service, "_build_mission_control_from_daily_analysis", lambda analysis: {
        "summary": {"open_action_count": 3, "blocked_count": 1},
        "plan_health": [{"asset": "BTC", "status": "blocked"}],
        "portfolio_risk": analysis.get("portfolio_risk") or {},
        "workqueue": [
            {
                "id": "review",
                "title": "BTC live bots vragen review",
                "type": "portfolio_live_hotspot",
                "priority": "high",
                "priority_rank": 6,
                "reason": "Er staat live reviewdruk op BTC bots",
                "asset": "BTC",
            }
        ],
    })
    monkeypatch.setattr(service, "_get_recent_finn_activity", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_fetch_recent_governance_events", AsyncMock(return_value=[
        {
            "type": "finn_plan_adherence_review",
            "symbol": "BTC",
            "description": "Je probeert een plan- of strategiegrens te overrulen.",
            "payload": {
                "asset": "BTC",
                "adherence_status": "forced_override",
                "threatened_rule": "Je probeert een plan- of strategiegrens te overrulen.",
            },
        }
    ]))
    monkeypatch.setattr(service, "_record_governance_event", AsyncMock())

    result = asyncio.run(service.build_portfolio_operating_system_response(1, "Geef mijn portfolio operating system", {"page": "mission_control"}))

    assert result["intent"] == "portfolio_operating_system"
    assert result["analysis"]["operating_posture"] in {"risk_first", "review_first"}
    assert result["analysis"]["control_plane"]["headline"]
    assert result["analysis"]["subsystems"]["priority_engine"]["status"] == "active"
    assert result["analysis"]["portfolio_layer"]["top_asset"] == "BTC"


def test_behavioral_insight_waits_for_evidence_when_empty():
    service = _service()

    insight = service._build_behavioral_insight_from_activity([])
    message = service._behavioral_intelligence_message(insight)

    assert insight["status"] == "not_enough_data"
    assert insight["advice_only"] is True
    assert insight["signals"] == []
    assert "te weinig" in insight["coaching"]["primary_reflection"].lower()
    assert "alleen" in message.lower()


def test_weekly_reflection_waits_for_enough_evidence():
    service = _service()
    behavioral = service._build_behavioral_insight_from_activity([])

    reflection = service._build_weekly_reflection_from_behavioral(behavioral, [])
    message = service._weekly_reflection_message(reflection)

    assert reflection["status"] == "not_enough_data"
    assert reflection["period"] == "last_7_days"
    assert reflection["advice_only"] is True
    assert reflection["discipline_score"] is None
    assert reflection["behavioral_profile"]["type"] == "insufficient_history"
    assert "nog niet betrouwbaar" in message.lower()


def test_behavioral_insight_rewards_review_discipline():
    service = _service()
    skipped = service._mission_activity_item({
        "id": "finn-skip-1",
        "status": "executed",
        "created_at": _utc_now(),
        "payload": {
            "action": {"type": "skip_bot_decision"},
            "result": {"ok": True, "status": "skipped", "message": "Bot-decision overgeslagen."},
        },
    })
    snoozed = service._mission_activity_item({
        "id": "finn-snooze-1",
        "status": "executed",
        "created_at": _utc_now(),
        "payload": {
            "action": {"type": "snooze_mission_item"},
            "result": {"ok": True, "status": "snoozed", "message": "Later opnieuw bekijken."},
        },
    })

    insight = service._build_behavioral_insight_from_activity([skipped, snoozed])

    assert insight["status"] == "early_signal"
    assert any(signal["type"] == "disciplined_waiting" for signal in insight["signals"])
    assert insight["metrics"]["skipped_today"] == 1
    assert insight["metrics"]["snoozed_today"] == 1


def test_behavioral_insight_flags_decision_churn():
    service = _service()
    activity = [
        service._mission_activity_item({
            "id": f"finn-decision-{idx}",
            "status": "executed",
            "created_at": _utc_now(),
            "payload": {
                "action": {"type": "generate_bot_decision"},
                "result": {"ok": True, "status": "generated", "message": "Bot-decision gemaakt."},
            },
        })
        for idx in range(3)
    ]

    insight = service._build_behavioral_insight_from_activity(activity)

    assert insight["status"] == "attention"
    assert any(signal["type"] == "decision_churn" for signal in insight["signals"])
    assert insight["metrics"]["bot_decisions_generated"] == 3
    assert insight["metrics"]["bot_decisions_generated_7d"] == 3
    assert insight["behavioral_profile"]["type"] == "decision_heavy"
    assert insight["trend"]["period"] == "last_7_days_vs_previous_7_days"
    assert isinstance(insight["risk_flags"], list)
    assert isinstance(insight["habit_cards"], list)


def test_generate_bot_decision_event_marks_open_review_churn():
    service = _service()
    action = {
        "type": "generate_bot_decision",
        "payload": {
            "bot_id": 12,
            "asset": "BTC",
            "behavioral_context": {
                "decision_churn": {
                    "existing_decision_ids": [101, 102],
                    "existing_open_count": 2,
                }
            },
        },
    }

    event = service._behavioral_event_from_generate_bot_decision_action(action)

    assert event["type"] == "decision_churn"
    assert event["bot_id"] == 12
    assert event["existing_decision_ids"] == [101, 102]
    assert any("open review" in reason for reason in event["reasons"])


def test_weekly_reflection_names_explicit_decision_churn_event():
    service = _service()
    churn = service._mission_activity_item({
        "id": "finn-decision-churn-1",
        "status": "executed",
        "created_at": _utc_now(),
        "payload": {
            "action": {"type": "generate_bot_decision"},
            "result": {
                "ok": True,
                "status": "generated",
                "message": "Bot-decision gemaakt.",
                "behavioral_event": {
                    "type": "decision_churn",
                    "severity": "medium",
                    "existing_decision_ids": [101],
                    "reasons": ["nieuwe bot-decision gevraagd terwijl 1 open review nog niet afgehandeld was"],
                },
            },
        },
    })

    behavioral = service._build_behavioral_insight_from_activity([churn])
    reflection = service._build_weekly_reflection_from_behavioral(behavioral, [churn])
    message = service._weekly_reflection_message(reflection)

    assert behavioral["metrics"]["decision_churn_events_7d"] == 1
    assert "decision_churn" in behavioral["patterns"]
    assert reflection["metrics"]["decision_churn_events_7d"] == 1
    assert "Je vroeg meerdere keren nieuwe decisions aan terwijl er nog open review stond." in message


def test_behavioral_memory_report_uses_30_day_evidence_without_new_writes():
    service = _service()
    now = _utc_now()
    activity = [
        service._mission_activity_item({
            "id": "finn-memory-plan",
            "status": "executed",
            "created_at": now - timedelta(days=2),
            "payload": {
                "action": {"type": "create_plan"},
                "result": {"ok": True, "message": "Plan gemaakt."},
            },
        }),
        service._mission_activity_item({
            "id": "finn-memory-bot-update",
            "status": "executed",
            "created_at": now - timedelta(days=3),
            "payload": {
                "action": {"type": "bot_config_update"},
                "result": {
                    "ok": True,
                    "behavioral_event": {
                        "type": "plan_deviation_attempt",
                        "severity": "medium",
                        "reasons": ["budget verhoogd"],
                    },
                },
            },
        }),
        service._mission_activity_item({
            "id": "finn-memory-churn",
            "status": "executed",
            "created_at": now - timedelta(days=4),
            "payload": {
                "action": {"type": "generate_bot_decision"},
                "result": {
                    "ok": True,
                    "behavioral_event": {
                        "type": "decision_churn",
                        "severity": "medium",
                        "existing_decision_ids": [12],
                    },
                },
            },
        }),
        service._mission_activity_item({
            "id": "finn-memory-skip",
            "status": "executed",
            "created_at": now - timedelta(days=5),
            "payload": {
                "action": {"type": "skip_bot_decision"},
                "result": {"ok": True, "status": "skipped"},
            },
        }),
    ]
    behavioral = service._build_behavioral_insight_from_activity(activity)

    memory = service._build_behavioral_memory_report(activity, behavioral)
    message = service._behavioral_memory_message(memory)

    assert memory["status"] == "early_memory"
    assert memory["metrics"]["actions_30d"] == 4
    assert memory["metrics"]["decision_churn_events_30d"] == 1
    assert memory["metrics"]["plan_deviation_events_30d"] == 1
    assert memory["memory_policy"]["stores_new_memory"] is False
    assert any(card["type"] == "decision_churn" for card in memory["memory_cards"])
    assert memory["trend"]["period"] == "last_30_days_vs_previous_30_days"
    assert "behavioral_profile" in memory
    assert isinstance(memory["risk_flags"], list)
    assert isinstance(memory["habit_cards"], list)
    assert "Wat Finn voorzichtig mag onthouden" in message
    assert "Wat Finn nog niet mag concluderen" in message


def test_build_memory_v2_summary_extracts_plan_break_pattern():
    service = _service()
    activity = [
        {
            "type": "skip_bot_decision",
            "resolve_state": "skipped",
            "created_at": (_utc_now() - timedelta(days=5)).isoformat(),
        }
    ]
    governance_events = [
        {
            "type": "finn_plan_adherence_review",
            "symbol": "BTC",
            "description": "Je probeert een plan- of strategiegrens te overrulen.",
            "payload": {
                "asset": "BTC",
                "adherence_status": "forced_override",
                "threatened_rule": "Je probeert een plan- of strategiegrens te overrulen.",
            },
        },
        {
            "type": "finn_plan_adherence_review",
            "symbol": "ETH",
            "description": "Deze beslissing botst nu met je plan, risico of portfolio-kaders.",
            "payload": {
                "asset": "ETH",
                "adherence_status": "outside_plan",
                "threatened_rule": "Risico en sizing",
            },
        },
    ]

    memory_v2 = service._build_memory_v2_summary(activity, governance_events)

    assert memory_v2["memory_pattern"] == "plan_break_pattern"
    assert memory_v2["confidence_level"] in {"medium", "high"}
    assert memory_v2["supporting_evidence_count"] >= 2
    assert "override" in memory_v2["recommended_rule"].lower() or "override" in memory_v2["behavioral_cost"].lower()


def test_build_behavioral_memory_response_includes_memory_v2_contract(monkeypatch):
    service = _service()
    now = _utc_now()
    activity = [
        service._mission_activity_item({
            "id": "finn-memory-bot-update",
            "status": "executed",
            "created_at": now - timedelta(days=3),
            "payload": {
                "action": {"type": "bot_config_update"},
                "result": {
                    "ok": True,
                    "behavioral_event": {
                        "type": "plan_deviation_attempt",
                        "severity": "medium",
                        "reasons": ["budget verhoogd"],
                    },
                },
            },
        }),
        service._mission_activity_item({
            "id": "finn-memory-skip",
            "status": "executed",
            "created_at": now - timedelta(days=2),
            "payload": {
                "action": {"type": "skip_bot_decision"},
                "result": {"ok": True, "status": "skipped"},
            },
        }),
    ]

    async def _fake_activity(user_id, limit=180):
        return activity

    async def _fake_events(user_id, *, event_types, limit=80):
        return [
            {
                "type": "finn_plan_adherence_review",
                "symbol": "BTC",
                "description": "Je probeert een plan- of strategiegrens te overrulen.",
                "payload": {
                    "asset": "BTC",
                    "query": "Ik wil toch buiten mijn plan handelen",
                    "adherence_status": "forced_override",
                    "threatened_rule": "Je probeert een plan- of strategiegrens te overrulen.",
                },
            },
            {
                "type": "finn_outcome_tracking_summary",
                "symbol": "BTC",
                "description": "Het patroon eindigt vaker in remmen of niet-doen dan in overtuigende uitvoering.",
                "payload": {
                    "sample_size": 4,
                    "net_effect": "Het patroon eindigt vaker in remmen of niet-doen dan in overtuigende uitvoering.",
                },
            },
        ]

    monkeypatch.setattr(service, "_get_recent_finn_activity", _fake_activity)
    monkeypatch.setattr(service, "_fetch_recent_governance_events", _fake_events)
    monkeypatch.setattr(service, "_record_governance_event", AsyncMock())

    result = asyncio.run(service.build_behavioral_memory_response(30, "Wat onthoudt Finn van mijn trading discipline?", {}))

    assert result["intent"] == "behavioral_memory"
    assert result["analysis"]["memory_pattern"] in {"plan_break_pattern", "recovery_pattern"}
    assert result["analysis"]["time_window"] == "last_90_days"
    assert result["analysis"]["recommended_rule"]
    assert result["analysis"]["confidence_level"] in {"medium", "high"}
    assert "Memory V2 patroon" in result["response"]


def test_behavioral_memory_friction_slows_repeated_bot_decisions():
    service = _service()
    memory = {
        "memory_cards": [
            {
                "type": "decision_churn",
                "evidence": ["2 bot-decisions in 30 dagen", "1 expliciete decision-churn events"],
            }
        ]
    }

    friction = service._behavioral_memory_friction_from_report(memory, "generate_bot_decision")

    assert friction["type"] == "decision_churn"
    assert friction["source"] == "behavioral_memory"
    assert "review" in friction["safe_alternative"]


def test_behavioral_memory_ack_blocks_bot_decision_until_ack():
    service = _service()
    friction = {
        "type": "decision_churn",
        "severity": "medium",
        "message": "je recente memory laat decision-churn zien.",
        "source": "behavioral_memory",
        "evidence": ["1 expliciete decision-churn events"],
    }

    blocked = service._blocked_behavioral_memory_ack_response("BTC", 12, friction)

    assert blocked["can_confirm"] is False
    assert blocked["actions"] == []
    assert blocked["next_question"] == "behavioral_memory_ack"
    assert "behavioral_memory_ack" in blocked["missing_fields"]
    assert blocked["state"]["memory_friction"]["requires_ack"] is True
    assert service._is_behavioral_memory_ack("bewust doorgaan") is True


def test_weekly_reflection_summarizes_behavioral_patterns():
    service = _service()
    activity = [
        service._mission_activity_item({
            "id": f"finn-decision-{idx}",
            "status": "executed",
            "created_at": _utc_now() - timedelta(days=idx),
            "payload": {
                "action": {"type": "generate_bot_decision"},
                "result": {"ok": True, "status": "generated", "message": "Bot-decision gemaakt."},
            },
        })
        for idx in range(5)
    ]
    activity.append(service._mission_activity_item({
        "id": "finn-skip-1",
        "status": "executed",
        "created_at": _utc_now(),
        "payload": {
            "action": {"type": "skip_bot_decision"},
            "result": {"ok": True, "status": "skipped", "message": "Bot-decision overgeslagen."},
        },
    }))
    behavioral = service._build_behavioral_insight_from_activity(activity)

    reflection = service._build_weekly_reflection_from_behavioral(behavioral, activity)
    message = service._weekly_reflection_message(reflection)

    assert reflection["status"] == "attention"
    assert reflection["period"] == "last_7_days"
    assert reflection["discipline_score"] == 55
    assert "decision_churn" in reflection["patterns"]
    assert reflection["metrics"]["bot_decisions_generated_7d"] == 5
    assert reflection["strengths"]
    assert reflection["watchouts"]
    assert reflection["behavioral_balance_score"] is not None
    assert isinstance(reflection["risk_flags"], list)
    assert isinstance(reflection["habit_cards"], list)
    assert "Weekreflectie" in message


def test_weekly_reflection_splits_configuration_metrics():
    service = _service()
    activity = [
        service._mission_activity_item({
            "id": "finn-plan-1",
            "status": "executed",
            "created_at": _utc_now(),
            "payload": {
                "action": {"type": "create_plan"},
                "result": {"ok": True, "status": "created", "message": "Plan aangemaakt."},
            },
        }),
        service._mission_activity_item({
            "id": "finn-strategy-1",
            "status": "executed",
            "created_at": _utc_now(),
            "payload": {
                "action": {"type": "create_strategy"},
                "result": {"ok": True, "status": "created", "message": "Strategie opgeslagen."},
            },
        }),
        service._mission_activity_item({
            "id": "finn-bot-1",
            "status": "executed",
            "created_at": _utc_now(),
            "payload": {
                "action": {"type": "create_bot"},
                "result": {"ok": True, "status": "created", "message": "Bot opgeslagen."},
            },
        }),
        service._mission_activity_item({
            "id": "finn-indicator-1",
            "status": "executed",
            "created_at": _utc_now(),
            "payload": {
                "action": {"type": "configure_indicator"},
                "result": {"ok": True, "status": "saved", "message": "Indicator opgeslagen."},
            },
        }),
    ]
    behavioral = service._build_behavioral_insight_from_activity(activity)

    reflection = service._build_weekly_reflection_from_behavioral(behavioral, activity)
    message = service._weekly_reflection_message(reflection)

    assert reflection["metrics"]["plan_creates_7d"] == 1
    assert reflection["metrics"]["strategy_changes_7d"] == 1
    assert reflection["metrics"]["bot_changes_7d"] == 1
    assert reflection["metrics"]["indicator_changes_7d"] == 1
    assert reflection["metrics"]["configuration_changes_7d"] == 4
    assert "1 nieuwe plannen" in message


def test_weekly_reflection_includes_week_over_week_and_profile():
    service = _service()
    activity = [
        service._mission_activity_item({
            "id": f"finn-decision-now-{idx}",
            "status": "executed",
            "created_at": _utc_now() - timedelta(days=idx),
            "payload": {
                "action": {"type": "generate_bot_decision"},
                "result": {"ok": True, "status": "generated", "message": "Bot-decision gemaakt."},
            },
        })
        for idx in range(5)
    ]
    activity.append(service._mission_activity_item({
        "id": "finn-decision-prev",
        "status": "executed",
        "created_at": _utc_now() - timedelta(days=9),
        "payload": {
            "action": {"type": "generate_bot_decision"},
            "result": {"ok": True, "status": "generated", "message": "Bot-decision gemaakt."},
        },
    }))
    behavioral = service._build_behavioral_insight_from_activity(activity)

    reflection = service._build_weekly_reflection_from_behavioral(behavioral, activity)
    message = service._weekly_reflection_message(reflection)

    assert reflection["behavioral_profile"]["type"] == "decision_heavy"
    assert reflection["week_over_week"]["period"] == "last_7_days_vs_previous_7_days"
    assert reflection["week_over_week"]["comparisons"][1]["current"] == 5
    assert reflection["week_over_week"]["comparisons"][1]["previous"] == 1
    assert reflection["metrics"]["previous_bot_decisions_generated_7d"] == 1
    assert reflection["trend"]["period"] == "last_7_days_vs_previous_7_days"
    assert "Profiel deze week" in message
    assert "Vergeleken met vorige week" in message


def test_behavioral_profile_can_mark_overtrading_risk():
    service = _service()
    activity = [
        service._mission_activity_item({
            "id": f"finn-overtrade-{idx}",
            "status": "executed",
            "created_at": _utc_now() - timedelta(hours=idx),
            "payload": {
                "action": {"type": "generate_bot_decision"},
                "result": {
                    "ok": True,
                    "status": "generated",
                    "behavioral_event": {
                        "type": "decision_churn",
                        "severity": "medium",
                    } if idx == 0 else None,
                },
            },
        })
        for idx in range(6)
    ]
    activity.extend([
        service._mission_activity_item({
            "id": "finn-overtrade-paper",
            "status": "executed",
            "created_at": _utc_now(),
            "payload": {
                "action": {"type": "paper_execute_bot_decision"},
                "result": {"ok": True, "status": "executed"},
            },
        }),
        service._mission_activity_item({
            "id": "finn-overtrade-live",
            "status": "executed",
            "created_at": _utc_now(),
            "payload": {
                "action": {"type": "live_preflight_bot_decision"},
                "result": {"ok": True, "status": "ok"},
            },
        }),
    ])

    behavioral = service._build_behavioral_insight_from_activity(activity)

    assert behavioral["behavioral_profile"]["type"] == "overtrading_risk"
    assert any(flag["id"] == "overtrading_pressure" for flag in behavioral["risk_flags"])


def test_weekly_reflection_names_waiting_behavior():
    service = _service()
    activity = [
        service._mission_activity_item({
            "id": "finn-skip-1",
            "status": "executed",
            "created_at": _utc_now(),
            "payload": {
                "action": {"type": "skip_bot_decision"},
                "result": {"ok": True, "status": "skipped", "message": "Bot-decision overgeslagen."},
            },
        }),
        service._mission_activity_item({
            "id": "finn-snooze-1",
            "status": "executed",
            "created_at": _utc_now(),
            "payload": {
                "action": {"type": "snooze_mission_item"},
                "result": {"ok": True, "status": "snoozed", "message": "Later opnieuw bekijken."},
            },
        }),
    ]
    behavioral = service._build_behavioral_insight_from_activity(activity)

    reflection = service._build_weekly_reflection_from_behavioral(behavioral, activity)

    assert reflection["metrics"]["skipped_7d"] == 1
    assert reflection["metrics"]["snoozed_7d"] == 1
    assert any("bewust niet doorgezet" in item for item in reflection["strengths"])
    assert any("uitgesteld" in item for item in reflection["strengths"])


def test_weekly_reflection_includes_agent_rhythm_without_performance_claims():
    service = _service()
    now = _utc_now().isoformat()
    activity = [
        {
            "type": "agent_controller_handoff",
            "status": "executed",
            "resolve_state": "resolved",
            "asset": "BTC",
            "created_at": now,
            "agent_accountability": {
                "dominant_agent": "risk_agent",
                "dominant_label": "Risk Agent",
                "primary_action_label": "Portfolio-risico bekijken",
            },
        },
        {
            "type": "agent_controller_handoff",
            "status": "executed",
            "resolve_state": "monitor_today",
            "asset": "ETH",
            "created_at": now,
            "agent_accountability": {
                "dominant_agent": "execution_agent",
                "dominant_label": "Execution Agent",
                "primary_action_label": "Live preflight bekijken",
            },
        },
    ]
    behavioral = service._build_behavioral_insight_from_activity(activity)

    reflection = service._build_weekly_reflection_from_behavioral(behavioral, activity)
    message = service._weekly_reflection_message(reflection)

    assert reflection["agent_learning"]["status"] == "ready"
    assert reflection["agent_learning"]["policy"]["claims_performance"] is False
    assert reflection["agent_rhythm"]["status"] == "ready"
    assert reflection["agent_rhythm"]["policy"]["uses_pnl"] is False
    assert reflection["operating_rules"]["policy"]["coaching_only"] is True
    assert any(rule["id"] == "risk_agent_first" for rule in reflection["operating_rules"]["rules"])
    assert any("Risk Agent" in item for item in reflection["agent_rhythm"]["followed_patterns"])
    assert any("Execution Agent" in item for item in reflection["agent_rhythm"]["friction_patterns"])
    assert "Agent-ritme:" in message
    assert "Personal operating rules:" in message


def test_behavioral_event_from_bot_update_detects_budget_and_live_pressure():
    service = _service()
    draft = {
        "operation": "update",
        "asset": "BTC",
        "bot_id": 42,
        "strategy_id": 11,
        "changes": [
            {"field": "budget_total_eur", "from": 100, "to": 500},
            {"field": "is_live", "from": False, "to": True},
        ],
    }

    event = service._behavioral_event_from_bot_draft(draft)

    assert event["type"] == "plan_deviation_attempt"
    assert event["bot_id"] == 42
    assert any("budget_total_eur verhoogd" in reason for reason in event["reasons"])
    assert any("live" in reason for reason in event["reasons"])


def test_behavioral_event_from_bot_update_includes_blocked_setup_context():
    service = _service()
    draft = {
        "operation": "update",
        "asset": "BTC",
        "bot_id": 42,
        "strategy_id": 11,
        "changes": [
            {"field": "budget_daily_limit_eur", "from": 100, "to": 200},
        ],
    }
    context = {
        "status": "blocked",
        "asset": "BTC",
        "setup_id": 7,
        "has_scores": True,
        "match_percentage": 33.3,
        "reasons": ["macro score 10 buiten [30, 70]"],
    }

    event = service._behavioral_event_from_bot_draft(draft, context)

    assert event["type"] == "plan_deviation_attempt"
    assert event["severity"] == "high"
    assert event["context"]["status"] == "blocked"
    assert event["context"]["setup_id"] == 7
    assert "actie terwijl setup-score blokkeert" in event["reasons"]
    assert "macro score 10 buiten [30, 70]" in event["reasons"]


def test_behavioral_event_from_strategy_update_detects_sensitive_changes():
    service = _service()
    draft = {
        "operation": "update",
        "asset": "ETH",
        "setup_id": 7,
        "strategy_id": 12,
        "changes": [
            {"field": "base_amount_eur", "from": 100, "to": 250},
            {"field": "targets", "from": [3200], "to": [3600]},
        ],
    }

    event = service._behavioral_event_from_strategy_draft(draft)

    assert event["type"] == "strategy_change_pressure"
    assert event["strategy_id"] == 12
    assert "base_amount_eur gewijzigd" in event["reasons"]


def test_behavioral_event_from_strategy_update_tracks_data_missing_context():
    service = _service()
    draft = {
        "operation": "update",
        "asset": "ETH",
        "setup_id": 7,
        "strategy_id": 12,
        "changes": [
            {"field": "base_amount_eur", "from": 100, "to": 250},
        ],
    }
    context = {
        "status": "data_missing",
        "asset": "ETH",
        "setup_id": 7,
        "has_scores": False,
        "match_percentage": 0,
        "reasons": ["macro score of range ontbreekt"],
    }

    event = service._behavioral_event_from_strategy_draft(draft, context)

    assert event["type"] == "strategy_change_pressure"
    assert event["context"]["status"] == "data_missing"
    assert "actie terwijl scoredata of setup-check incompleet is" in event["reasons"]


def test_strategy_plan_deviation_requires_conscious_override_before_confirm():
    service = _service()
    draft = {
        "draft_kind": "strategy",
        "operation": "update",
        "setup_id": 7,
        "strategy_id": 12,
        "setup_type": "dca",
        "asset": "BTC",
        "timeframe": "1W",
        "strategy": {"base_amount_eur": 150},
        "plan_deviation": {
            "requires_ack": True,
            "acknowledged": False,
            "message": "Je wijzigt nu BTC terwijl je setup blokkeert.",
            "reasons": ["macro score 10 buiten [30, 70]"],
        },
    }

    validation = service._validate_strategy_draft(draft)
    message = service._build_strategy_message(draft, validation)

    assert validation["can_confirm"] is False
    assert validation["next_question"] == "plan_deviation_ack"
    assert "niet aan je eigen plan" in message
    assert "bewuste override" in message


def test_strategy_plan_deviation_ack_restores_confirmability():
    service = _service()
    draft = {
        "draft_kind": "strategy",
        "operation": "update",
        "setup_id": 7,
        "strategy_id": 12,
        "setup_type": "dca",
        "asset": "BTC",
        "timeframe": "1W",
        "strategy": {"base_amount_eur": 150},
        "plan_deviation_ack": True,
        "plan_deviation": {
            "requires_ack": True,
            "acknowledged": True,
            "message": "Je wijzigt nu BTC terwijl je setup blokkeert.",
            "reasons": ["macro score 10 buiten [30, 70]"],
        },
    }

    validation = service._validate_strategy_draft(draft)
    message = service._build_strategy_message(draft, validation)

    assert validation["can_confirm"] is True
    assert "Plan-afwijking: ja" in message
    assert "Override bevestigd: ja" in message


def test_bot_plan_deviation_requires_override_before_confirm():
    service = _service()
    draft = {
        "draft_kind": "bot",
        "operation": "update",
        "bot_id": 42,
        "strategy_id": 11,
        "asset": "BTC",
        "bot": {
            "name": "Finn BTC Auto Bot",
            "mode": "auto",
            "risk_profile": "balanced",
            "cadence": "daily",
            "is_live": False,
            "budget_total_eur": 1000,
            "budget_daily_limit_eur": 100,
            "budget_min_order_eur": 10,
            "budget_max_order_eur": 50,
        },
        "existing_bot_snapshot": {
            "name": "Finn BTC Auto Bot",
            "mode": "auto",
            "risk_profile": "balanced",
            "cadence": "daily",
            "is_live": False,
            "budget_total_eur": 500,
            "budget_daily_limit_eur": 100,
            "budget_min_order_eur": 10,
            "budget_max_order_eur": 50,
        },
        "changes": [{"field": "budget_total_eur", "from": 500, "to": 1000}],
        "plan_deviation": {
            "requires_ack": True,
            "acknowledged": False,
            "message": "Je wijzigt nu BTC terwijl je setup blokkeert.",
            "reasons": ["technical score 10 buiten [40, 80]"],
        },
    }

    validation = service._validate_bot_draft(draft)
    message = service._build_bot_message(draft, validation)

    assert validation["can_confirm"] is False
    assert validation["next_question"] == "plan_deviation_ack"
    assert "niet aan je eigen plan" in message


def test_behavioral_insight_uses_seven_day_patterns():
    service = _service()
    activity = [
        service._mission_activity_item({
            "id": f"finn-old-decision-{idx}",
            "status": "executed",
            "created_at": _utc_now() - timedelta(days=idx + 1),
            "payload": {
                "action": {"type": "generate_bot_decision"},
                "result": {"ok": True, "status": "generated", "message": "Bot-decision gemaakt."},
            },
        })
        for idx in range(5)
    ]

    insight = service._build_behavioral_insight_from_activity(activity)

    assert insight["status"] == "attention"
    assert insight["metrics"]["bot_decisions_generated"] == 0
    assert insight["metrics"]["bot_decisions_generated_7d"] == 5
    assert "decision_churn" in insight["patterns"]


def test_behavioral_event_from_risky_execution_is_auditable():
    service = _service()
    action = service._bot_execution_action(
        "paper_execute_bot_decision",
        {
            "decision_id": 22,
            "bot_id": 9,
            "asset": "BTC",
            "action": "buy",
            "risk_level": "high",
            "confidence": 0.48,
            "guardrail_reason": "Daglimiet overschreden",
            "setup_match": {"status": "partial", "score": 62},
        },
        is_live=False,
    )
    event = service._behavioral_event_from_execution_action(action, result_status="executed")

    assert event["type"] == "plan_deviation_attempt"
    assert event["decision_id"] == 22
    assert any("confidence" in reason for reason in event["reasons"])
    assert any("setup match" in reason for reason in event["reasons"])
    assert any("guardrail" in reason for reason in event["reasons"])


def test_behavioral_insight_counts_override_events():
    service = _service()
    risky = service._mission_activity_item({
        "id": "finn-risky-paper-1",
        "status": "executed",
        "created_at": _utc_now(),
        "payload": {
            "action": {"type": "paper_execute_bot_decision"},
            "result": {
                "ok": True,
                "status": "executed",
                "behavioral_event": {
                    "type": "plan_deviation_attempt",
                    "severity": "medium",
                    "reasons": ["confidence 0.48 onder 0.55"],
                },
            },
        },
    })

    insight = service._build_behavioral_insight_from_activity([risky])

    assert insight["metrics"]["possible_overrides_7d"] == 1
    assert insight["metrics"]["plan_deviation_events_7d"] == 1
    assert insight["behavioral_events"][0]["type"] == "plan_deviation_attempt"
    assert any(signal["type"] == "execution_friction" for signal in insight["signals"])


def test_behavioral_insight_counts_direct_bot_risk_update_events():
    service = _service()
    item = service._mission_activity_item({
        "id": "finn-risk-abc123",
        "status": "executed",
        "created_at": _utc_now(),
        "payload": {
            "action": {"type": "bot_config_update"},
            "result": {
                "ok": True,
                "behavioral_event": {
                    "type": "plan_deviation_attempt",
                    "severity": "medium",
                    "reasons": ["budget_total_eur verhoogd van 0 naar 1000"],
                },
            },
        },
    })

    insight = service._build_behavioral_insight_from_activity([item])

    assert item["label"] == "Bot risk-wijziging bevestigd"
    assert insight["metrics"]["bot_changes_7d"] == 1
    assert insight["metrics"]["possible_overrides_7d"] == 1
    assert insight["metrics"]["plan_deviation_events_7d"] == 1


def test_bot_decision_review_request_detection():
    service = _service()

    assert service.looks_like_bot_decision_review_request("Leg bot-decision 22 uit") is True
    assert service.looks_like_bot_decision_review_request("Waarom dit bot voorstel?") is True
    assert service.looks_like_bot_decision_review_request("Maak bot-decision voor BTC") is False
    assert service.looks_like_bot_execution_decision_request("Sla bot-decision 22 over") is True
    assert service.looks_like_bot_execution_decision_request("Voer bot-decision 22 paper uit") is True
    assert service.looks_like_bot_execution_decision_request("Doe live preflight voor bot-decision 22") is True
    assert service.looks_like_bot_execution_decision_request("Leg bot-decision 22 uit") is False
    assert service._bot_execution_choice("Sla bot-decision 22 over") == "skip"
    assert service._bot_execution_choice("Voer bot-decision 22 paper uit") == "paper_execute"
    assert service._bot_execution_choice("Doe live preflight voor bot-decision 22") == "live_preflight"


def test_bot_execution_actions_are_confirmable_and_guarded():
    service = _service()
    review = {
        "decision_id": 22,
        "bot_id": 9,
        "asset": "BTC",
    }

    skip_action = service._bot_execution_action("skip_bot_decision", review, is_live=False)
    paper_action = service._bot_execution_action("paper_execute_bot_decision", review, is_live=False)
    live_action = service._bot_execution_action("live_preflight_bot_decision", review, is_live=True)

    assert skip_action["requires_confirmation"] is True
    assert paper_action["payload"]["decision_id"] == 22
    assert paper_action["guardrails"]["can_execute_without_user"] is False
    assert live_action["guardrails"]["live_preflight_only"] is True
    assert live_action["risk_level"] == "high"


def test_skip_bot_decision_action_returns_operator_resolution(monkeypatch):
    service = _service()

    class BotSvc:
        def __init__(self, session):
            self.session = session

        async def skip_bot_today(self, bot_id, _, user_id):
            return {"ok": True}

    monkeypatch.setattr("backend.services.finn_plan_service.BotService", BotSvc)
    service._try_create_pending_action = AsyncMock(return_value=True)
    service._upsert_action_audit = AsyncMock()
    service._read_bot_decision_status = AsyncMock(return_value="skipped")

    result = asyncio.run(service._execute_skip_bot_decision_action(30, {
        "id": "skip-bot-decision-108032",
        "type": "skip_bot_decision",
        "payload": {"bot_id": 17, "decision_id": 108032},
    }))

    assert result["verified"]["bot_decision_skipped"] is True
    assert result["operator_resolution"]["status"] == "skipped"
    assert "bewust" in result["operator_resolution"]["summary"].lower()
    assert result["action_follow_through"] == result["operator_resolution"]
    assert result["state"]["analysis"]["operator_resolution"] == result["operator_resolution"]
    assert result["state"]["analysis"]["action_follow_through"] == result["operator_resolution"]


def test_legacy_skip_result_gets_follow_through_hydrated():
    service = _service()

    hydrated = service._hydrate_legacy_follow_through_result(
        {
            "type": "skip_bot_decision",
            "payload": {"bot_id": 17, "decision_id": 121110},
        },
        {
            "ok": True,
            "message": "Bot-decision #121110 is overgeslagen.",
            "decision_id": 121110,
            "verified": {"bot_decision_skipped": True},
        },
    )

    assert hydrated["operator_resolution"]["status"] == "skipped"
    assert hydrated["action_follow_through"] == hydrated["operator_resolution"]
    assert hydrated["state"]["analysis"]["operator_resolution"] == hydrated["operator_resolution"]
    assert hydrated["state"]["analysis"]["action_follow_through"] == hydrated["operator_resolution"]


def test_execute_issued_action_replays_legacy_skip_result_with_follow_through():
    service = FinnPlanService(db_session=object())
    service._get_pending_action_row = AsyncMock(return_value={
        "status": "executed",
        "payload": {
            "action": {
                "type": "skip_bot_decision",
                "payload": {"bot_id": 17, "decision_id": 121110},
            },
            "result": {
                "ok": True,
                "message": "Bot-decision #121110 is overgeslagen.",
                "decision_id": 121110,
                "verified": {"bot_decision_skipped": True},
            },
        },
    })

    result = asyncio.run(service.execute_issued_action(30, "finn-maint-skip-legacy-u30"))

    assert result["replayed"] is True
    assert result["operator_resolution"]["status"] == "skipped"
    assert result["action_follow_through"] == result["operator_resolution"]
    assert result["state"]["analysis"]["operator_resolution"] == result["operator_resolution"]
    assert result["state"]["analysis"]["action_follow_through"] == result["operator_resolution"]


def test_skip_bot_decision_response_exposes_follow_through_preview(monkeypatch):
    service = _service()

    review = {
        "id": 121110,
        "bot_id": 17,
        "symbol": "BTC",
        "status": "proposed",
        "action": "buy",
        "risk_level": "medium",
        "confidence": 0.64,
        "guardrail_reason": None,
        "guardrails_result": {"ok": True},
        "setup_match": {"status": "aligned", "score": 82},
    }

    async def find_decision(user_id, query, context):
        return review

    monkeypatch.setattr(service, "_find_bot_decision_for_query", find_decision)

    result = asyncio.run(service.build_bot_execution_decision_response(30, "Sla bot-decision 121110 over"))

    assert result["can_confirm"] is True
    assert result["actions"][0]["type"] == "skip_bot_decision"
    preview = result["state"]["analysis"]["operator_resolution"]
    assert preview["status"] == "preview"
    assert "overslaat" in preview["title"].lower()
    assert len(preview["what_changed"]) == 2
    assert result["state"]["analysis"]["action_follow_through"] == preview


def test_execute_issued_action_accepts_legacy_finn_id_without_user_suffix():
    service = FinnPlanService(db_session=object())
    service._get_pending_action_row = AsyncMock(side_effect=[
        None,
        {
            "payload": {
                "action": {
                    "id": "finn-maint-resolve-blocked-plan",
                    "type": "resolve_mission_item",
                    "payload": {"source_item_id": "blocked_plan:BTC:61", "resolution": "monitor_today"},
                }
            },
            "status": "pending",
        },
    ])
    service.execute_action = AsyncMock(return_value={"ok": True, "verified": {"mission_item_resolved": True}})

    result = asyncio.run(service.execute_issued_action(30, "finn-maint-resolve-blocked-plan"))

    assert result["ok"] is True
    assert service._get_pending_action_row.await_args_list[1].args == (30, "finn-maint-resolve-blocked-plan-u30")
    service.execute_action.assert_awaited_once()


def test_live_preflight_blocks_on_stale_decision_context(monkeypatch):
    service = _service()

    class Repo:
        async def get_bot_config(self, user_id, bot_id):
            return {"id": bot_id, "is_live": True}

    class BotSvc:
        def __init__(self, session):
            self.session = session
            self.repository = Repo()

        async def require_fresh_live_decision_context(self, user_id, bot_id):
            raise HTTPException(409, {
                "code": "LIVE_EXECUTION_STALE_DATA",
                "message": "Live execution vereist een recente bot-decision context.",
                "freshness": {"status": "stale", "age_minutes": 90},
            })

    class ExchangeRepo:
        def __init__(self, session):
            self.session = session

        async def get_active_keys(self, user_id):
            return [{"id": 1}]

    monkeypatch.setattr("backend.services.finn_plan_service.BotService", BotSvc)
    monkeypatch.setattr("backend.services.finn_plan_service.ExchangeRepository", ExchangeRepo)

    action = service._bot_execution_action(
        "live_preflight_bot_decision",
        {"decision_id": 22, "bot_id": 9, "asset": "BTC"},
        is_live=True,
    )

    result = asyncio.run(service._execute_live_preflight_bot_decision_action(1, action))

    assert result["ok"] is True
    assert result["verified"]["live_preflight"] is False
    assert result["verified"]["live_bot"] is True
    assert result["verified"]["exchange_keys"] is True
    assert result["verified"]["fresh_decision_context"] is False
    assert result["stale_data_block"]["code"] == "LIVE_EXECUTION_STALE_DATA"
    assert result["freshness"]["status"] == "stale"


def test_resolve_mission_item_action_returns_operator_resolution():
    service = _service()
    service._try_create_pending_action = AsyncMock(return_value=True)
    service._upsert_action_audit = AsyncMock()

    result = asyncio.run(service._execute_resolve_mission_item_action(30, {
        "id": "resolve-blocked-plan",
        "type": "resolve_mission_item",
        "payload": {
            "source_item_id": "blocked_plan:BTC:12",
            "resolution": "monitor_today",
            "asset": "BTC",
            "day_key": _utc_now().date().isoformat(),
        },
    }))

    assert result["verified"]["mission_item_resolved"] is True
    assert result["operator_resolution"]["status"] == "monitor_today"
    assert "werkqueue" in result["operator_resolution"]["what_changed"][1].lower()
    assert result["action_follow_through"] == result["operator_resolution"]
    assert result["state"]["analysis"]["operator_resolution"] == result["operator_resolution"]
    assert result["state"]["analysis"]["action_follow_through"] == result["operator_resolution"]


def test_bot_decision_memory_friction_blocks_even_with_open_reviews(monkeypatch):
    service = FinnPlanService(db_session=object())

    class BotSvc:
        def __init__(self, session):
            self.session = session

        async def get_bot_configs(self, user_id):
            return [{"id": 9, "name": "BTC Paper Bot", "symbol": "BTC"}]

    async def open_reviews(user_id, asset, bot_id):
        return [{"decision_id": 22, "bot_id": bot_id, "review_status": "needs_review"}]

    async def memory_friction(user_id, action_type):
        return {
            "type": "decision_churn",
            "message": "je recente memory laat decision-churn zien.",
            "evidence": ["2 bot-decisions in 30 dagen"],
        }

    monkeypatch.setattr("backend.services.finn_plan_service.BotService", BotSvc)
    monkeypatch.setattr(service, "_open_bot_reviews_for_bot", open_reviews)
    monkeypatch.setattr(service, "_behavioral_memory_friction_for_action", memory_friction)

    result = asyncio.run(service.build_bot_decision_response(1, "Maak bot-decision voor BTC"))

    assert result["can_confirm"] is False
    assert result["actions"] == []
    assert result["missing_fields"] == ["behavioral_memory_ack"]
    assert result["next_question"] == "behavioral_memory_ack"
    assert result["state"]["pending_behavioral_memory_friction"]["requires_ack"] is True


def test_daily_coach_analysis_waits_when_setup_has_blockers():
    service = _service()
    setup_analysis = service._evaluate_setup_row(
        {
            "id": 12,
            "name": "BTC Plan",
            "setup_type": "dca",
            "timeframe": "1W",
            "score": 55,
            "is_active": False,
            "min_macro_score": 30,
            "max_macro_score": 70,
            "min_technical_score": 40,
            "max_technical_score": 60,
            "min_market_score": 20,
            "max_market_score": 80,
        },
        {"macro_score": 50, "technical_score": 90, "market_score": 40},
    )

    analysis = service._build_daily_coach_analysis(
        asset="BTC",
        daily_scores={"macro_score": 50, "technical_score": 90, "market_score": 40},
        setup_analysis=setup_analysis,
        active_strategy={"active": False},
        bot_today={"decisions": []},
        indicator_analysis={
            "warnings": ["technical: zwakke indicatoren: rsi"],
            "suggestions": ["Je technical-laag is dun; voeg MA200 toe."],
            "categories": {},
        },
    )

    assert analysis["stance"] == "wait_for_plan"
    assert analysis["setup_active"] is False
    assert analysis["blockers"][0]["category"] == "technical"
    assert any(verdict["agent"] == "technical_agent" and verdict["status"] == "blocks_plan" for verdict in analysis["agent_verdicts"])
    assert any(verdict["agent"] == "risk_agent" and verdict["status"] == "blocked" for verdict in analysis["agent_verdicts"])
    assert any(verdict["agent"] == "execution_agent" and verdict["status"] == "no_decision" for verdict in analysis["agent_verdicts"])
    assert "Niet forceren" in analysis["suggested_actions"][0]


def test_daily_coach_message_is_advice_only_and_mentions_bot_decisions():
    service = _service()
    analysis = {
        "asset": "BTC",
        "stance": "plan_is_active",
        "has_scores": True,
        "setup": {"id": 12, "name": "BTC Plan"},
        "setup_match_percentage": 100.0,
        "blockers": [],
        "active_strategy": {"active": True, "strategy": {"id": 44, "name": "Weekly DCA"}},
        "bot_today": {
            "decision_count": 1,
            "decisions": [{"bot_id": 8, "action": "buy", "status": "pending"}],
        },
        "indicator_summary": {"warnings": []},
        "agent_verdicts": [
            {"label": "Risk Agent", "status": "ready", "reason": "Geen setup-blocker gevonden."}
        ],
        "suggested_actions": ["Volg je plan."],
    }

    message = service._daily_coach_message(analysis)

    assert "je plan mag vandaag actief zijn" in message
    assert "Bot vandaag: 1 beslissing" in message
    assert "Agent-verdicts:" in message
    assert "Ik voer niets automatisch uit" in message


def test_assistant_insight_from_daily_coach_is_structured_morning_brief():
    assistant = AiAssistantService(
        score_repo=None,
        setup_repo=None,
        report_repo=None,
        bot_repo=None,
        user_repo=None,
        market_data_repo=None,
        strategy_repo=None,
        state_repo=None,
        ai_gateway=None,
    )

    insight = assistant._assistant_insight_from_daily_coach(
        symbol="BTC",
        page_type="FINN",
        daily_response={"response": "Daily coach text"},
        analysis={
            "asset": "BTC",
            "stance": "wait_for_plan",
            "has_scores": True,
            "setup": {"id": 12, "name": "BTC Plan"},
            "setup_match_percentage": 0.0,
            "blockers": [{"category": "macro", "score": 10.0, "range": [30.0, 70.0]}],
            "bot_today": {"decision_count": 0},
            "indicator_summary": {"warnings": ["macro: geen actieve indicator-data gevonden"]},
            "suggested_actions": ["Niet forceren"],
        },
    )

    assert insight["context_detected"]["flow"] == "daily_coach"
    assert insight["context_detected"]["posture"] == "Defensive Posture"
    assert "geblokkeerd" in insight["market_insight"]["conclusion"]
    assert "macro 10.0 buiten [30.0, 70.0]" in insight["market_insight"]["why"]
    assert insight["suggested_actions"] == ["Niet forceren"]
