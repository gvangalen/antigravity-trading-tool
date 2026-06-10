from backend.ai_agents import report_ai_agent as report_module


def _seed_report_context(monkeypatch):
    monkeypatch.setattr(
        report_module,
        "get_watchlist_summary",
        lambda user_id: [
            {
                "symbol": "BTC",
                "scores": {"technical_score": 63, "market_score": 42, "setup_score": 68},
                "top_indicators": [{"indicator": "RSI", "score": 61}],
            },
            {
                "symbol": "ETH",
                "scores": {"technical_score": 58, "market_score": 39, "setup_score": 55},
                "top_indicators": [{"indicator": "MACD", "score": 54}],
            },
        ],
    )
    monkeypatch.setattr(
        report_module,
        "get_daily_scores",
        lambda user_id: {
            "macro_score": 52,
            "technical_score": 63,
            "market_score": 42,
            "setup_score": 68,
        },
    )
    monkeypatch.setattr(
        report_module,
        "get_market_snapshot",
        lambda: {"price": 61471, "change_24h": -2.03, "volume": 38575067935},
    )
    monkeypatch.setattr(
        report_module,
        "get_market_indicator_highlights",
        lambda user_id: [{"indicator": "Market Breadth", "score": 44, "interpretation": "breedte blijft achter bij de headlineprijs"}],
    )
    monkeypatch.setattr(
        report_module,
        "get_macro_indicator_highlights",
        lambda user_id: [{"indicator": "DXY", "score": 49, "interpretation": "macro geeft geen nieuwe risicoversnelling"}],
    )
    monkeypatch.setattr(
        report_module,
        "get_technical_indicator_highlights",
        lambda user_id: [{"indicator": "RSI", "score": 61, "interpretation": "momentum herstelt maar nog zonder brede expansie"}],
    )
    monkeypatch.setattr(
        report_module,
        "get_setup_snapshot",
        lambda user_id: {
            "best_setup": {
                "id": 1,
                "name": "BTC Pullback Continuation",
                "symbol": "BTC",
                "timeframe": "1D",
                "score": 68,
            },
            "top_setups": [{"id": 1, "name": "BTC Pullback Continuation", "score": 68}],
        },
    )
    monkeypatch.setattr(
        report_module,
        "get_active_strategy_snapshot",
        lambda user_id: {
            "setup_name": "BTC Pullback Continuation",
            "symbol": "BTC",
            "timeframe": "1D",
            "entry": 61000,
            "targets": None,
            "stop_loss": 59800,
            "adjustment_reason": "watch momentum",
            "confidence_score": 64,
        },
    )
    monkeypatch.setattr(
        report_module,
        "get_bot_daily_snapshot",
        lambda user_id: {
            "bot_name": "Finn Bot",
            "action": "hold",
            "confidence": None,
            "amount_eur": None,
            "setup_match": "BTC Pullback Continuation",
            "reason": "conditions not met",
        },
    )
    monkeypatch.setattr(
        report_module,
        "get_portfolio_health_snapshot",
        lambda user_id: {
            "equity_eur": 12500,
            "cash_eur": 5000,
            "invested_eur": 7500,
            "unrealized_pnl_eur": 120,
        },
    )
    monkeypatch.setattr(
        report_module,
        "get_daily_deltas",
        lambda user_id: {"market_delta": -3.0, "technical_delta": 1.0, "macro_delta": 0.0},
    )
    monkeypatch.setattr(report_module, "get_regime_memory", lambda user_id: {"label": "trading_range", "confidence": 61})
    monkeypatch.setattr(report_module, "compute_transition_detector", lambda user_id: {"state": "range-to-trend watch"})


def test_generate_daily_report_sections_uses_rich_fallbacks_when_ai_sections_missing(monkeypatch):
    _seed_report_context(monkeypatch)
    monkeypatch.setattr(report_module, "ask_gpt_json", lambda **kwargs: {})

    result = report_module.generate_daily_report_sections(user_id=7)

    assert result["executive_summary"] != "Regime intact."
    assert "BTC Pullback Continuation" in result["executive_summary"]
    assert "24-uurs" in result["executive_summary"]
    assert result["market_analysis"] != "Market steady."
    assert "38.575.067.935" in result["market_analysis"]
    assert result["outlook"] != "Await confirmation."


def test_generate_daily_report_sections_replaces_weak_short_ai_sections_with_contextual_fallbacks(monkeypatch):
    _seed_report_context(monkeypatch)
    monkeypatch.setattr(
        report_module,
        "ask_gpt_json",
        lambda **kwargs: {
            "executive_summary": "Regime intact.",
            "market_analysis": "Market steady.",
            "macro_context": "Macro unchanged.",
            "technical_analysis": "Technicals neutral.",
            "setup_validation": "Setups selective.",
            "strategy_implication": "Strategy stable.",
            "bot_strategy": "Bot inactive.",
            "outlook": "Await confirmation.",
        },
    )

    result = report_module.generate_daily_report_sections(user_id=7)

    assert "Regime intact." not in result["executive_summary"]
    assert "Market steady." not in result["market_analysis"]
    assert "Macro unchanged." not in result["macro_context"]
    assert "Technicals neutral." not in result["technical_analysis"]
    assert "Setups selective." not in result["setup_validation"]
    assert "Strategy stable." not in result["strategy_implication"]
    assert "Bot inactive." not in result["bot_strategy"]
    assert "Await confirmation." not in result["outlook"]
