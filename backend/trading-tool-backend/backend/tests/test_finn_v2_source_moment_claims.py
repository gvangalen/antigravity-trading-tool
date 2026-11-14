from backend.services.finn_v2_source_moment_claims import current_source_moments_supported
from backend.services.finn_v2_run_service import _minimal_read_answer
from types import SimpleNamespace


def _evidence():
    return (
        {"scope": "read_market_snapshot", "status": "completed", "data": {
            "symbol": "AAPL", "quote_currency": "USD", "price": 356.17,
            "source_observed_at_utc": "2026-11-13T20:59:00+00:00",
        }},
        {"scope": "read_market_snapshot", "status": "completed", "data": {
            "symbol": "BTC", "quote_currency": "USDT", "price": 74968,
            "source_observed_at_utc": "2026-11-13T20:55:01+00:00",
        }},
        {"scope": "read_portfolio", "status": "completed", "data": {
            "read_at": "2026-11-13T21:03:00+00:00",
        }},
    )


def test_multi_asset_quote_table_requires_the_current_source_for_each_row():
    answer = (
        "| Instrument | Benchmark | Koersbronmoment |\n"
        "| AAPL | 52,7 | 13 november 2026, 20:59 UTC |\n"
        "| BTC/USDT | 35,0 | 13 november 2026, 21:55:01 CET |"
    )
    assert current_source_moments_supported(answer, _evidence())
    assert not current_source_moments_supported(
        answer.replace("20:59 UTC", "20:44 UTC"), _evidence(),
    )
    assert not current_source_moments_supported(answer, _evidence()[1:])


def test_live_four_column_comparison_cannot_use_an_old_aapl_source():
    answer = (
        "| Instrument | Markt / macro / techniek | Benchmark | Koersbronmoment | "
        "| BTC/USDT | 50 / 20 / 35 | 35,0 | 13 november 2026, 20:55:01 UTC | "
        "| AAPL | 80 / 20 / 58 | 52,7 | 13 november 2026, 20:44 UTC |"
    )
    assert not current_source_moments_supported(answer, _evidence())
    assert current_source_moments_supported(
        answer.replace("20:44 UTC", "21:59 CET"), _evidence(),
    )


def test_portfolio_read_time_must_convert_cet_and_utc_from_one_instant():
    correct = "De verse Paper-portefeuille-uitlezing van 13 november 2026 om 22:03 CET toont €10.005,45."
    assert current_source_moments_supported(correct, _evidence())
    assert current_source_moments_supported(
        correct.replace("22:03 CET", "21:03 UTC"), _evidence(),
    )
    assert not current_source_moments_supported(
        correct.replace("22:03 CET", "22:03 UTC"), _evidence(),
    )
    assert not current_source_moments_supported(
        correct.replace("van 13 november", "op 13 november").replace("22:03 CET", "22:03 UTC"),
        _evidence(),
    )
    assert not current_source_moments_supported(
        "De actuele portefeuille is opgehaald op 13 nov 2026, 22:03 UTC.", _evidence(),
    )
    assert current_source_moments_supported(
        "De actuele portefeuille is opgehaald op 13 nov 2026, 22:03 CET.", _evidence(),
    )


def test_summer_and_winter_labels_are_checked_against_amsterdam_zone():
    summer = ({"scope": "read_portfolio", "status": "completed",
               "data": {"read_at": "2026-07-01T12:00:00+00:00"}},)
    assert current_source_moments_supported(
        "De actuele Paper-portefeuille-snapshot van 1 juli 2026 om 14:00 CEST is geladen.",
        summer,
    )
    assert not current_source_moments_supported(
        "De actuele Paper-portefeuille-snapshot van 1 juli 2026 om 14:00 CET is geladen.",
        summer,
    )


def test_historical_report_moment_remains_separate_from_current_read():
    answer = (
        "Het oude dagrapport noemt 9 november 2026 om 19:03 UTC. "
        "De verse Paper-portefeuille-uitlezing van 13 november 2026 om 22:03 CET toont geen posities."
    )
    assert current_source_moments_supported(answer, _evidence())
    assert not current_source_moments_supported(
        "Vergeleken met het oude dagrapport toont de verse Paper-portefeuille-uitlezing "
        "van 13 november 2026 om 22:03 UTC geen posities.", _evidence(),
    )


