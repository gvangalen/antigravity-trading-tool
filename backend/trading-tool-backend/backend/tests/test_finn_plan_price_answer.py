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


def test_plan_read_includes_a_separate_latest_quote():
    from backend.services.finn_v2_responses_tool_catalog import FinnResponsesToolCatalog

    call = FinnResponsesToolCatalog().validate("get_active_plan_and_strategy", {"asset": "AAPL"})
    assert "read_asset_scores" in call.read_tools
    assert "read_market_snapshot" in call.read_tools


def test_previous_aapl_quote_cannot_be_called_current_after_newer_measurement():
    trace = list(_trace(with_market=False))
    trace[0]["result"]["results"].append({
        "scope": "read_market_snapshot", "status": "completed", "source": "market_data",
        "freshness": "stale", "as_of": "2026-11-09T20:59:00+00:00",
        "data": {"symbol": "AAPL", "price": 350.48999, "quote_currency": "USD",
                 "as_of": "2026-11-09T20:59:00+00:00"},
    })
    previous = {"tool_trace": _trace(), "answer": "De koers was USD 351,19 om 19:03 UTC."}
    wrong = (
        "De actuele koerssnapshot die ik kan verifiëren is USD 351,19 van 9 november 19:03 UTC. "
        "De benchmark gebruikte USD 350,49 van 9 november 20:59 UTC."
    )
    rejected = _verify("Wat is de laatste AAPL-koers?", wrong, tuple(trace), previous_response=previous)
    assert rejected.status == "unavailable"
    assert rejected.reason == "latest_quote_conflicts_with_source"
    evidence = tuple(trace[0]["result"]["results"])
    assert FinnResponsesAnswerVerifier._latest_quote_claim_supported(
        "De laatste beschikbare AAPL-koersmeting is USD 350,49 van 9 november 20:59 UTC.",
        evidence,
    )


def test_latest_quote_claim_requires_current_turn_market_evidence():
    answer = _verify(
        "Wat is de laatste AAPL-koers?",
        "De laatste AAPL-koers is USD 351,19 van 9 november 19:03 UTC.",
        _trace(with_market=False),
    )
    assert answer.reason == "latest_quote_conflicts_with_source"


def test_latest_quote_accepts_dutch_thousands_separator_for_crypto():
    evidence = ({
        "scope": "read_market_snapshot", "status": "completed", "freshness": "fresh",
        "data": {"symbol": "BTC", "price": 75894, "quote_currency": "USDT",
                 "as_of": "2026-11-10T15:00:00+00:00"},
    },)
    assert FinnResponsesAnswerVerifier._latest_quote_claim_supported(
        "De actuele BTC-koers is USDT 75.894 van 10 november 15:00 UTC.", evidence,
    )


