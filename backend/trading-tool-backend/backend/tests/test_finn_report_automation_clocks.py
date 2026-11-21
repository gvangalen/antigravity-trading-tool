from backend.services.finn_unified_report_service import (
    _report_automation_clocks_supported, _report_automation_evidence,
    _report_v2_contradicts_facts,
    _report_v2_factual_fallbacks,
)


def _status(symbol="BTC", bot_id=129):
    return {"bots": [{"bot_id": bot_id, "symbol": symbol,
                      "latest_decision": {"at": "2026-11-16T04:15:18"}}]}


def test_report_bot_decision_has_explicit_utc_and_amsterdam_clocks():
    evidence = _report_automation_evidence(_status())
    decision = evidence["bots"][0]["latest_decision"]
    assert decision["at"] == "2026-11-16T04:15:18+00:00"
    assert decision["at_amsterdam"] == "2026-11-16 05:15:18 CET"


def test_report_automation_rejects_unzoned_or_wrong_bot_clock():
    status = _status()
    assert not _report_automation_clocks_supported(
        "De BTC-bot is beoordeeld op 16 november om 04:15.", status,
    )
    assert not _report_automation_clocks_supported(
        "De BTC-bot is beoordeeld op 16 november om 04:15 CET.", status,
    )
    assert _report_automation_clocks_supported(
        "De BTC-bot is beoordeeld op 16 november om 05:15 CET.", status,
    )
    assert _report_automation_clocks_supported(
        "Bot 129 kreeg een besluit op 16 november om 04:15 UTC.", status,
    )


def test_report_automation_matches_another_asset_to_its_own_decision():
    status = {"bots": [*_status()["bots"],
                       {"bot_id": 130, "symbol": "AAPL",
                        "latest_decision": {"at": "2026-11-16T08:45:00+00:00"}}]}
    assert not _report_automation_clocks_supported(
        "De AAPL-bot is beoordeeld om 05:15 CET.", status,
    )
    assert _report_automation_clocks_supported(
        "De AAPL-bot is beoordeeld om 09:45 CET.", status,
    )


def test_report_validation_replaces_wrong_automation_clock():
    context = {"report_bot_status": _status()}
    assert _report_v2_contradicts_facts(
        "automation", "De BTC-bot kreeg een beoordeling om 04:15 CET.",
        {"assets": []}, context, {},
    )
    assert not _report_v2_contradicts_facts(
        "automation", "De BTC-bot kreeg een beoordeling om 05:15 CET.",
        {"assets": []}, context, {},
    )


def test_report_fallback_keeps_verified_bot_time_visible():
    text = _report_v2_factual_fallbacks(
        {"locale": "nl", "report_bot_status": _status(), "report_portfolios": {}},
        {"assets": []}, {"period": "daily"}, "nl",
    )["automation"]
    assert "BTC" in text
    assert "2026-11-16 05:15:18 CET" in text
    assert "04:15" not in text
    assert "beslissing in deze rapportmomentopname" in text
