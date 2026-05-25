from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parents[2]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_api_modules_do_not_use_sync_session_query_patterns():
    for path in sorted((BACKEND_ROOT / "api").glob("*.py")):
        source = _read(path)

        assert "sqlalchemy.orm import Session" not in source, path
        assert ".query(" not in source, path


def test_process_local_caches_are_disabled_or_removed_for_phase6():
    dashboard_source = _read(BACKEND_ROOT / "services" / "dashboard_service.py")
    intelligence_source = _read(BACKEND_ROOT / "services" / "intelligence_service.py")
    macro_source = _read(BACKEND_ROOT / "services" / "macro_data_service.py")
    technical_source = _read(BACKEND_ROOT / "services" / "technical_data_service.py")

    assert "DASHBOARD_OVERVIEW_CACHE_ENABLED" in dashboard_source
    assert "INTELLIGENCE_SERVICE_CACHE_ENABLED" in intelligence_source
    assert "_cache = {}" not in macro_source
    assert "_cache = {}" not in technical_source


def test_psycopg2_usage_is_limited_to_explicit_legacy_boundaries():
    allowed = {
        BACKEND_ROOT / "ai_core" / "regime_memory.py",
        BACKEND_ROOT / "celery_task" / "daily_report_task.py",
        BACKEND_ROOT / "scripts" / "database.py",
        BACKEND_ROOT / "utils" / "db.py",
    }
    matches = {
        path
        for path in BACKEND_ROOT.rglob("*.py")
        if "psycopg2" in _read(path)
        and "tests" not in path.parts
    }

    assert matches == allowed


def test_root_pytest_collects_maintained_backend_suite_only():
    pytest_ini = _read(REPO_ROOT / "pytest.ini")

    assert "testpaths =" in pytest_ini
    assert "backend/trading-tool-backend/backend/tests" in pytest_ini
    assert "pythonpath =" in pytest_ini
    assert "backend/trading-tool-backend" in pytest_ini
    assert "frontend" in pytest_ini
    assert "mobile" in pytest_ini
    assert "scratch" in pytest_ini
