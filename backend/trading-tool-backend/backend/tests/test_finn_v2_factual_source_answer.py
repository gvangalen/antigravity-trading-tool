import asyncio
from datetime import datetime, timezone

from backend.services.finn_v2_responses_front_door import FinnResponsesFrontDoor
from backend.services.finn_v2_responses_answer_verifier import FinnResponsesAnswerVerifier
from backend.services.finn_v2_factual_source_answer import (
    mentions_technical_indicator, render_bot_decision, render_closed_paper_exit_facts,
    render_account_market_report_facts,
)
from backend.services.asset_catalog_service import requested_catalog_trading_pair


def _run(message, results, *, verified_asset=None, workspace_hints=None):
    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7,
                                   run_id="factual-source-test", model_led_coach=True)
    calls = []

    async def read(call):
        calls.append(call)
        return {"status": "completed", "results": results}

    front.reads = read
    prepared = asyncio.run(front.run(
        message=message, instructions="", conversation_context={},
        verified_asset=verified_asset, locale="nl", workspace_hints=workspace_hints,
    ))
    assert len(calls) == 1
    checked = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=message, result=prepared.response, locale="nl",
        user_time_zone=(workspace_hints or {}).get("time_zone"),
    ))
    assert checked.status == "completed", (checked.reason, checked.rejection_details)
    assert checked.text == prepared.response.text
    return prepared.response, calls[0]


def test_paper_four_amounts_verify_in_user_time_zone():
    question = (
        "Wat is de ingestelde budgetlimiet van mijn BTC Paper-bot, hoeveel is "
        "werkelijk belegd, hoeveel kas heeft die bot en hoeveel kas heeft mijn "
        "totale Paper-portefeuille? Noem deze vier bedragen afzonderlijk met "
        "bronmoment. Lees alleen en verander niets."
    )
    rows = [{"scope": "read_portfolio", "status": "completed", "asset": None,
             "data": {"environment": "paper", "read_at_utc": "2026-11-24T05:25:00+00:00",
                      "global": {"cash_balance": 10000, "invested_value": 0},
                      "bots": [{"symbol": "BTC", "is_live": False, "position_qty": 0,
                                "invested_eur": 0, "paper_cash_eur": 10000,
                                "budget_total_eur": 1000}]}}]
    for zone, moment in (("Europe/Amsterdam", "2026-11-24 06:25:00 CET"),
                         ("America/Los_Angeles", "2026-11-23 21:25:00 PST")):
        answer, call = _run(question, rows, workspace_hints={"time_zone": zone})
        assert call.name == "get_portfolio_and_exposure"
        assert "budgetlimiet van je BTC Paper-bot is €1000" in answer.text
        assert "In die bot is €0 werkelijk belegd" in answer.text
        assert "totale Paper-portefeuille heeft €0 belegd en €10000 kas" in answer.text
        assert "BTC-botkas is daarvan €10000" in answer.text
        assert moment in answer.text
        wrong_zone = "America/Los_Angeles" if zone == "Europe/Amsterdam" else "Europe/Amsterdam"
        rejected = asyncio.run(FinnResponsesAnswerVerifier().verify(
            message=question, result=answer, locale="nl", user_time_zone=wrong_zone,
        ))
        assert rejected.status == "unavailable"
        assert rejected.reason == "factual_source_mismatch"
    invested_question = question.replace("werkelijk belegd", "werkelijk geïnvesteerd")
    invested_answer, _ = _run(
        invested_question, rows, workspace_hints={"time_zone": "Europe/Amsterdam"},
    )
    assert "€0 werkelijk belegd" in invested_answer.text


def _dated_aapl_account_rows():
    return [
        {"scope": "read_active_setup", "source": "setups", "status": "completed",
         "data": {"symbol": "AAPL", "setup_id": 11}},
        {"scope": "read_linked_strategy", "source": "strategies", "status": "completed",
         "data": {"symbol": "AAPL", "setup_id": 11, "strategy_id": 12}},
        {"scope": "read_asset_scores", "source": "daily_scores_and_source_indicators",
         "status": "completed", "data": {"symbol": "AAPL", "benchmark_score": 52.7,
                                        "reported_scores": {"market_score": 52.7}}},
        {"scope": "read_market_snapshot", "source": "market_data", "status": "completed",
         "data": {"symbol": "AAPL", "quote_currency": "USD", "price": 341.92,
                  "source_observed_at_utc": "2026-11-20T20:58:00+00:00"}},
        {"scope": "read_latest_report", "source": "daily_reports", "status": "completed",
         "data": {"report_date": "2026-11-09", "score_source_snapshot": {"assets": [{
             "symbol": "AAPL", "market_snapshot": {"price": 351.19,
                 "quote_currency": "USD", "as_of": "2026-11-09T19:03:00+00:00"}}]}}},
        {"scope": "read_bot_status", "source": "bot_configs", "status": "completed",
         "data": {"bot_id": 13, "is_live": False,
                  "latest_decision": {"reason_code": "market_price_stale"}}},
    ]


