import importlib
import inspect


def test_dashboard_service_avoids_the_retired_blocking_score_read():
    module = importlib.import_module("backend.services.dashboard_service")
    source = inspect.getsource(module)

    assert "sync_get_scores_for_symbol" not in source
    assert "asyncio.to_thread" not in source
    assert "reported_scores" in source
