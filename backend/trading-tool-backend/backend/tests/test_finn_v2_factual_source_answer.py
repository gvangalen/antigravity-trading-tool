import asyncio
from datetime import datetime, timezone

from backend.services.finn_v2_responses_front_door import FinnResponsesFrontDoor
from backend.services.finn_v2_responses_answer_verifier import FinnResponsesAnswerVerifier
from backend.services.finn_v2_factual_source_answer import mentions_technical_indicator
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