def test_live_report_generation_utc_and_cet_must_be_the_same_instant():
    report = ({"scope": "read_latest_report", "status": "completed", "data": {
        "report_date": "2026-11-14", "generated_at": "2026-11-14T04:33:08+00:00",
    }},)
    wrong = ("Het dagrapport werd gegenereerd om 04:33:08 UTC "
             "(04:33:08 in Europe/Amsterdam, CET).")
    assert not current_source_moments_supported(wrong, report)
    assert current_source_moments_supported(
        wrong.replace("(04:33:08 in", "(05:33:08 in"), report,
    )
    assert not current_source_moments_supported(
        "Rapport opgesteld: 14 november 2026, 04:33 CET.", report,
    )
    assert current_source_moments_supported(
        "Rapport opgesteld: 14 november 2026, 05:33 CET.", report,
    )
    assert current_source_moments_supported(
        "Het dagrapport is gegenereerd om 05:33:08 CET en de BTC/EUR-koersbron "
        "daarin was 04:29:59 UTC.", report,
    )
    assert current_source_moments_supported(
        "Het dagrapport is gegenereerd om 04:33:08 UTC en de BTC/EUR-koersbron "
        "daarin was 05:29:59 CET.", report,
    )
    assert current_source_moments_supported(
        "Het dagrapport werd gegenereerd met de koersbron van 04:29:59 UTC.", report,
    )
    assert current_source_moments_supported(
        "Het dagrapport werd gegenereerd om 05:33:08 CET "
        "(koersbron BTC/EUR 04:29:59 UTC).", report,
    )


def test_report_generation_uses_ce_st_in_summer():
    report = ({"scope": "read_latest_report", "status": "completed", "data": {
        "generated_at": "2026-07-14T04:33:08+00:00",
    }},)
    assert current_source_moments_supported(
        "Rapport opgesteld om 06:33:08 CEST.", report,
    )
    assert not current_source_moments_supported(
        "Rapport opgesteld om 05:33:08 CET.", report,
    )


def test_current_market_source_in_prose_requires_the_matching_quote_read():
    wrong = "Het nieuwste AAPL-koersbronmoment is 13 november 2026 om 20:44 UTC."
    assert not current_source_moments_supported(wrong, _evidence())
    assert current_source_moments_supported(
        wrong.replace("20:44 UTC", "21:59 CET"), _evidence(),
    )
    assert not current_source_moments_supported(
        wrong.replace("20:44 UTC", "20:59 UTC"), _evidence()[1:],
    )
    historical = "Het laatste AAPL-koersbronmoment in het oude dagrapport was 9 november 2026 om 19:03 UTC."
    assert current_source_moments_supported(historical, _evidence())
    assert current_source_moments_supported(
        "In het oude dagrapport was het laatste AAPL-koersbronmoment 9 november 2026 om 19:03 UTC.",
        _evidence(),
    )
    assert current_source_moments_supported(
        "Het nieuwste koersbronmoment is 13 november 2026 om 20:59 UTC.",
        _evidence()[:1],
    )


