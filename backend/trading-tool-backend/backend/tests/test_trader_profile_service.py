from backend.services.trader_profile_service import build_trader_profile_context


def test_build_trader_profile_context_uses_missing_profile_fallback():
    context = build_trader_profile_context({}, request_context={"page": "/dashboard"}, query="Leg dit uit")

    assert context["trader_profile_used"] is False
    assert context["profile_match_mode"] == "profile_missing_fallback"
    assert context["profile_conflict_detected"] is False


def test_build_trader_profile_context_marks_mixed_profile_page_context_priority():
    context = build_trader_profile_context(
        {
            "trader_types": ["investor", "swing_trader"],
            "primary_timeframes": ["4h", "1d"],
        },
        request_context={"page": "/setup", "setup_timeframe": "4h"},
        query="Is dit een goede swing entry?",
    )

    assert context["trader_profile_used"] is True
    assert context["profile_match_mode"] == "mixed_profile_page_context_priority"
    assert context["profile_conflict_detected"] is False


def test_build_trader_profile_context_detects_profile_conflict_for_intraday_request():
    context = build_trader_profile_context(
        {
            "trader_types": ["investor", "dca_investor"],
            "primary_timeframes": ["1w"],
        },
        request_context={"page": "/dashboard", "timeframe": "15m"},
        query="Kan ik dit intraday traden?",
    )

    assert context["trader_profile_used"] is True
    assert context["profile_match_mode"] == "mixed_profile_page_context_priority"
    assert context["profile_conflict_detected"] is True