def test_latest_aapl_quote_with_iso_date_and_seconds_matches_full_source_moment():
    evidence = ({
        "scope": "read_market_snapshot", "status": "completed", "freshness": "fresh",
        "data": {"symbol": "AAPL", "price": 348.58, "quote_currency": "USD",
                 "source_observed_at_utc": "2026-11-10T19:48:00+00:00"},
    },)
    correct = (
        "De nieuwste door een bron gemeten AAPL-koers is USD 348,58, "
        "met bronmoment 2026-11-10 19:48:00 UTC. "
        "Het oude dagrapport vermeldt USD 351,19 op 2026-11-09 19:03:00 UTC."
    )
    assert FinnResponsesAnswerVerifier._latest_quote_claim_supported(correct, evidence)
    assert FinnResponsesAnswerVerifier._latest_quote_claim_supported(
        "Op 2026-11-10 19:48:00 UTC is de nieuwste AAPL-koers USD 348,58.", evidence,
    )
    same_sentence = (
        "De nieuwste AAPL-koers is USD 348,58 op 2026-11-10 19:48:00 UTC; "
        "het oude rapport vermeldt USD 351,19 op 2026-11-09 19:03:00 UTC."
    )
    assert FinnResponsesAnswerVerifier._latest_quote_claim_supported(same_sentence, evidence)
    report_before_its_price = (
        "De actuele AAPL-koers is USD 348,58 op 2026-11-10 19:48:00 UTC "
        "en het oude dagrapport van 2026-11-09 19:03:00 UTC noemt USD 351,19."
    )
    assert FinnResponsesAnswerVerifier._latest_quote_claim_supported(report_before_its_price, evidence)
    assert FinnResponsesAnswerVerifier._latest_quote_claim_supported(
        "Het oude rapport vermeldt USD 351,19 op 2026-11-09 19:03:00 UTC; "
        "de nieuwste AAPL-koers is USD 348,58 op 2026-11-10 19:48:00 UTC.",
        evidence,
    )
    historical_first = (
        "De laatste koers in het oude rapport was USD 351,19; "
        "op 2026-11-10 19:48:00 UTC is de actuele AAPL-koers USD 348,58."
    )
    assert FinnResponsesAnswerVerifier._latest_quote_claim_supported(historical_first, evidence)
    for wrong in (
        correct.replace("19:48:00 UTC", "19:48:01 UTC"),
        correct.replace("2026-11-10 19:48:00 UTC", "2026-11-09 19:48:00 UTC"),
        correct.replace("19:48:00 UTC", "48:00 UTC"),
        same_sentence.replace("2026-11-10 19:48:00 UTC", "2026-11-09 19:03:00 UTC"),
        report_before_its_price.replace("2026-11-10 19:48:00 UTC", "2026-11-09 19:03:00 UTC"),
        historical_first.replace("USD 348,58", "USD 999,00"),
        historical_first.replace("2026-11-10 19:48:00 UTC", "2026-11-09 19:03:00 UTC"),
        "Het oude rapport vermeldt USD 351,19; op 2026-11-09 19:03:00 UTC "
        "is de nieuwste AAPL-koers USD 348,58.",
    ):
        assert not FinnResponsesAnswerVerifier._latest_quote_claim_supported(wrong, evidence)


def test_stale_latest_quote_accepts_exact_iso_source_moment_with_seconds():
    evidence = ({
        "scope": "read_market_snapshot", "status": "completed", "freshness": "stale",
        "data": {"symbol": "AAPL", "price": 348.58, "quote_currency": "USD",
                 "source_observed_at_utc": "2026-11-10T19:48:00+00:00"},
    },)
    assert FinnResponsesAnswerVerifier._latest_quote_claim_supported(
        "De laatste beschikbare AAPL-koers is USD 348,58 van 2026-11-10 19:48:00 UTC.",
        evidence,
    )
    assert not FinnResponsesAnswerVerifier._latest_quote_claim_supported(
        "De laatste beschikbare AAPL-koers is USD 348,58 van 2026-11-10 19:48:01 UTC.",
        evidence,
    )


def test_latest_quote_matches_exact_currency_when_two_pairs_are_read():
    evidence = tuple({
        "scope": "read_market_snapshot", "status": "completed", "freshness": "fresh",
        "data": {"symbol": "BTC", "price": price, "quote_currency": quote,
                 "as_of": moment},
    } for price, quote, moment in (
        (66000, "EUR", "2026-11-10T10:00:00+00:00"),
        (74000, "USDT", "2026-11-10T10:01:00+00:00"),
    ))
    assert FinnResponsesAnswerVerifier._latest_quote_claim_supported(
        "De actuele BTC/EUR-koers is €66.000 van 10:00 UTC.", evidence,
    )
    assert FinnResponsesAnswerVerifier._latest_quote_claim_supported(
        "De actuele BTC/USDT-koers is USDT 74.000 van 10:01 UTC.", evidence,
    )


def test_historical_report_quote_and_unknown_current_quote_do_not_become_current_claims():
    evidence = ({
        "scope": "read_market_snapshot", "status": "completed", "freshness": "stale",
        "data": {"symbol": "AAPL", "price": 350.49, "quote_currency": "USD",
                 "as_of": "2026-11-09T20:59:00+00:00"},
    },)
    assert FinnResponsesAnswerVerifier._latest_quote_claim_supported(
        "De laatste koers in het ochtendrapport was USD 351,19 van 9 november 19:03 UTC.", evidence,
    )
    assert FinnResponsesAnswerVerifier._latest_quote_claim_supported(
        "De huidige AAPL-koers is onbekend; mijn stop is USD 300.", evidence,
    )


