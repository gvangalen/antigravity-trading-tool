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
    macro_source = _read(BACKEND_ROOT / "services" / "macro_data_service.py")
    technical_source = _read(BACKEND_ROOT / "services" / "technical_data_service.py")

    assert "_overview_cache:" not in dashboard_source
    assert "self._overview_cache" not in dashboard_source
    assert "DashboardService._overview_cache" not in dashboard_source
    assert "DASHBOARD_OVERVIEW_CACHE_ENABLED" not in dashboard_source
    assert not (BACKEND_ROOT / "services" / "intelligence_service.py").exists()
    assert "_cache = {}" not in macro_source
    assert "_cache = {}" not in technical_source
    assert not (BACKEND_ROOT / "engine" / "transition_detector.py").exists()


def test_psycopg2_usage_is_limited_to_explicit_legacy_boundaries():
    allowed = {
        BACKEND_ROOT / "utils" / "db.py",
    }
    matches = {
        path
        for path in BACKEND_ROOT.rglob("*.py")
        if "psycopg2" in _read(path)
        and "tests" not in path.parts
    }

    assert matches == allowed


def test_json_adapter_is_hidden_behind_legacy_db_boundary():
    forbidden = "from psycopg2.extras import Json"
    matches = {
        path
        for path in BACKEND_ROOT.rglob("*.py")
        if forbidden in _read(path)
        and "tests" not in path.parts
    }

    assert matches == {BACKEND_ROOT / "utils" / "db.py"}


def test_legacy_script_database_module_is_compatibility_wrapper():
    source = _read(BACKEND_ROOT / "scripts" / "database.py")

    assert "import psycopg2" not in source
    assert "from backend.utils.db import get_db_connection" in source


def test_retired_regime_memory_is_absent_and_daily_report_uses_repository_boundary():
    daily_report_source = _read(BACKEND_ROOT / "celery_task" / "daily_report_task.py")
    daily_report_repo_source = _read(
        BACKEND_ROOT / "infrastructure" / "repositories" / "daily_report_repository.py"
    )

    assert not (BACKEND_ROOT / "ai_core" / "regime_memory.py").exists()
    regime_task = (BACKEND_ROOT / "celery_task" / "regime_memory_task.py").read_text(encoding="utf-8")
    assert "retired_regime_agent" in regime_task
    assert "get_regime_memory" not in regime_task
    assert not (BACKEND_ROOT / "infrastructure" / "repositories" / "regime_memory_repository.py").exists()
    assert "from backend.utils.db import" not in daily_report_source
    assert "get_db_connection" not in daily_report_source
    assert "jsonb_param" not in daily_report_source
    assert "DailyReportWriteRepository" in daily_report_source
    assert "bindparam" in daily_report_repo_source
    assert "type_=JSONB" in daily_report_repo_source


def test_root_pytest_collects_maintained_backend_suite_only():
    pytest_ini = _read(REPO_ROOT / "pytest.ini")

    assert "testpaths =" in pytest_ini
    assert "backend/trading-tool-backend/backend/tests" in pytest_ini
    assert "pythonpath =" in pytest_ini
    assert "backend/trading-tool-backend" in pytest_ini
    assert "frontend" in pytest_ini
    assert "mobile" in pytest_ini
    assert "scratch" in pytest_ini
