from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend" / "trading-tool-backend" / "backend"
FRONTEND_ROOT = REPO_ROOT / "frontend" / "trading-tool-frontend"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_system_health_is_operator_only():
    source = _read(BACKEND_ROOT / "api" / "system_api.py")

    assert "async def require_operator" in source
    assert 'from backend.utils.rate_limit import client_ip' in source
    assert "forwarded_client_ip = client_ip(request)" in source
    assert 'client_host in {"127.0.0.1", "::1", "localhost"}' in source
    assert 'forwarded_client_ip in {"127.0.0.1", "::1", "localhost"}' in source
    assert 'current_user.get("role") != "admin"' in source
    assert 'detail="Admin access required."' in source
    assert 'async def system_health(current_user: dict = Depends(require_operator))' in source


def test_market_latest_and_7d_get_routes_are_read_only():
    source = _read(BACKEND_ROOT / "api" / "market_data_api.py")

    latest_section = source.split('@router.get("/market_data/{symbol}/latest"', 1)[1].split('@router.get("/market_data/interpreted")', 1)[0]
    seven_day_section = source.split('@router.get("/market_data/7d"', 1)[1].split("# =========================================================\n# FORWARD RETURNS", 1)[0]

    assert "sync_live_price" not in latest_section
    assert "sync_symbol_7day_data" not in seven_day_section


def test_market_fill_route_requires_authenticated_user():
    source = _read(BACKEND_ROOT / "api" / "market_data_api.py")

    fill_section = source.split('@router.post("/market_data/7d/fill")', 1)[1].split('@router.get("/market_data/7d"', 1)[0]

    assert "current_user: dict = Depends(get_current_user)" in fill_section
    assert "sync_symbol_7day_data" in fill_section


def test_api_responses_are_marked_no_store():
    source = _read(BACKEND_ROOT / "main.py")

    assert "async def api_no_store_middleware" in source
    assert 'if request.url.path.startswith("/api/")' in source
    assert 'response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"' in source
    assert 'response.headers["Pragma"] = "no-cache"' in source
    assert 'response.headers["Expires"] = "0"' in source


def test_service_worker_no_longer_caches_authenticated_api_responses():
    source = _read(FRONTEND_ROOT / "public" / "sw.js")

    assert "self.registration.unregister" in source
    assert "caches.keys()" in source
    assert "TRADAMIND_SW_DISABLED" in source
    assert "NetworkFirst" not in source
    assert 'cacheName:"apis"' not in source
    assert "/api/" not in source