def test_closed_market_account_comparison_completes_without_a_second_model_round():
    question = ("Lees mijn AAPL-plan en score, de nieuwste AAPL-marktkoers met exact UTC-bronmoment, "
                "het oudere opgeslagen dagrapport met USD 351,19 op 9 november 19:03 UTC, "
                "en de Paper-botstatus met market_price_stale. Welke koers is nu de nieuwste bron? "
                "Bespreek alleen; wijzig niets en plaats geen order.")
    answer, call = _run(question, _dated_aapl_account_rows(), verified_asset="AAPL")
    assert answer.answer_kind == "factual_source"
    assert set(call.read_tools) == {row["scope"] for row in _dated_aapl_account_rows()}
    assert call.inputs["report_date"] == "2026-11-09"
    assert "benchmarkscore is 52.7/100" in answer.text
    assert "USD 341,92 met bronmoment 2026-11-20 20:58 UTC" in answer.text
    assert "historisch USD 351,19 met bronmoment 2026-11-09 19:03 UTC" in answer.text
    assert "geen geverifieerde uitvoeringskoers" in answer.text


def test_closed_market_account_followup_rechecks_both_sources():
    question = ("Eerder noemden we USD 351,19 om 19:03 UTC. Is dat nu de actuele AAPL-koers? "
                "Controleer opnieuw plan, score, marktbron, oud rapport en Paper-botstatus. "
                "Geef de twee UTC-bronmomenten en wijzig niets.")
    answer, call = _run(question, _dated_aapl_account_rows(), verified_asset="AAPL")
    assert answer.answer_kind == "factual_source"
    assert call.name == "get_active_plan_and_strategy"
    assert "2026-11-20 20:58 UTC" in answer.text
    assert "2026-11-09 19:03 UTC" in answer.text


def test_account_market_report_refuses_cross_asset_or_unlinked_sources():
    rows = _dated_aapl_account_rows()
    rows[1]["data"] = {**rows[1]["data"], "setup_id": 99}
    answer = render_account_market_report_facts({"results": rows}, symbol="AAPL")
    assert "niet eenduidig koppelen" in answer
    assert "341,92" not in answer


def test_named_paper_exit_facts_use_exact_owner_review_and_both_currencies():
    question = ("Wat was bij mijn trade-reflectie #77 de vastgelegde Paper-exitreden? "
                "Noem de oorspronkelijke koersvaluta, het opgeslagen eerste doel en de "
                "wisselkoers bij uitvoering. Alleen teruglezen; geen voorstel of actie.")
    trace = ({"name": "get_closed_trade_review", "result": {"results": [{
        "scope": "read_review_history", "status": "completed", "data": {"closed_trades": [
            {"review_id": 76, "environment": "paper", "paper_exit_evidence": {
                "trigger": "stop_loss", "source_price_currency": "USD",
                "saved_first_target": 999, "execution_fx_eur_per_unit": 0.5}},
            {"review_id": 77, "environment": "paper", "paper_exit_evidence": {
                "trigger": "first_target", "source_price_currency": "USD",
                "saved_first_target": 320, "execution_fx_eur_per_unit": 0.920000}},
        ]},
    }]}},)

    answer = render_closed_paper_exit_facts(question, trace)

    assert "trade-reflectie #77" in answer
    assert "eerste koersdoel" in answer
    assert "eerste doel was 320 USD" in answer
    assert "wisselkoers bij uitvoering was 0.92 EUR per USD" in answer
    assert "999" not in answer
    assert render_closed_paper_exit_facts(question.replace("#77", "#78"), trace) is None


def test_named_paper_exit_facts_require_verified_fx_and_paper_origin():
    question = ("Wat was bij mijn trade-reflectie #77 de vastgelegde Paper-exitreden? "
                "Noem de oorspronkelijke koersvaluta, het opgeslagen eerste doel en de "
                "wisselkoers bij uitvoering.")
    row = {"review_id": 77, "environment": "paper", "paper_exit_evidence": {
        "trigger": "stop_loss", "source_price_currency": "USD",
        "saved_first_target": 320, "execution_fx_eur_per_unit": None}}
    trace = ({"result": {"results": [{"scope": "read_review_history",
              "status": "completed", "data": {"closed_trades": [row]}}]}},)

    assert render_closed_paper_exit_facts(question, trace) is None
    row["paper_exit_evidence"]["execution_fx_eur_per_unit"] = 0.92
    row["environment"] = "live"
    assert render_closed_paper_exit_facts(question, trace) is None


def test_explicit_bot_id_selects_only_its_saved_decision():
    result = {"results": [{"scope": "read_review_history", "status": "completed",
                           "data": {"latest_bot_decisions": [
                               {"bot_id": 129, "symbol": "BTC", "is_live": False,
                                "action": "hold", "persistence_status": "completed",
                                "decision_at": "2026-11-16T08:45:18+00:00"},
                               {"bot_id": 131, "symbol": "BTC", "is_live": False,
                                "action": "buy", "persistence_status": "completed",
                                "decision_at": "2026-11-16T09:00:18+00:00"},
                           ]}}]}
    answer = render_bot_decision(result, symbol="BTC", paper=False, bot_id=129)
    assert "bot 129" in answer
    assert "09:45:18 CET" in answer
    assert "10:00:18 CET" not in answer


