import importlib
import inspect


def test_dashboard_service_imports_asyncio_for_score_thread_offload():
    module = importlib.import_module("backend.services.dashboard_service")
    source = inspect.getsource(module)

    assert "import asyncio" in source
    assert "asyncio.to_thread" in source
