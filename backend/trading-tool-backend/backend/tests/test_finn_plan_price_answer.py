import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from backend.services.finn_v2_responses_answer_verifier import FinnResponsesAnswerVerifier
from backend.services.finn_v2_responses_loop import FinnResponsesResult
from backend.services.finn_v2_turn_contract import build_turn_contract


def _result(market, message="Staat de actuele AAPL koers boven of onder mijn entry?"):
    strategy = {"scope": "read_linked_strategy", "status": "completed", "data": {
        "setup_id": 8, "strategy_id": 130, "symbol": "AAPL", "name": "AAPL plan",
        "entry": 347.14, "stop_loss": 342, "targets": [357.42],
        "price_currency": "USD", "price_currency_status": "confirmed",
    }}
    trace = (
            {"name": "get_active_plan_and_strategy", "result": {"results": [strategy]}},
            {"name": "get_market_snapshot", "result": {"results": [market]}},
        )
    return FinnResponsesResult(
        "AAPL is boven de entry van USD 347,14.", "response-1", trace,
        model_led_coach=True,
        turn_contract=build_turn_contract(message=message, tool_trace=trace),
    )


def test_direct_price_question_uses_server_comparison_not_model_direction():
    market = {"scope": "read_market_snapshot", "status": "completed", "data": {
        "symbol": "AAPL", "price": 346.61, "quote_currency": "USD",
        "as_of": datetime.now(timezone.utc).isoformat(),
    }}
    verified = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message="Staat de actuele AAPL koers boven of onder mijn entry?",
        result=_result(market), locale="nl",
    ))
    assert verified.status == "completed"
    assert verified.reason == "verified_plan_price_comparison"
    assert "onder de opgeslagen instapprijs" in verified.text
    assert "boven de entry" not in verified.text


def test_general_plan_question_cannot_volunteer_wrong_price_direction():
    market = {"scope": "read_market_snapshot", "status": "completed", "data": {
        "symbol": "AAPL", "price": 346.61, "quote_currency": "USD",
        "as_of": datetime.now(timezone.utc).isoformat(),
    }}
    message = "Wat vind je van mijn AAPL-plan?"
    verified = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=message, result=_result(market, message), locale="nl",
    ))
    assert verified.reason == "verified_saved_plan_answer"
    assert "stop-loss USD 342" in verified.text
    assert "doel(en) USD 357,42" in verified.text
    assert "geen volledige beoordeling" in verified.text
    assert "onder de opgeslagen instapprijs" in verified.text
    assert "boven de entry" not in verified.text
    front_door = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=message, result=replace(_result(market, message), model_owned_repair=True), locale="nl",
    ))
    assert front_door.reason == "verified_saved_plan_answer"
    assert front_door.text == verified.text


def test_price_answer_shows_subcent_direction_and_distance():
    market = {"scope": "read_market_snapshot", "status": "completed", "data": {
        "symbol": "AAPL", "price": 347.141, "quote_currency": "USD",
        "as_of": datetime.now(timezone.utc).isoformat(),
    }}
    message = "Hoe ver ligt de actuele AAPL koers van mijn entry?"
    verified = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=message, result=_result(market, message), locale="nl",
    ))
    assert "USD 347,141" in verified.text
    assert "USD 347,140" in verified.text
    assert "verschil is USD 0,001" in verified.text


def test_current_quote_does_not_claim_historical_entry_trigger():
    market = {"scope": "read_market_snapshot", "status": "completed", "data": {
        "symbol": "AAPL", "price": 346.61, "quote_currency": "USD",
        "as_of": datetime.now(timezone.utc).isoformat(),
    }}
    message = "Is mijn AAPL-instapprijs al bereikt?"
    verified = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=message, result=_result(market, message), locale="nl",
    ))
    assert "Of de instap eerder is geraakt" in verified.text