def test_clicked_paper_wait_card_uses_selected_decision_not_later_history():
    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7,
                                   run_id="selected-feed-test", model_led_coach=True)
    calls = []

    async def read(call):
        calls.append(call)
        return {"status": "completed", "results": [{"scope": "read_review_history",
            "status": "completed", "data": {
                "selected_feed_decision": {"symbol": "BTC", "pair": "BTC/USDT",
                    "action": "hold", "decision_at": "2026-11-16T06:00:18+00:00",
                    "paper_executed": False},
                "latest_bot_decisions": [{"symbol": "BTC", "action": "hold",
                    "decision_at": "2026-11-16T09:45:18+00:00"}],
            }}]}

    front.reads = read
    message = ("Bespreek dit opgeslagen Paper-botbesluit voor BTC: Je BTC-bot wacht · Paper. "
               "Controleer de beslissing en eventuele uitvoering in de botgeschiedenis.")
    result = asyncio.run(front.run(message=message, instructions="", conversation_context={},
        verified_asset="BTC", locale="nl", feed_evidence=[{"source": "owner_scoped_feed",
            "facts": {"event_type": "bot_decision", "historical_notification": True,
                      "selection_origin": "current_run", "symbol": "BTC",
                      "historical_source_observed_at": "2026-11-16T06:00:18+00:00",
                      "historical_event_facts": {"action": "hold"}}}]))
    assert len(calls) == 1 and calls[0].read_tools == ("read_review_history",)
    assert "2026-11-16 07:00:18 CET" in result.response.text
    assert "10:45" not in result.response.text
    assert "geen gevulde Paper-order" in result.response.text
    checked = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=message, result=result.response, locale="nl"))
    assert checked.status == "completed", (checked.reason, checked.rejection_details)


def test_clicked_paper_card_without_owner_feed_context_fails_closed():
    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7,
                                   run_id="missing-feed-test", model_led_coach=True)
    result = asyncio.run(front.run(
        message="Bespreek dit opgeslagen Paper-botbesluit voor AAPL: Je AAPL-bot wacht · Paper.",
        instructions="", conversation_context={}, verified_asset="AAPL", locale="nl",
    ))
    assert "kaart niet verifiëren" in result.response.text


def test_clicked_paper_sale_uses_selected_historical_decision_without_model_clock():
    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7,
                                   run_id="selected-sale-test", model_led_coach=True)
    calls = []

    async def read(call):
        calls.append(call)
        return {"status": "completed", "results": [{"scope": "read_review_history",
            "status": "completed", "data": {"selected_feed_decision": {
                "symbol": "AAPL", "action": "sell", "decision_at": "2026-11-10T14:45:00+00:00",
                "paper_executed": True, "filled_amount_eur": 393.01,
                "reasons": ["Opgeslagen stop geraakt"]}}}]}

    front.reads = read
    message = ("Controleer deze uitgevoerde Paper-verkoop voor AAPL in de botgeschiedenis, "
               "order en portefeuille. Leg uit of de positie echt is gesloten en bied een reflectievraag aan.")
    result = asyncio.run(front.run(message=message, instructions="", conversation_context={},
        verified_asset="AAPL", locale="nl", feed_evidence=[{"source": "owner_scoped_feed",
            "facts": {"event_type": "bot_decision", "historical_notification": True,
                      "selection_origin": "current_run", "symbol": "AAPL",
                      "historical_source_observed_at": "2026-11-10T14:45:00+00:00"}}]))
    assert len(calls) == 1 and calls[0].read_tools == ("read_review_history",)
    assert "Opgeslagen stop geraakt" in result.response.text
    assert "Reflectievraag:" in result.response.text
    checked = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=message, result=result.response, locale="nl"))
    assert checked.status == "completed", (checked.reason, checked.rejection_details)


def test_clicked_paper_card_without_matching_saved_decision_never_uses_latest():
    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7,
                                   run_id="unmatched-feed-test", model_led_coach=True)

    async def read(_call):
        return {"status": "completed", "results": [{"scope": "read_review_history",
            "status": "completed", "data": {"selected_feed_decision": None,
                "latest_bot_decisions": [{"symbol": "AAPL", "action": "hold",
                    "decision_at": "2026-11-16T09:45:18+00:00"}]}}]}

    front.reads = read
    result = asyncio.run(front.run(
        message="Bespreek dit opgeslagen Paper-botbesluit voor AAPL.", instructions="",
        conversation_context={}, verified_asset="AAPL", locale="nl",
        feed_evidence=[{"source": "owner_scoped_feed", "facts": {
            "event_type": "bot_decision", "historical_notification": True,
            "selection_origin": "current_run", "symbol": "AAPL",
            "historical_event_facts": {"action": "hold"}}}],
    ))
    assert "niet aan een opgeslagen beslissing koppelen" in result.response.text
    assert "10:45" not in result.response.text


