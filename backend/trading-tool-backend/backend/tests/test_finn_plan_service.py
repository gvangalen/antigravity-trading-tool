import asyncio

from backend.services.finn_plan_service import FinnPlanService


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
    assert result["draft"]["strategy"]["entry"] == 160
    assert result["draft"]["strategy"]["stop_loss"] == 145
    assert result["draft"]["strategy"]["targets"] == [180, 200]


def test_trade_plan_understands_natural_breakout_language():
    result = _service().build_response(
        "Ik wil SOL kopen bij breakout boven 180 op 4H met stop 160 targets 210 en 240 voor 100 euro"
    )

    assert result["can_confirm"] is True
    assert result["draft"]["plan_type"] == "trade"
    assert result["draft"]["asset"] == "SOL"
    assert result["draft"]["setup"]["timeframe"] == "4H"
    assert result["draft"]["strategy"]["entry"] == 180
    assert result["draft"]["strategy"]["stop_loss"] == 160
    assert result["draft"]["strategy"]["targets"] == [210, 240]
    assert result["actions"][0]["type"] == "create_plan"


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