def test_general_followup_cannot_reuse_wrong_direction_from_previous_tools():
    market = {"scope": "read_market_snapshot", "status": "completed", "data": {
        "symbol": "AAPL", "price": 346.61, "quote_currency": "USD",
        "as_of": datetime.now(timezone.utc).isoformat(),
    }}
    previous = _result(market)
    result = FinnResponsesResult(
        "AAPL staat boven de entry.", "response-followup", (),
        uses_previous_response=True, model_led_coach=True,
    )
    verified = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message="En wat betekent dat voor mijn plan?", result=result, locale="nl",
        previous_response={"tool_trace": previous.tool_trace},
    ))
    assert verified.reason == "plan_price_requires_fresh_read"
    assert "opnieuw ophalen" in verified.text

    # A current strategy-only read must not make an old market quote look new.
    strategy_only = replace(result, tool_trace=(previous.tool_trace[0],))
    verified = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message="En wat betekent dat voor mijn plan?", result=strategy_only, locale="nl",
        previous_response={"tool_trace": previous.tool_trace},
    ))
    assert verified.reason == "plan_price_requires_fresh_read"


def test_general_answer_never_delivers_unverified_price_or_currency_claims():
    market = {"scope": "read_market_snapshot", "status": "completed", "data": {
        "symbol": "AAPL", "price": 346.61, "quote_currency": "USD",
        "as_of": datetime.now(timezone.utc).isoformat(),
    }}
    for answer in (
        "AAPL staat boven de instap.",
        "AAPL is boven de instap. De koers ligt ook onder de instap.",
        "De AAPL-entry is EUR 347,14.",
        "AAPL handelt voorbij de opgeslagen instap.",
    ):
        result = replace(_result(market, "Wat vind je van mijn AAPL-plan?"), text=answer)
        verified = asyncio.run(FinnResponsesAnswerVerifier().verify(
            message="Wat vind je van mijn AAPL-plan?", result=result, locale="nl",
        ))
        assert verified.reason == "verified_saved_plan_answer", answer
        assert answer not in verified.text


def test_saved_stop_readback_uses_current_strategy_without_market_quote():
    market = {"scope": "read_market_snapshot", "status": "completed", "data": {
        "symbol": "AAPL", "price": 346.61, "quote_currency": "USD",
        "as_of": datetime.now(timezone.utc).isoformat(),
    }}
    previous = _result(market)
    question = "Wat is mijn opgeslagen stop-loss?"
    current = FinnResponsesResult(
        "Je stop-loss is EUR 342.", "response-stop", (previous.tool_trace[0],),
        model_led_coach=True, uses_previous_response=True,
        turn_contract=build_turn_contract(message=question, tool_trace=(previous.tool_trace[0],)),
    )
    verified = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=question, result=current, locale="nl",
        previous_response={"tool_trace": previous.tool_trace},
    ))
    assert verified.reason == "verified_saved_plan_answer"
    assert "stop-loss USD 342" in verified.text
    assert "marktkoers" not in verified.text
    front_door = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=question, result=replace(current, model_owned_repair=True), locale="nl",
        previous_response={"tool_trace": previous.tool_trace},
    ))
    assert front_door.reason == "verified_saved_plan_answer"
    assert front_door.text == verified.text


def test_saved_readback_does_not_use_another_asset_or_conflicting_snapshot():
    market = {"scope": "read_market_snapshot", "status": "completed", "data": {
        "symbol": "AAPL", "price": 346.61, "quote_currency": "USD",
        "as_of": datetime.now(timezone.utc).isoformat(),
    }}
    base = _result(market, "Wat is mijn AAPL-instap?")
    other = {**base.tool_trace[0]["result"]["results"][0], "data": {
        **base.tool_trace[0]["result"]["results"][0]["data"],
        "symbol": "BTC", "entry": 60000,
    }}
    wrong_asset = replace(base, tool_trace=({"result": {"results": [other]}}, base.tool_trace[1]))
    verified = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message="Wat is mijn AAPL-instap?", result=wrong_asset, locale="nl",
    ))
    assert verified.reason == "verified_saved_plan_answer"
    assert "niet bevestigen" in verified.text
    assert "60000" not in verified.text

    first = base.tool_trace[0]["result"]["results"][0]
    changed = {**first, "data": {**first["data"], "entry": 400}}
    conflicting = replace(base, tool_trace=({"result": {"results": [first, changed]}}, base.tool_trace[1]))
    verified = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message="Wat is mijn AAPL-instap?", result=conflicting, locale="nl",
    ))
    assert verified.reason == "verified_saved_plan_answer"
    assert "spreken elkaar tegen" in verified.text
    assert "347" not in verified.text and "400" not in verified.text

    price_question = "Staat de huidige AAPL koers boven mijn entry?"
    direct = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=price_question,
        result=replace(conflicting, turn_contract=build_turn_contract(
            message=price_question, tool_trace=conflicting.tool_trace,
        )), locale="nl",
    ))
    assert direct.reason == "verified_plan_price_comparison"
    assert "spreken" in direct.text and "tegen" in direct.text

    market_conflict = {**market, "data": {**market["data"], "price": 400}}
    conflicting_market = replace(base, tool_trace=(
        base.tool_trace[0], {"result": {"results": [market, market_conflict]}},
    ))
    direct = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=price_question,
        result=replace(conflicting_market, turn_contract=build_turn_contract(
            message=price_question, tool_trace=conflicting_market.tool_trace,
        )), locale="nl",
    ))
    assert "spreken" in direct.text and "tegen" in direct.text

    equivalent_time = {**market_conflict, "data": {
        **market_conflict["data"],
        "as_of": market["data"]["as_of"].replace("+00:00", "Z"),
    }}
    conflicting_market = replace(base, tool_trace=(
        base.tool_trace[0], {"result": {"results": [market, equivalent_time]}},
    ))
    direct = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=price_question,
        result=replace(conflicting_market, turn_contract=build_turn_contract(
            message=price_question, tool_trace=conflicting_market.tool_trace,
        )), locale="nl",
    ))
    assert "spreken" in direct.text and "tegen" in direct.text