def test_clicked_paper_card_rejects_decision_from_later_source_moment():
    from backend.services.finn_v2_factual_source_answer import render_selected_paper_feed_decision
    text = render_selected_paper_feed_decision({"results": [{"scope": "read_review_history",
        "status": "completed", "data": {"selected_feed_decision": {
            "symbol": "BTC", "action": "hold", "decision_at": "2026-11-16T10:45:17+00:00",
            "paper_executed": False}}}]}, symbol="BTC",
        expected_source_at="2026-11-16T06:00:18+00:00")
    assert "hoort niet bij het bronmoment" in text
    assert "11:45" not in text


def test_clicked_paper_buy_card_keeps_verified_filled_amount():
    from backend.services.finn_v2_factual_source_answer import render_selected_paper_feed_decision
    text = render_selected_paper_feed_decision({"results": [{"scope": "read_review_history",
        "status": "completed", "data": {"selected_feed_decision": {
            "symbol": "AAPL", "action": "buy", "decision_at": "2026-11-10T14:45:00+00:00",
            "paper_executed": True, "filled_amount_eur": 393.01}}}]}, symbol="AAPL",
        expected_source_at="2026-11-10T14:45:00+00:00")
    assert "kopen (buy)" in text and "€393.01" in text


def test_legacy_houd_vast_action_is_a_selected_wait_card():
    from backend.services.finn_v2_factual_source_answer import render_selected_paper_feed_decision
    text = render_selected_paper_feed_decision({"results": [{"scope": "read_review_history",
        "status": "completed", "data": {"selected_feed_decision": {
            "symbol": "AAPL", "action": "houd_vast",
            "decision_at": "2026-11-16T06:00:18+00:00", "paper_executed": False,
            "reasons": ["Score buiten de opgeslagen koopzone"]}}}]}, symbol="AAPL")
    assert "wachten (hold)" in text
    assert "2026-11-16 07:00:18 CET" in text
    assert "Score buiten de opgeslagen koopzone" in text
    assert "Controleer vóór een volgende beoordeling" in text


def test_selected_paper_card_does_not_repeat_identical_saved_reasons():
    from backend.services.finn_v2_factual_source_answer import render_selected_paper_feed_decision
    text = render_selected_paper_feed_decision({"results": [{"scope": "read_review_history",
        "status": "completed", "data": {"selected_feed_decision": {
            "symbol": "AAPL", "action": "hold",
            "decision_at": "2026-11-16T06:00:18+00:00", "paper_executed": False,
            "reasons": ["Score buiten de koopzone.", "score buiten de koopzone", "Beurs gesloten"],
        }}}]}, symbol="AAPL")
    assert text.count("Score buiten de koopzone") == 1
    assert "Beurs gesloten" in text


def test_clicked_filled_paper_exit_offers_reflection_without_claiming_flat_position():
    from backend.services.finn_v2_factual_source_answer import render_selected_paper_feed_decision
    text = render_selected_paper_feed_decision({"results": [{"scope": "read_review_history",
        "status": "completed", "data": {"selected_feed_decision": {
            "symbol": "AAPL", "action": "sell", "decision_at": "2026-11-10T14:45:00+00:00",
            "paper_executed": True, "filled_amount_eur": 393.01,
            "reasons": ["Opgeslagen stop geraakt"]}}}]}, symbol="AAPL",
        expected_source_at="2026-11-10T14:45:00+00:00")
    assert "Opgeslagen stop geraakt" in text
    assert "niet dat de hele positie is gesloten" in text
    assert "Reflectievraag:" in text


def test_latest_btc_paper_decision_uses_the_persisted_row():
    message = ("Wat is het laatste opgeslagen besluit van mijn BTC Paper-bot? "
               "Noem actie, besluitmoment met CET/CEST en of dit een historische of actuele beoordeling is.")
    response, call = _run(message, [{"scope": "read_review_history", "status": "completed", "data": {
        "latest_bot_decisions": [
            {"symbol": "BTC", "bot_name": "BTC Paper", "is_live": False, "action": "hold",
             "persistence_status": "planned", "decision_at": "2026-10-18T07:48:54+00:00"},
            {"symbol": "BTC", "bot_name": "BTC Live", "is_live": True, "action": "buy",
             "persistence_status": "completed", "decision_at": "2026-11-13T19:00:00+00:00"},
        ],
    }}])
    assert call.read_tools == ("read_review_history",)
    assert call.inputs["_latest_bot_decisions_only"] is True
    assert "2026-10-18 09:48:54 CEST" in response.text
    assert "geen order" in response.text and "historische" in response.text
    assert "BTC Live" not in response.text


def test_short_bot_reason_rechecks_current_bot_page_after_failed_prior_turn():
    response, call = _run(
        "Wat was de exacte reden?",
        [{"scope": "read_review_history", "status": "completed", "data": {
            "latest_bot_decisions": [{
                "symbol": "AAPL", "bot_name": "AAPL Paper", "is_live": False,
                "action": "hold", "persistence_status": "planned",
                "decision_at": "2026-11-20T17:45:00+00:00",
                "safety_reason": "Opgeslagen setupvoorwaarden passen niet bij de actuele benchmark.",
            }],
        }}], verified_asset="AAPL", workspace_hints={"page": "/bot"},
    )
    assert call.inputs["_latest_bot_decisions_only"] is True
    assert "Opgeslagen setupvoorwaarden passen niet" in response.text
    assert "Welke bot" not in response.text


