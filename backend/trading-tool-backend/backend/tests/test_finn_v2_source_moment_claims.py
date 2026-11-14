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
