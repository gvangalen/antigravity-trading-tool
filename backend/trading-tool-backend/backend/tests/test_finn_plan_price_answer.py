"""The model owns read-only coach prose; tools supply dated, typed facts."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services.finn_v2_responses_answer_verifier import FinnResponsesAnswerVerifier
from backend.services.finn_v2_responses_loop import FinnResponsesResult
from backend.services.finn_v2_run_service import _minimal_read_answer
from backend.services.finn_v2_turn_contract import build_turn_contract


def _trace(*, with_market=True):
    strategy = {
        "scope": "read_linked_strategy", "status": "completed", "source": "owner_strategy",
        "data": {
            "setup_id": 8, "strategy_id": 130, "symbol": "AAPL", "name": "AAPL plan",
            "entry": 347.14, "stop_loss": 342, "targets": [357.42],
            "price_currency": "USD", "price_currency_status": "confirmed",
        },
    }
    trace = [{"name": "get_active_plan_and_strategy", "result": {"results": [strategy]}}]
    if with_market:
        trace.append({"name": "get_market_snapshot", "result": {"results": [{
            "scope": "read_market_snapshot", "status": "completed", "source": "market_data",
            "freshness": "fresh", "as_of": datetime.now(timezone.utc).isoformat(),
            "data": {
                "symbol": "AAPL", "price": 346.61, "quote_currency": "USD",
                "as_of": datetime.now(timezone.utc).isoformat(),
            },
        }]}})
    return tuple(trace)


def _verify(message, draft, trace, *, previous_response=None):
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    result = FinnResponsesResult(
        draft, "model-response", trace, model_led_coach=True,
        model_owned_repair=True, answer_kind="free_text",
        uses_previous_response=previous_response is not None,
        turn_contract=build_turn_contract(message=message, tool_trace=trace),
    )
    return asyncio.run(FinnResponsesAnswerVerifier(semantic=semantic).verify(
        message=message, result=result, previous_response=previous_response, locale="nl",
    ))


def test_saved_stop_loss_after_market_question_keeps_model_prose():
    trace = _trace()
    draft = "De opgeslagen stop-loss van AAPL plan is USD 342. Dat is een planwaarde."
    answer = _verify(
        "Wat is mijn opgeslagen stop-loss?", draft, trace[:1],
        previous_response={"tool_trace": trace, "answer": "De koers was USD 346,61."},
    )
    assert answer.status == "completed"
    assert answer.text == draft


def test_live_minimal_read_path_keeps_model_answer_and_checks_typed_price_direction():
    trace = _trace()
    def prepared(draft):
        return SimpleNamespace(response=SimpleNamespace(
            text=draft, tool_trace=trace, uses_previous_response=False,
        ), previous_response=None)

    correct = "De actuele AAPL-koers ligt onder je opgeslagen instapprijs."
    incorrect = "De actuele AAPL-koers ligt boven je opgeslagen instapprijs."
    assert _minimal_read_answer(message="Vergelijk koers en instap", prepared=prepared(correct)).text == correct
    rejected = _minimal_read_answer(message="Vergelijk koers en instap", prepared=prepared(incorrect))
    assert rejected.status == "unavailable"
    assert rejected.reason == "price_relation_conflicts_with_source"


def test_broad_plan_review_does_not_become_a_fixed_template():
    trace = _trace()
    draft = (
        "Je AAPL plan heeft een opgeslagen stop-loss van USD 342. "
        "De laatste koersmeting is USD 346,61; bespreek eerst welke instapvoorwaarde je bedoelt."
    )
    answer = _verify("Wat vind je van mijn AAPL-plan?", draft, trace)
    assert answer.status == "completed"
    assert answer.text == draft


def test_price_followup_without_new_quote_can_discuss_saved_plan():
    trace = _trace()
    draft = (
        "Je opgeslagen AAPL-stop is USD 342. De eerdere koersmeting kan ik als "
        "momentopname bespreken; ik bevestig er geen nieuwe actuele koers mee."
    )
    answer = _verify(
        "En wat betekent dat voor mijn plan?", draft, trace[:1],
        previous_response={"tool_trace": trace, "answer": "De koers was USD 346,61."},
    )
    assert answer.status == "completed"
    assert answer.text == draft


def test_fact_check_rejects_wrong_direction_without_writing_coach_copy():
    question = "Ligt de huidige AAPL-koers boven of onder mijn instap?"
    incorrect = "De AAPL-koers van USD 346,61 ligt boven je instap van USD 347,14."
    correct = "De AAPL-koers van USD 346,61 ligt onder je instap van USD 347,14."
    wrong = _verify(question, incorrect, _trace())
    right = _verify(question, correct, _trace())
    assert wrong.status == "unavailable"
    assert wrong.reason == "price_relation_conflicts_with_source"
    assert wrong.rejection_details == {"fact_mismatch": "typed_plan_price_relation"}
    assert right.status == "completed"
    assert right.text == correct


def test_live_read_rejects_the_paper_traders_exact_wrong_aapl_price_claims():
    trace = _trace()
    def checked(draft):
        prepared = SimpleNamespace(response=SimpleNamespace(
            text=draft, tool_trace=trace, uses_previous_response=False,
        ), previous_response=None)
        return _minimal_read_answer(message="Vergelijk mijn AAPL-plan met de koers", prepared=prepared)

    wrong_direction = checked("US$346,61 ligt boven de entry van US$347,14.")
    wrong_quote = checked("De opgeslagen prijsvaluta is EUR.")
    wrong_level_quote = checked("De entry is €347,14.")
    wrong_trailing_quote = checked("De entry is 347,14 EUR.")
    correct = "US$346,61 ligt onder de entry van US$347,14. Het basisbedrag is €25."
    assert wrong_direction.reason == "price_relation_conflicts_with_source"
    assert wrong_quote.reason == "price_relation_conflicts_with_source"
    assert wrong_level_quote.reason == "price_relation_conflicts_with_source"
    assert wrong_trailing_quote.reason == "price_relation_conflicts_with_source"
    assert checked(correct).text == correct


def test_negated_comparison_is_not_treated_as_opposite_claim():
    trace = _trace()
    evidence = tuple(item for call in trace for item in call["result"]["results"])
    assert FinnResponsesAnswerVerifier._price_relation_claim_supported(
        "De koers ligt niet boven je instap.", evidence,
    )


def test_crypto_quote_uses_its_own_usdt_unit():
    trace = list(_trace())
    strategy = trace[0]["result"]["results"][0]
    market = trace[1]["result"]["results"][0]
    strategy["data"].update({
        "symbol": "BTC", "name": "BTC plan", "entry": 76000,
        "stop_loss": 72000, "targets": [84000], "price_currency": "USDT",
    })
    market["data"].update({"symbol": "BTC", "price": 75000, "quote_currency": "USDT"})
    draft = "De BTC-koers van USDT 75000 ligt onder de opgeslagen instap van USDT 76000."
    answer = _verify("Ligt de huidige BTC-koers onder mijn instap?", draft, tuple(trace))
    assert answer.status == "completed"
    assert answer.text == draft


def test_provider_outage_cannot_be_published_as_a_written_coach_answer():
    result = FinnResponsesResult(
        "", "provider-timeout", (), model_led_coach=True,
        answer_kind="provider_unavailable",
    )
    answer = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message="Ik wil mijn stop-loss weghalen; denk met me mee zonder iets te wijzigen.",
        result=result, locale="nl",
    ))
    assert answer.status == "unavailable"
    assert answer.reason == "responses_provider_timeout"
    assert "Ik zou" not in answer.text