def test_current_quote_aliases_and_currency_after_amount_require_fresh_evidence():
    stale = ({
        "scope": "read_market_snapshot", "status": "completed", "freshness": "stale",
        "data": {"symbol": "AAPL", "price": 351.19, "quote_currency": "USD",
                 "as_of": "2026-11-09T19:03:00+00:00"},
    },)
    for claim in (
        "AAPL noteert momenteel USD 351,19.",
        "De koers van AAPL is nu USD 351,19.",
        "De laatste koers van AAPL is USD 351,19.",
    ):
        assert not FinnResponsesAnswerVerifier._latest_quote_claim_supported(claim, stale)
    assert not FinnResponsesAnswerVerifier._latest_quote_claim_supported(
        "De actuele AAPL-koers is 351,19 USD.", (),
    )


def test_three_decimal_crypto_quote_is_not_mistaken_for_thousands():
    evidence = ({
        "scope": "read_market_snapshot", "status": "completed", "freshness": "fresh",
        "data": {"symbol": "ADA", "price": 0.123, "quote_currency": "USDT",
                 "as_of": "2026-11-10T10:00:00+00:00"},
    },)
    assert FinnResponsesAnswerVerifier._latest_quote_claim_supported(
        "De actuele ADA-koers is USDT 0.123 van 10:00 UTC.", evidence,
    )


def test_stale_latest_quote_requires_its_exact_dated_source_moment():
    stale = ({
        "scope": "read_market_snapshot", "status": "completed", "freshness": "stale",
        "data": {"symbol": "AAPL", "price": 351.19, "quote_currency": "USD",
                 "as_of": "2026-11-09T19:03:00+00:00"},
    },)
    for claim in (
        "Om 10:00 UTC is de laatste AAPL-koers USD 351,19.",
        "De laatste AAPL-koers om 10:00 UTC is USD 351,19.",
        "De laatste AAPL-koers is USD 351,19 van 8 november 19:03 UTC.",
        "De laatste AAPL-koers is USD 351,19 van 9 november 20:03 UTC.",
        "De laatste AAPL-koers is USD 351,19 van 9 november 20:03 CEST.",
    ):
        assert not FinnResponsesAnswerVerifier._latest_quote_claim_supported(claim, stale)
    assert FinnResponsesAnswerVerifier._latest_quote_claim_supported(
        "De laatste beschikbare AAPL-koers is USD 351,19 van 9 november 19:03 UTC.", stale,
    )
    assert FinnResponsesAnswerVerifier._latest_quote_claim_supported(
        "De laatste beschikbare AAPL-koers is USD 351,19 van 9 november 20:03 CET.", stale,
    )


def test_nonexistent_amsterdam_dst_clock_cannot_be_a_source_moment():
    stale = ({
        "scope": "read_market_snapshot", "status": "completed", "freshness": "stale",
        "data": {"symbol": "AAPL", "price": 351.19, "quote_currency": "USD",
                 "as_of": "2026-03-29T01:30:00+00:00"},
    },)
    assert not FinnResponsesAnswerVerifier._latest_quote_claim_supported(
        "De laatste AAPL-koers is USD 351,19 van 29 maart 2026 02:30 CET.", stale,
    )
    assert FinnResponsesAnswerVerifier._latest_quote_claim_supported(
        "De laatste AAPL-koers is USD 351,19 van 29 maart 2026 03:30 CEST.", stale,
    )


def test_minimal_read_cannot_relabel_previous_turn_price_as_current():
    old_trace = _trace()
    prepared = SimpleNamespace(
        response=SimpleNamespace(
            text="De actuele AAPL-koerssnapshot is USD 346,61.",
            tool_trace=_trace(with_market=False), uses_previous_response=True,
        ),
        previous_response={"terminal_status": "completed", "tool_trace": old_trace,
                           "turn_contract": {"targets": [{"evidence": {"symbol": "AAPL"}}]}},
    )
    answer = _minimal_read_answer(message="Wat is nu de actuele AAPL-koers?", prepared=prepared)
    assert answer.status == "unavailable"
    assert answer.reason == "latest_quote_conflicts_with_source"


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