def test_missing_historical_botcheck_names_the_available_report():
    from backend.services.finn_v2_factual_source_answer import render_report_bot_check_comparison
    answer = render_report_bot_check_comparison({"results": [
        {"scope": "read_review_history", "status": "completed",
         "data": {"referenced_bot_decisions": []}},
        {"scope": "read_latest_report", "status": "completed",
         "data": {"generated_at": "2026-11-19T04:21:00+00:00"}},
    ]}, symbol="AAPL", message=(
        "Vergelijk mijn AAPL-botcheck op 19 november rond 10:00 CET met "
        "mijn dagrapport van 05:21 CET."))
    assert "dagrapport van 2026-11-19 05:21:00 CET" in answer
    assert "botcheck ontbreekt" in answer

    response, call = _run(
        "Vergelijk de AAPL-botcheck van 19 november 2026 rond 10:00 CET met "
        "het AAPL-dagrapport van 19 november 2026 om 05:21 CET. Welke bron "
        "heb je werkelijk? Als een bron ontbreekt, noem precies welke en "
        "vervang hem niet door een later rapport. Voer niets uit.",
        [{"scope": "read_review_history", "status": "completed",
          "data": {"referenced_bot_decisions": []}},
         {"scope": "read_latest_report", "status": "completed",
          "data": {"generated_at": "2026-11-19T04:21:00+00:00"}}],
        verified_asset="AAPL",
    )
    assert call.inputs["report_date"] == "2026-11-19"
    assert "dagrapport van 2026-11-19 05:21:00 CET" in response.text

    later = render_report_bot_check_comparison({"results": [
        {"scope": "read_review_history", "status": "completed",
         "data": {"referenced_bot_decisions": []}},
        {"scope": "read_latest_report", "status": "completed",
         "data": {"generated_at": "2026-11-19T19:08:00+00:00"}},
    ]}, symbol="AAPL", message=(
        "Vergelijk de AAPL-botcheck van 19 november 2026 rond 10:00 CET met "
        "het AAPL-dagrapport van 19 november 2026 om 05:21 CET."))
    assert "niet het genoemde uitleesmoment 05:21" in later
    assert "Het specifiek gevraagde rapport is daarmee niet geverifieerd" in later
    assert "20:08" not in later
    assert "botcheck is niet gevonden" in later


def test_report_bot_comparison_keeps_displayed_and_raw_block_reasons_distinct():
    from backend.services.finn_v2_factual_source_answer import render_report_bot_check_comparison

    answer = render_report_bot_check_comparison({"results": [
        {"scope": "read_review_history", "status": "completed", "data": {
            "referenced_bot_decisions": [{
                "bot_id": 130, "symbol": "AAPL", "action": "hold",
                "decision_at": "2026-11-21T09:15:17+00:00",
                "safety_reason": "De marktprijs is te oud voor een Paper-order.",
            }],
        }},
        {"scope": "read_latest_report", "status": "completed", "data": {
            "report_date": "2026-11-21",
            "generated_at": "2026-11-21T04:39:26+00:00",
            "score_source_snapshot": {
                "report_v2": {
                    "automation": {
                        "bots": [{
                            "bot_id": 130, "symbol": "AAPL", "latest_decision": {
                                "at": "2026-11-21T04:30:32+00:00",
                                "reason": "De marktprijs is te oud voor een Paper-order.",
                                "block_code": "market_price_stale",
                            },
                        }],
                    },
                },
            },
        }},
    ]}, symbol="AAPL", message=(
        "Vergelijk de AAPL-botbeslissing in het dagrapport van 21 november om 05:39 CET "
        "met de latere botcheck van 10:15 CET. Noem de exacte opgeslagen reden."
    ))
    assert "Het botbesluit daarin is van" in answer
    assert "05:30" in answer
    assert "Geen recente marktprijs beschikbaar voor deze beoordeling." in answer
    assert "De ruwe opgeslagen botreden in de rapportsnapshot luidt: " \
           "De marktprijs is te oud voor een Paper-order." in answer
    assert "afzonderlijke botcheck van" in answer and "10:15" in answer


def test_multi_asset_report_bot_without_report_decision_still_shows_current_check():
    from backend.services.finn_v2_factual_source_answer import render_multi_asset_report_bot_comparison

    result = {"results": [
        {"scope": "read_latest_report", "status": "completed", "data": {
            "report_date": "2026-11-21", "generated_at": "2026-11-21T04:39:26+00:00",
            "score_source_snapshot": {"report_v2": {"automation": {"bots": [
                {"bot_id": 130, "symbol": "AAPL", "is_live": False,
                 "latest_decision": None},
            ]}}},
        }},
        {"scope": "read_review_history", "status": "completed", "data": {
            "latest_bot_decisions": [
                {"bot_id": 130, "symbol": "AAPL", "is_live": False,
                 "decision_at": "2026-11-21T09:15:17+00:00",
                 "safety_reason": "Koerscontrole tijdens de latere Paper-check"},
            ],
        }},
    ]}
    answer = render_multi_asset_report_bot_comparison([result], symbols=("AAPL", "BTC"))
    assert "geen besluit in de rapportmomentopname" in answer
    assert "10:15:17 CET" in answer
    assert "Koerscontrole tijdens de latere Paper-check" in answer


