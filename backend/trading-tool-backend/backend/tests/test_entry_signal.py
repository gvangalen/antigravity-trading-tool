from datetime import datetime, timedelta, timezone

import pytest

from backend.domain.entry_signal import evaluate_entry_signal, explicit_entry_signal_from_text, validate_entry_signal


NOW = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)


def rule(reference=None, direction="above"):
    return {
        "version": 1,
        "event": "close_crosses_reference",
        "direction": direction,
        "timeframe": "1D",
        "reference": reference or {"kind": "sma", "period": 2},
    }


def candles(values):
    start = datetime(2026, 10, 30, 23, 59, 59, tzinfo=timezone.utc)
    return [
        {"at": (start + timedelta(days=index)).isoformat(), "close": value}
        for index, value in enumerate(values)
    ]


def test_sma_crossing_requires_closed_pair_candles_and_is_stable():
    evidence = evaluate_entry_signal(rule(), candles([10, 10, 12]), market_id=7, now=NOW)
    assert evidence["status"] == "triggered"
    assert evidence["rule"] == rule()
    assert evidence["market_id"] == 7
    assert evidence["signal_key"] == evaluate_entry_signal(
        rule(), candles([10, 10, 12]), market_id=7, now=NOW,
    )["signal_key"]
    assert evidence["signal_key"] != evaluate_entry_signal(
        rule(), candles([10, 10, 12]), market_id=8, now=NOW,
    )["signal_key"]
    assert evidence["signal_key"] != evaluate_entry_signal(
        rule(), candles([10, 9, 12]), market_id=7, now=NOW,
    )["signal_key"]


def test_no_cross_missing_and_stale_evidence_hold():
    assert evaluate_entry_signal(rule(), candles([10, 11]), market_id=7, now=NOW)["status"] == "insufficient_closed_candles"
    assert evaluate_entry_signal(rule(), candles([9, 10, 11]), market_id=7, now=NOW)["status"] == "not_triggered"
    assert evaluate_entry_signal(
        rule(), candles([10, 10, 12]), market_id=7, now=NOW + timedelta(days=4),
    )["status"] == "closed_candle_stale_or_unconfirmed"


def test_trendline_cross_and_invalid_rule():
    anchor_times = [candles([10, 10])[index]["at"] for index in (0, 1)]
    line = rule({"kind": "trendline", "anchors": [
        {"at": anchor_times[0], "price": 10},
        {"at": anchor_times[1], "price": 10},
    ]})
    assert evaluate_entry_signal(line, candles([10, 10, 12]), market_id=7, now=NOW)["status"] == "triggered"
    with pytest.raises(ValueError):
        validate_entry_signal(rule({"kind": "sma", "period": 220}))
    with pytest.raises(ValueError):
        validate_entry_signal({**rule(), "unexpected": True})


def test_missing_daily_candle_or_older_latest_candle_cannot_trigger():
    missing_day = candles([10, 10, 12])
    missing_day[0]["at"] = (datetime.fromisoformat(missing_day[0]["at"]) - timedelta(days=1)).isoformat()
    assert evaluate_entry_signal(rule(), missing_day, market_id=7, now=NOW)["status"] == "missing_closed_candle_days"
    older = candles([10, 10, 12])
    assert evaluate_entry_signal(rule(), older, market_id=7, now=NOW + timedelta(days=1))["status"] == "closed_candle_stale_or_unconfirmed"


def test_explicit_crossing_is_preserved_even_when_name_repeats_sma_period():
    assert explicit_entry_signal_from_text(
        "Koop €10 alleen wanneer een afgesloten dagcandle van BTC/EUR de SMA over "
        "50 afgesloten dagcandles van onder naar boven kruist."
    ) == rule({"kind": "sma", "period": 50})
    message = (
        "Maak SMA50 Kruising QA. Als extra instapvoorwaarde moet de afgesloten "
        "dagkoers de SMA50 van onder naar boven kruisen."
    )
    assert explicit_entry_signal_from_text(message) == rule({"kind": "sma", "period": 50})
    assert explicit_entry_signal_from_text(
        "Extra getypeerde instapregel: alleen als de afgesloten 1D-slotkoers van "
        "BTC/EUR de SMA50 van onder naar boven kruist."
    ) == rule({"kind": "sma", "period": 50})
    assert explicit_entry_signal_from_text(
        "Koop wanneer de afgesloten dagkoers de SMA200 van boven naar onder kruist."
    ) == rule({"kind": "sma", "period": 200}, direction="below")
    assert explicit_entry_signal_from_text(
        "Koop pas als de afgesloten dagkoers SMA34 opwaarts kruist."
    ) == rule({"kind": "sma", "period": 34})
    assert explicit_entry_signal_from_text(
        "Verkoop als de afgesloten dagkoers neerwaarts de SMA34 kruist."
    ) == rule({"kind": "sma", "period": 34}, direction="below")


def test_ambiguous_crossing_is_not_silently_interpreted_as_fixed_price():
    assert explicit_entry_signal_from_text("Koop als de koers SMA50 kruist.") is None
    assert explicit_entry_signal_from_text(
        "Koop als de afgesloten dagkoers SMA50 of SMA200 van onder naar boven kruist."
    ) is None
    line = explicit_entry_signal_from_text(
        "De afgesloten dagkoers kruist de trendlijn van onder naar boven; "
        "ankers 2026-10-01 70000 en 2026-10-20 76000."
    )
    assert line["reference"]["kind"] == "trendline"
    assert [point["price"] for point in line["reference"]["anchors"]] == [70000.0, 76000.0]


def test_explicit_trendline_with_utc_times_and_localized_prices():
    line = explicit_entry_signal_from_text(
        "De afgesloten 1D-slotkoers kruist opwaarts door de trendlijn met punten "
        "2026-09-01 00:00 UTC op €50.000 en 2026-10-01 00:00 UTC op €55.000."
    )
    assert line == rule({"kind": "trendline", "anchors": [
        {"at": "2026-09-01T00:00:00+00:00", "price": 50000.0},
        {"at": "2026-10-01T00:00:00+00:00", "price": 55000.0},
    ]})


def test_explicit_trendline_preserves_nonmidnight_utc_anchors():
    line = explicit_entry_signal_from_text(
        "De afgesloten dagkoers kruist de trendlijn van onder naar boven; "
        "ankers 2026-09-01 14:30 UTC op 50000 en 2026-10-01 16:45 UTC op 55000."
    )
    assert line["reference"]["anchors"] == [
        {"at": "2026-09-01T14:30:00+00:00", "price": 50000.0},
        {"at": "2026-10-01T16:45:00+00:00", "price": 55000.0},
    ]
    assert explicit_entry_signal_from_text(
        "De afgesloten dagkoers kruist de trendlijn van onder naar boven; "
        "ankers 2026-09-01 14:30 op 50000 en 2026-10-01 16:45 op 55000."
    ) is None