def test_direct_price_question_never_uses_stale_or_mismatched_quote():
    market = {"scope": "read_market_snapshot", "status": "completed", "data": {
        "symbol": "AAPL", "price": 346.61, "quote_currency": "USD",
        "as_of": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
    }}
    verifier = FinnResponsesAnswerVerifier()
    stale = asyncio.run(verifier.verify(
        message="Is de huidige AAPL koers boven mijn entry?", result=_result(market, "Is de huidige AAPL koers boven mijn entry?"), locale="nl",
    ))
    assert stale.reason == "verified_plan_price_comparison"
    assert "nieuwe, bevestigde marktkoers" in stale.text
    market["data"]["as_of"] = datetime.now(timezone.utc).isoformat()
    market["data"]["quote_currency"] = "EUR"
    mismatched = asyncio.run(verifier.verify(
        message="Is de huidige AAPL koers boven mijn entry?", result=_result(market, "Is de huidige AAPL koers boven mijn entry?"), locale="nl",
    ))
    assert "niet betrouwbaar" in mismatched.text


def test_general_plan_advice_is_not_classified_as_direct_price_comparison():
    assert not build_turn_contract(
        message="Hoe beïnvloedt de markt mijn instapplan?", tool_trace=(),
    )["price_relation_requested"]
    for message in (
        "Is de AAPL prijs boven mijn instap?",
        "Ligt mijn AAPL-instap op dit moment boven de markt?",
        "Is mijn AAPL-instapprijs al bereikt?",
        "Wat is het verschil tussen de actuele koers en mijn instap?",
        "Hoe ver ligt AAPL nog van mijn entry?",
    ):
        assert build_turn_contract(
            message=message, tool_trace=(),
        )["price_relation_requested"], message


def test_multiple_strategy_price_question_asks_which_strategy():
    now = datetime.now(timezone.utc)
    strategy = lambda setup_id, strategy_id: {
        "scope": "read_linked_strategy", "status": "completed", "data": {
            "setup_id": setup_id, "strategy_id": strategy_id,
            "symbol": "AAPL", "entry": 347.14,
            "price_currency": "USD", "price_currency_status": "confirmed",
        },
    }
    market = {"scope": "read_market_snapshot", "status": "completed", "data": {
        "symbol": "AAPL", "price": 346.61, "quote_currency": "USD", "as_of": now.isoformat(),
    }}
    trace = ({"result": {"results": [strategy(8, 130), strategy(9, 131)]}},
             {"result": {"results": [market]}})
    message = "Staat de actuele koers boven of onder mijn entry?"
    result = FinnResponsesResult(
        "AAPL is boven de entry.", "response-2", trace,
        turn_contract=build_turn_contract(message=message, tool_trace=trace),
    )
    verified = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=message, result=result, locale="nl",
    ))
    assert verified.text == "Welke opgeslagen strategie wil je met de actuele koers vergelijken?"
