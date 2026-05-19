import asyncio
from decimal import Decimal

from backend.services.finn_plan_service import FinnPlanService
from backend.services.strategy_service import StrategyService


def _service():
    return FinnPlanService(db_session=None)


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
    result = _service().build_response("Maak een wekelijkse BTC DCA van 100 euro zonder bot")

    assert result["can_confirm"] is True
    assert result["draft"]["bot"]["create_bot"] is False
    assert "Bot:" not in result["response"]


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