def test_blocked_bot_decision_reports_safety_outcome_and_reason():
    response, _ = _run(
        "Wat is het laatste opgeslagen besluit van mijn ETH Paper-bot? "
        "Noem de veiligheidsstatus en reden.",
        [{"scope": "read_review_history", "status": "completed", "data": {
            "latest_bot_decisions": [{
                "symbol": "ETH", "bot_name": "ETH Paper", "is_live": False,
                "action": "hold", "persistence_status": "completed",
                "decision_at": "2026-11-14T22:45:00+00:00",
                "safety_state": "blocked",
                "safety_reason_code": "conversion_unavailable",
                "safety_reason": "Een recente USD/EUR-omrekening ontbreekt.",
            }],
        }}],
    )
    assert "trade geblokkeerd / geen order" in response.text
    assert "Een recente USD/EUR-omrekening ontbreekt" in response.text
    assert "geen order (hold)" not in response.text


def test_report_and_current_pair_sources_keep_separate_cet_moments():
    message = ("Vergelijk mijn dagrapport van 14 november voor BTC/EUR met de nieuwste BTC/EUR-koers. "
               "Noem apart rapportmoment, koersbron in het rapport en huidige koersbronmoment in CET, "
               "en onderscheid historisch van actueel.")
    response, call = _run(message, [
        {"scope": "read_latest_report", "status": "completed", "data": {
            "report_date": "2026-11-14", "generated_at": "2026-11-14T04:33:08+00:00",
            "score_source_snapshot": {"assets": [{"symbol": "BTC", "pair": "BTC/EUR",
                "market_snapshot": {"as_of": "2026-11-14T04:29:59+00:00"}}]},
        }},
        {"scope": "read_market_snapshot", "status": "completed", "data": {
            "symbol": "BTC", "quote_currency": "EUR", "price": 66600,
            "source_observed_at_utc": "2026-11-14T11:19:57+00:00",
        }},
    ], verified_asset="BTC")
    assert call.read_tools == ("read_latest_report", "read_market_snapshot")
    assert call.inputs["quote_currency"] == "EUR"
    assert call.inputs["report_date"] == "2026-11-14"
    assert "2026-11-14 05:33:08 CET" in response.text
    assert "2026-11-14 05:29:59 CET" in response.text
    assert "2026-11-14 12:19:57 CET" in response.text


def test_first_natural_report_indicator_question_reads_both_sources():
    message = ("In het AAPL-dagrapport staat een 50-daags gemiddelde. Leg dat naast wat "
               "Analyse nu voor dezelfde indicator kan lezen. Gaat het om een nieuwe koersdag "
               "of om een latere revisie/uitlezing van dezelfde broncandle? "
               "Noem beide waarden en de drie relevante momenten. Doe geen voorstel of wijziging.")
    response, call = _run(message, [
        {"scope": "read_latest_report", "status": "completed", "data": {
            "report_date": "2026-11-14", "generated_at": "2026-11-14T04:21:34+00:00",
            "score_source_snapshot": {"assets": [{"symbol": "AAPL", "verified_indicator_evidence": {
                "technical": {
                    "ma_50": {"value": 1.0575293, "source_observed_at": "2026-11-13T00:00:00+00:00"},
                    "rsi": {"value": 58.46, "source_observed_at": "2026-11-13T00:00:00+00:00"},
                },
            }}]},
        }},
        {"scope": "read_technical_snapshot", "status": "completed", "data": {
            "symbol": "AAPL", "read_at": "2026-11-14T13:16:23+00:00",
            "items": [
                {"indicator": "ma_50", "value": 1.0508311,
                 "source_observed_at": "2026-11-13T00:00:00+00:00"},
                {"indicator": "rsi", "value": 58.46,
                 "source_observed_at": "2026-11-13T00:00:00+00:00"},
            ],
        }},
    ], verified_asset="AAPL")
    assert call.read_tools == ("read_latest_report", "read_technical_snapshot")
    assert call.inputs["asset"] == "AAPL"
    assert "1.0575293" in response.text and "1.0508311" in response.text
    assert "2026-11-14 05:21:34 CET" in response.text
    assert "2026-11-14 14:16:23 CET" in response.text
    assert "2026-11-13 01:00:00 CET" in response.text
    assert "geen nieuwe candle" in response.text
    assert "RSI" not in response.text


