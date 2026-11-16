import asyncio
from datetime import datetime, timezone

from backend.services.finn_v2_responses_front_door import FinnResponsesFrontDoor
from backend.services.finn_v2_responses_answer_verifier import FinnResponsesAnswerVerifier
from backend.services.finn_v2_factual_source_answer import (
    mentions_technical_indicator, render_bot_decision, render_closed_paper_exit_facts,
)
from backend.services.asset_catalog_service import requested_catalog_trading_pair


def _run(message, results, *, verified_asset=None):
    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7,
                                   run_id="factual-source-test", model_led_coach=True)
    calls = []

    async def read(call):
        calls.append(call)
        return {"status": "completed", "results": results}

    front.reads = read
    prepared = asyncio.run(front.run(
        message=message, instructions="", conversation_context={},
        verified_asset=verified_asset, locale="nl",
    ))
    assert len(calls) == 1
    checked = asyncio.run(FinnResponsesAnswerVerifier().verify(message=message, result=prepared.response, locale="nl"))
    assert checked.status == "completed", (checked.reason, checked.rejection_details)
    assert checked.text == prepared.response.text
    return prepared.response, calls[0]


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
            "decision_at": "2026-11-16T06:00:18+00:00", "paper_executed": False}}}]}, symbol="AAPL")
    assert "wachten (hold)" in text
    assert "2026-11-16 07:00:18 CET" in text


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
