from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
FRONTEND_ROOT = REPO_ROOT / "frontend" / "trading-tool-frontend"
BACKEND_ROOT = REPO_ROOT / "backend" / "trading-tool-backend" / "backend"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_market_macro_technical_routes_no_longer_force_asset_redirect():
    market_page = _read(FRONTEND_ROOT / "app" / "(protected)" / "market" / "page.jsx")
    macro_page = _read(FRONTEND_ROOT / "app" / "(protected)" / "macro" / "page.jsx")
    technical_page = _read(FRONTEND_ROOT / "app" / "(protected)" / "technical" / "page.jsx")

    assert "canonicalizeLegacy" not in market_page
    assert "canonicalizeLegacy" not in macro_page
    assert "canonicalizeLegacy" not in technical_page


def test_legacy_assistant_events_route_is_retired_in_favor_of_coach_feed():
    main_source = _read(BACKEND_ROOT / "main.py")
    assistant_source = _read(FRONTEND_ROOT / "components" / "ui" / "AIAssistant.jsx")
    coach_feed_source = _read(FRONTEND_ROOT / "components" / "finn" / "FinnCoachFeed.jsx")

    assert "intelligence_event_api" not in main_source
    assert "useIntelligenceEvents" not in assistant_source
    assert "/api/assistant/feed?history=" in coach_feed_source


def test_retired_market_intelligence_and_mission_control_routes_are_absent():
    assistant_source = _read(BACKEND_ROOT / "api" / "ai_assistant_api.py")
    market_source = _read(BACKEND_ROOT / "api" / "market_intelligence_api.py")

    assert not (BACKEND_ROOT / "services" / "intelligence_service.py").exists()
    assert '"/market/intelligence"' not in market_source
    assert '"/assistant/mission-control"' not in assistant_source
    assert "_mission_control_cache" not in assistant_source