def test_live_latest_aapl_quote_rejects_wrong_parenthesized_source_day():
    evidence = ({"scope": "read_market_snapshot", "status": "completed", "data": {
        "symbol": "AAPL", "quote_currency": "USD", "price": 356.4,
        "source_observed_at_utc": "2026-11-13T21:00:00+00:00",
    }},)
    question = (
        "Wat is de nieuwste beschikbare AAPL-koers? Noem uitsluitend prijs, "
        "databron, exact bronmoment in Europe/Amsterdam en of de beurs nu open is."
    )
    wrong = "$356,40 USD · Twelve Data · 14 november 2026, 22:00:00 CET " \
            "(Europe/Amsterdam) · Beurs nu: gesloten."
    assert not current_source_moments_supported(wrong, evidence, question=question)
    assert not current_source_moments_supported(
        "$356,40 USD. Twelve Data · 14 november 2026, 22:00:00 CET.",
        evidence, question=question,
    )
    assert not current_source_moments_supported(
        "AAPL: $356,40 USD. Bron: Twelve Data. Gemeten: 14 november 2026, 22:00:00 CET.",
        evidence, question=question,
    )
    assert current_source_moments_supported(
        wrong.replace("14 november", "13 november"), evidence, question=question,
    )
    assert current_source_moments_supported(
        "In het oude dagrapport was de laatste AAPL-koers $356,40 USD "
        "op 9 november 2026 om 22:00 CET.", evidence, question=question,
    )
    assert current_source_moments_supported(
        "De laatste AAPL-koers in het dagrapport was $350 USD "
        "op 9 november 2026 om 22:00 CET.", evidence, question=question,
    )
    assert current_source_moments_supported(
        "Het dagrapport bevatte een oudere AAPL-koers van $350 USD op "
        "9 november 2026 om 22:00 CET. Het plan is bijgewerkt op "
        "14 november 2026 om 08:00 CET.", evidence, question=question,
    )
    assert current_source_moments_supported(
        "Het dagrapport bevatte een oudere AAPL-koers van $350 USD op "
        "9 november 2026 om 22:00 CET. De analyse is aangemaakt op "
        "14 november 2026 om 08:00 CET.", evidence, question=question,
    )
    assert not current_source_moments_supported(
        "Het dagrapport is historisch, maar de nieuwste AAPL-koers is "
        "$356,40 USD · Twelve Data · 14 november 2026, 22:00 CET.",
        evidence, question=question,
    )
    assert not current_source_moments_supported(
        "In het rapport staat een oudere koers; de actuele AAPL-koers is "
        "$356,40 USD · Twelve Data · 14 november 2026, 22:00 CET.",
        evidence, question=question,
    )
    assert not current_source_moments_supported(
        "Het dagrapport is historisch en de nieuwste AAPL-koers is "
        "$356,40 USD · Twelve Data · 14 november 2026, 22:00 CET.",
        evidence, question=question,
    )
    assert not current_source_moments_supported(
        "Het dagrapport is historisch en de laatste AAPL-koers is "
        "$356,40 USD · Twelve Data · 14 november 2026, 22:00 CET.",
        evidence, question=question,
    )
    assert not current_source_moments_supported(
        "De nieuwste AAPL-koers is $356,40 USD op 14 november 2026 om "
        "22:00 CET en het oude rapport toont een andere koers.",
        evidence, question=question,
    )
    prepared = SimpleNamespace(
        response=SimpleNamespace(
            text=wrong,
            tool_trace=({"name": "get_market_snapshot", "result": {"results": list(evidence)}},),
            uses_previous_response=False,
        ),
        previous_response=None,
    )
    rejected = _minimal_read_answer(message=question, prepared=prepared)
    assert rejected.status == "unavailable"
    assert rejected.reason == "source_moment_conflicts_with_source"


def test_current_market_source_in_prose_keeps_exact_quote_pair():
    evidence = (
        {"scope": "read_market_snapshot", "status": "completed", "data": {
            "symbol": "BTC", "quote_currency": "EUR", "price": 66732,
            "source_observed_at_utc": "2026-11-13T20:59:00+00:00",
        }},
        {"scope": "read_market_snapshot", "status": "completed", "data": {
            "symbol": "BTC", "quote_currency": "USDT", "price": 74968,
            "source_observed_at_utc": "2026-11-13T20:44:00+00:00",
        }},
    )
    assert current_source_moments_supported(
        "Het nieuwste BTC/USDT-koersbronmoment is 13 november 2026 om 20:44 UTC.", evidence,
    )
    assert not current_source_moments_supported(
        "Het nieuwste BTC/USDT-koersbronmoment is 13 november 2026 om 20:59 UTC.", evidence,
    )
    assert not current_source_moments_supported(
        "Het nieuwste bronmoment van BTC/USDT is 13 november 2026 om 20:59 UTC.", evidence,
    )
    assert not current_source_moments_supported(
        "Het nieuwste BTC/USDT-koersbronmoment is 13 november 2026 om 20:59 UTC.",
        evidence[:1],
    )


def test_unrelated_second_table_is_not_treated_as_a_quote_source_table():
    answer = (
        "| Instrument | Benchmark | Koersbronmoment |\n"
        "| AAPL | 52,7 | 13 nov 2026, 21:59 CET |\n\n"
        "| Asset | Type | Status |\n"
        "| AAPL | aandeel | actief |"
    )
    assert current_source_moments_supported(answer, _evidence())
    assert current_source_moments_supported(answer.replace("\n\n", " "), _evidence())


def test_live_read_answer_rejects_wrong_zone_before_delivery():
    text = "De verse Paper-portefeuille-uitlezing van 13 november 2026 om 22:03 UTC toont €10.005,45."
    prepared = SimpleNamespace(
        response=SimpleNamespace(
            text=text,
            tool_trace=({"name": "get_portfolio", "result": {"results": list(_evidence())}},),
            uses_previous_response=False,
        ),
        previous_response=None,
    )
    rejected = _minimal_read_answer(message="Hoe staat mijn Paper-kas?", prepared=prepared)
    assert rejected.status == "unavailable"
    assert rejected.reason == "source_moment_conflicts_with_source"
