"""The retired market-intelligence overlay cannot re-enter active routes."""

from backend.api.market_intelligence_api import router
from backend.celery_task.celery_app import celery_app
from backend.engine import bot_brain


def test_old_market_intelligence_read_route_is_gone():
    paths = {(route.path, tuple(sorted(route.methods or ()))) for route in router.routes}
    assert not any(path == "/market/intelligence" for path, _ in paths)
    assert any(path == "/market/asset/initialize" and "POST" in methods
               for path, methods in paths)


def test_user_wide_regime_refresh_is_not_scheduled():
    assert "dispatch_regime_memory" not in celery_app.conf.beat_schedule


def test_bot_brain_exposes_only_score_2_0_context():
    assert not hasattr(bot_brain, "get_regime_memory")
    assert not hasattr(bot_brain, "get_market_intelligence")