def test_report_indicator_comparison_keeps_exact_pair_and_other_indicator():
    message = "Vergelijk de RSI in mijn dagrapport van 14 november voor ETH/EUR met de huidige RSI in Analyse."
    response, call = _run(message, [
        {"scope": "read_latest_report", "status": "completed", "data": {
            "report_date": "2026-11-14", "generated_at": "2026-11-14T06:00:00+00:00",
            "score_source_snapshot": {"assets": [
                {"symbol": "ETH", "pair": "ETH/USDT", "verified_indicator_evidence": {
                    "technical": {"rsi": {"value": 20, "source_observed_at": "2026-11-13T00:00:00+00:00"}}}},
                {"symbol": "ETH", "pair": "ETH/EUR", "verified_indicator_evidence": {
                    "technical": {"rsi": {"value": 30, "source_observed_at": "2026-11-13T00:00:00+00:00"}}}},
            ]},
        }},
        {"scope": "read_technical_snapshot", "status": "completed", "data": {
            "symbol": "ETH", "pair": "ETH/EUR", "read_at": "2026-11-14T10:00:00+00:00",
            "items": [{"indicator": "rsi", "value": 35,
                       "source_observed_at": "2026-11-14T00:00:00+00:00"}],
        }},
    ], verified_asset="ETH")
    assert call.inputs["quote_currency"] == "EUR"
    assert call.inputs["report_date"] == "2026-11-14"
    assert "ETH/EUR" in response.text and "RSI" in response.text
    assert "rapportwaarde 30" in response.text and "huidige uitlezing 35" in response.text
    assert "rapportwaarde 20" not in response.text
    assert "verschillende candles" in response.text


def test_report_indicator_comparison_does_not_choose_between_two_saved_pairs():
    message = "Vergelijk mijn BTC-dagrapport met de huidige RSI in Analyse."
    response, call = _run(message, [
        {"scope": "read_latest_report", "status": "completed", "data": {
            "report_date": "2026-11-14", "generated_at": "2026-11-14T06:00:00+00:00",
            "score_source_snapshot": {"assets": [
                {"symbol": "BTC", "pair": "BTC/EUR", "verified_indicator_evidence": {
                    "technical": {"rsi": {"value": 31, "source_observed_at": "2026-11-13T00:00:00+00:00"}}}},
                {"symbol": "BTC", "pair": "BTC/USDT", "verified_indicator_evidence": {
                    "technical": {"rsi": {"value": 26, "source_observed_at": "2026-11-13T00:00:00+00:00"}}}},
            ]},
        }},
        {"scope": "read_technical_snapshot", "status": "completed", "data": {
            "symbol": "BTC", "pair": "BTC/EUR", "read_at": "2026-11-14T10:00:00+00:00",
            "items": [{"indicator": "rsi", "value": 35,
                       "source_observed_at": "2026-11-14T00:00:00+00:00"}],
        }},
    ], verified_asset="BTC")
    assert call.inputs == {"asset": "BTC"}
    assert "niet eenduidig koppelen" in response.text
    assert "31" not in response.text and "26" not in response.text


def test_report_indicator_comparison_reports_only_the_missing_source():
    message = "Vergelijk de huidige AAPL RSI met die in mijn dagrapport."
    response, call = _run(message, [
        {"scope": "read_latest_report", "status": "completed", "data": {
            "report_date": "2026-11-14", "generated_at": "2026-11-14T04:21:34+00:00",
            "score_source_snapshot": {"assets": [{"symbol": "AAPL"}]},
        }},
        {"scope": "read_technical_snapshot", "status": "unavailable", "reason": "tool_timeout"},
    ], verified_asset="AAPL")
    assert call.read_tools == ("read_latest_report", "read_technical_snapshot")
    assert "huidige indicatoren: de bron reageerde niet op tijd" in response.text
    assert "dagrapport: " not in response.text


def test_report_indicator_comparison_does_not_parse_unmeasured_report_copy():
    message = "Vergelijk de huidige AAPL RSI met die in mijn dagrapport."
    response, _ = _run(message, [
        {"scope": "read_latest_report", "status": "completed", "data": {
            "report_date": "2026-11-14", "generated_at": "2026-11-14T04:21:34+00:00",
            "score_source_snapshot": {"assets": [{"symbol": "AAPL", "verified_indicator_evidence": []}]},
        }},
        {"scope": "read_technical_snapshot", "status": "completed", "data": {
            "symbol": "AAPL", "read_at": "2026-11-14T10:00:00+00:00",
            "items": [{"indicator": "rsi", "value": 58.46,
                       "source_observed_at": "2026-11-13T00:00:00+00:00"}],
        }},
    ], verified_asset="AAPL")
    assert "geen technische indicator met zowel rapport- als huidige meetwaarde" in response.text
    assert "58.46" not in response.text


def test_technical_request_detection_uses_active_indicator_catalog():
    assert mentions_technical_indicator("vergelijk MACD HIST PCT met mijn rapport")
    assert mentions_technical_indicator("50-daags gemiddelde in Analyse")
    assert not mentions_technical_indicator("vergelijk mijn rapport met de huidige koers")


