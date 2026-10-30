"""Regressions for FINN's shared report fallback when provider prose is unusable."""

from backend.services import finn_unified_report_service as reports


def _context():
    return {
        "locale": "nl", "profile": {}, "observed_at": "2026-10-07T12:00:00+00:00",
        "assets": [{
            "symbol": "BTC", "setups": [{"id": 1, "name": "BTC Pullback Continuation"}],
            "strategies": [], "bots": [],
            "benchmark": {"source_status": "missing_scores", "benchmark_score": None, "matches": []},
        }],
    }


def _generate(monkeypatch, provider_result):
    async def load(_user_id):
        return _context()

    monkeypatch.setattr(reports, "_load_context", load)
    monkeypatch.setattr(reports, "ask_gpt_json", lambda **_: provider_result)
    return reports.generate_unified_daily_report_sections(7)


def test_generate_daily_report_sections_uses_owner_plan_when_ai_sections_missing(monkeypatch):
    result = _generate(monkeypatch, {})
    assert "BTC Pullback Continuation" in result["executive_summary"]
    assert "ontbreekt een complete actuele benchmark" in result["executive_summary"]
    assert "geen bevestigde setupmatch" in result["setup_validation"]
    assert result["market_score"] is None


def test_generate_daily_report_sections_replaces_weak_short_ai_sections(monkeypatch):
    weak = {
        "executive_summary": "Regime intact.", "market_analysis": "Market steady.",
        "macro_context": "Macro unchanged.", "technical_analysis": "Technicals neutral.",
        "setup_validation": "Setups selective.", "strategy_implication": "Strategy stable.",
        "bot_strategy": "Bot inactive.", "outlook": "Await confirmation.",
    }
    result = _generate(monkeypatch, weak)
    for key, value in weak.items():
        assert result[key] != value
    assert "BTC Pullback Continuation" in result["executive_summary"]


def test_daily_report_keeps_model_narrative_in_its_sections(monkeypatch):
    prose = {
        "executive_summary": "BTC heeft vandaag geen volledige actuele benchmark; bekijk eerst de ontbrekende scorebronnen.",
        "market_analysis": "Voor BTC is de marktbeoordeling nog niet compleet. De koers alleen onderbouwt geen conclusie.",
        "macro_context": "Voor BTC ontbreekt macro bewijs; de huidige context kan daarom nog niet worden beoordeeld.",
        "technical_analysis": "De technische gegevens voor BTC zijn nog onvolledig; timing blijft daarmee onzeker.",
        "setup_validation": "De opgeslagen BTC Pullback Continuation kan zonder complete benchmark nog niet worden beoordeeld.",
        "strategy_implication": "Er is nog geen gekoppelde strategie; bepaal eerst welke uitvoering bij dit plan hoort.",
        "bot_strategy": "Er is geen gekoppelde bot en er is geen aankoop uit deze gegevens af te leiden.",
        "outlook": "Controleer de ontbrekende indicatorbronnen voordat je dit plan opnieuw beoordeelt.",
    }
    result = _generate(monkeypatch, prose)
    for section, text in prose.items():
        assert result[section] == text


def test_complete_scores_outside_setup_bounds_do_not_become_missing_benchmark(monkeypatch):
    context = {
        "locale": "nl", "profile": {}, "observed_at": "2026-10-11T12:00:00+00:00",
        "assets": [{
            "symbol": "ETH", "setups": [{"id": 9, "name": "ETH Plan"}],
            "strategies": [], "bots": [],
            "benchmark": {
                "source_status": "available", "benchmark_score": 33.3,
                "reported_scores": {
                    "market_score": 30, "macro_score": 20, "technical_score": 50,
                },
                "component_source_status": {
                    "market_score": "fresh", "macro_score": "fresh", "technical_score": "fresh",
                },
                "matches": [{
                    "setup_id": 9, "name": "ETH Plan", "symbol": "ETH",
                    "status": "outside_conditions", "score": 67, "is_active": False,
                }],
            },
        }],
    }

    async def load(_user_id):
        return context

    monkeypatch.setattr(reports, "_load_context", load)
    monkeypatch.setattr(reports, "ask_gpt_json", lambda **_: {
        "setup_validation": "Er is zonder complete actuele benchmark geen match.",
    })

    result = reports.generate_unified_daily_report_sections(7)

    assert result["market_score"] == 30
    assert result["macro_score"] == 20
    assert result["technical_score"] == 50
    assert "buiten hun scorevoorwaarden" in result["setup_validation"]
    assert "zonder complete" not in result["setup_validation"]


def test_missing_benchmark_does_not_publish_a_setup_proximity_score(monkeypatch):
    context = _context()
    context["assets"][0]["benchmark"]["benchmark_score"] = 55
    context["assets"][0]["benchmark"]["matches"] = [{
        "setup_id": 1, "name": "BTC Pullback Continuation", "symbol": "BTC",
        "status": "insufficient_data", "score": 0, "is_active": False,
    }]

    async def load(_user_id):
        return context

    monkeypatch.setattr(reports, "_load_context", load)
    monkeypatch.setattr(reports, "ask_gpt_json", lambda **_: {})

    result = reports.generate_unified_daily_report_sections(7)
    assert result["watchlist"][0]["benchmark"]["benchmark_score"] is None
    assert result["top_setups"][0]["score"] is None
    assert result["setup_score"] is None
