import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

from fastapi import HTTPException

from backend.services.finn_plan_service import FinnPlanService
from backend.services.finn_plan_service import _utc_now
from backend.services.finn_plan_service import empty_indicator_config_draft
from backend.services.ai_action_engine import _utc_db_timestamp
from backend.services.ai_assistant_service import AiAssistantService
from backend.services.strategy_service import StrategyService
from backend.schemas.assistant_schema import AssistantContextSchema


def _service():
    return FinnPlanService(db_session=None)


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


def test_finn_report_request_is_separate_from_trading_report():
    service = _service()

    assert service.looks_like_finn_report_request("Geef mijn Finn rapport van vandaag")
    assert service.looks_like_finn_report_request("Wat heeft Finn vandaag geblokkeerd?")
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
    assert any(verdict["agent"] == "risk_agent" for verdict in report["agent_verdicts"])
    assert "los van je dagelijkse trading report" in message
    assert "Agent-verdicts:" in message


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
    assert any(verdict["agent"] == "execution_agent" for verdict in report["agent_verdicts"])
    assert any("live orders geblokkeerd" in item.lower() for item in report["day_close"]["tomorrow_focus"])
    assert "Dagafsluiting:" in message
    assert "Meenemen naar morgen:" in message
    assert "los van je dagelijkse trading report" in message


def test_finn_report_response_exposes_top_level_state_contract(monkeypatch):
    async def activity(user_id, limit=200):
        return []

    service = _service()
    monkeypatch.setattr(service, "_get_recent_finn_activity", activity)

    result = asyncio.run(service.build_finn_report_response(1, "Geef mijn Finn rapport van vandaag"))

    assert result["intent"] == "finn_report"
    assert result["state"]["report_type"] == "finn_reflection_report"
    assert result["state"]["report_family"] == "finn_reports"
    assert result["state"]["separate_from"] == "daily_trading_report"
    assert result["state"]["source"]["primary"] == "ai_pending_actions"
    assert result["state"]["source"] == result["state"]["analysis"]["source"]


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
    assert "Technical Agent: blocks_plan" in message


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
    assert service.looks_like_daily_coach_request("Welke bots en plannen stapelen risico?") is True
    assert service._should_build_portfolio_daily_coach("Welke bots en plannen stapelen risico?", {}) is True
    assert service.looks_like_daily_coach_request("Welke setups conflicteren?") is True
    assert service._should_build_portfolio_daily_coach("Bots met overlappende budgetten", {}) is True
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
    assert any(verdict["agent"] == "execution_agent" for verdict in analysis["agent_verdicts"])
    assert any(verdict["agent"] == "risk_agent" and verdict["status"] == "high_attention" for verdict in analysis["agent_verdicts"])
    assert any(warning["asset"] == "BTC" for warning in risk["concentration_warnings"])
    assert risk["asset_priority"][0]["asset"] == "BTC"
    assert risk["asset_priority"][0]["priority"] == "eerst oplossen"
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
    assert "DCA en trade tegelijk" in risk["risk_stacks"][0]["factors"]
    assert "botbudget boven equity" in risk["risk_stacks"][0]["factors"]


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

    updated = service._apply_agent_controller_to_mission(mission, controller)

    assert controller["dominant_agent"] == "risk_agent"
    assert controller["ranked_verdicts"][0]["controller_rank"] == 1
    assert updated["summary"]["dominant_agent"] == "risk_agent"
    assert updated["workqueue_groups"][0]["key"] == "first"
    assert updated["workqueue"][0]["type"] == "blocked_plan"
    assert updated["workqueue"][0]["controller_rank_boost"] > 0
    assert updated["workqueue"][0]["dominant_agent"] == "risk_agent"


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
    assert "Wat Finn voorzichtig mag onthouden" in message
    assert "Wat Finn nog niet mag concluderen" in message


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
    assert "Profiel deze week" in message
    assert "Vergeleken met vorige week" in message


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