def test_latest_aapl_quote_reports_friday_source_on_weekend(monkeypatch):
    import backend.services.finn_v2_factual_source_answer as factual

    class Saturday(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 14, 12, tzinfo=timezone.utc)

    monkeypatch.setattr(factual, "datetime", Saturday)
    message = "Wat is de nieuwste AAPL-koers? Noem prijs, databron, exact bronmoment in CET/CEST en beursstatus."
    response, call = _run(message, [{"scope": "read_market_snapshot", "status": "completed", "data": {
        "symbol": "AAPL", "price": 356.4, "quote_currency": "USD",
        "price_provider": "twelve_data", "source_observed_at_utc": "2026-11-13T21:00:00+00:00",
    }}], verified_asset="AAPL")
    assert call.read_tools == ("read_market_snapshot",)
    assert "356.4 USD" in response.text
    assert "2026-11-13 22:00:00 CET" in response.text
    assert "gesloten" in response.text


def test_last_available_aapl_quote_for_planning_uses_dated_market_read():
    message = ("Wat is de laatst beschikbare AAPL-koers in USD met bronmoment? "
               "Gebruik die alleen voor planning; dit is geen actuele uitvoeringskoers. "
               "Plaats geen order.")
    response, call = _run(message, [{
        "scope": "read_market_snapshot", "status": "completed", "data": {
            "symbol": "AAPL", "price": 341.92, "quote_currency": "USD",
            "source_observed_at": "2026-11-20T20:58:00+00:00",
        },
    }], verified_asset="AAPL")
    assert call.read_tools == ("read_market_snapshot",)
    assert response.answer_kind == "factual_source"
    assert "341.92 USD" in response.text
    assert "2026-11-20 21:58:00 CET" in response.text


def test_explicit_pair_quote_keeps_exact_market_currency():
    message = ("Wat is de nieuwste BTC/USDT-koers? Noem prijs, valuta en exact "
               "bronmoment in CET/CEST.")
    response, call = _run(message, [{"scope": "read_market_snapshot", "status": "completed", "data": {
        "symbol": "BTC", "quote_currency": "USDT", "price": 74000,
        "source_observed_at": "2026-11-14T11:19:57+00:00",
    }}], verified_asset="BTC")
    assert call.inputs == {"asset": "BTC", "quote_currency": "USDT"}
    assert "BTC/USDT" in response.text and "74000 USDT" in response.text
    assert "geen reguliere beurssluiting" in response.text
    assert "Amerikaanse beurssessie" not in response.text


def test_timezone_slash_does_not_obscure_eur_pair_or_two_real_pairs():
    question = ("Wat is de nieuwste BTC/EUR-koers? Noem prijs, valuta en exact "
                "bronmoment in CET/CEST.")
    assert requested_catalog_trading_pair(question) == ("BTC", "EUR")
    assert requested_catalog_trading_pair("BTC/EUR en BTC/USDT, tijden in CET/CEST") is None
    response, call = _run(question, [{"scope": "read_market_snapshot", "status": "completed", "data": {
        "symbol": "BTC", "quote_currency": "EUR", "price": 60900.05,
        "source_observed_at": "2026-11-14T11:19:57+00:00",
    }}], verified_asset="BTC")
    assert call.inputs == {"asset": "BTC", "quote_currency": "EUR"}
    assert "BTC/EUR" in response.text and "60900.05 EUR" in response.text


def test_bot_decision_with_explicit_pair_does_not_mix_pair_rows():
    message = "Wat is het laatste opgeslagen besluit van mijn BTC/USDT Paper-bot?"
    response, _ = _run(message, [{"scope": "read_review_history", "status": "completed", "data": {
        "latest_bot_decisions": [
            {"symbol": "BTC", "pair": "BTC/EUR", "bot_name": "EUR", "is_live": False,
             "action": "buy", "decision_at": "2026-11-14T10:00:00+00:00"},
            {"symbol": "BTC", "pair": "BTC/USDT", "bot_name": "USDT", "is_live": False,
             "action": "hold", "decision_at": "2026-11-14T09:00:00+00:00"},
        ],
    }}])
    assert "BTC/USDT" in response.text and "geen order" in response.text
    assert "koopbesluit" not in response.text


def test_paper_portfolio_read_time_is_not_quote_source_time():
    message = ("Wanneer heb je mijn Paper-portefeuille uitgelezen? "
               "Geef het exacte uitleesmoment in CET/CEST en leg uit of dat een koersbronmoment is.")
    response, call = _run(message, [{"scope": "read_portfolio", "status": "completed", "data": {
        "read_at": "2026-11-14T11:27:14+00:00", "valuation_as_of": "2026-11-13T21:00:00+00:00",
    }}])
    assert call.read_tools == ("read_portfolio",)
    assert "2026-11-14 12:27:14 CET" in response.text
    assert "niet het bronmoment van een koers" in response.text


def test_missing_source_names_failed_scope_without_inventing_time():
    message = "Wat is de nieuwste AAPL-koers? Noem prijs, databron, exact bronmoment in CET/CEST en beursstatus."
    response, _ = _run(message, [{"scope": "read_market_snapshot", "status": "unavailable",
                                  "reason": "tool_timeout", "data": None}])
    assert "de bron reageerde niet op tijd" in response.text
    assert "tool_timeout" not in response.text
    assert "2026" not in response.text
