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


def test_assistant_events_get_is_read_only_and_refresh_is_explicit():
    source = _read(BACKEND_ROOT / "api" / "intelligence_event_api.py")

    get_section = source.split('@router.get("/assistant/events"', 1)[1].split('@router.post("/assistant/events/refresh")', 1)[0]
    refresh_section = source.split('@router.post("/assistant/events/refresh")', 1)[1]

    assert "evaluate_and_generate_events" not in get_section
    assert "evaluate_and_generate_events" in refresh_section


def test_market_intelligence_cache_ttl_and_mission_control_ttl_are_hardened():
    intelligence_source = _read(BACKEND_ROOT / "services" / "intelligence_service.py")
    assistant_source = _read(BACKEND_ROOT / "api" / "ai_assistant_api.py")

    assert 'MARKET_INTELLIGENCE_CACHE_TTL_SECONDS' in intelligence_source
    assert 'MISSION_CONTROL_CACHE_TTL_SECONDS = int(os.getenv("MISSION_CONTROL_CACHE_TTL_SECONDS", "90"))' in assistant_source
