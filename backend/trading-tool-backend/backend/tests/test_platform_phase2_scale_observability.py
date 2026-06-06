from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend" / "trading-tool-backend" / "backend"
FRONTEND_ROOT = REPO_ROOT / "frontend" / "trading-tool-frontend"
TEST_ROOT = BACKEND_ROOT / "tests"
STATUS_DOC = REPO_ROOT / "docs" / "operations" / "platform-hardening-status.md"


REQUEST_PATH_MODULES = [
    BACKEND_ROOT / "services" / "dashboard_service.py",
    BACKEND_ROOT / "services" / "ai_assistant_service.py",
    BACKEND_ROOT / "services" / "system_health_service.py",
    BACKEND_ROOT / "services" / "push_service.py",
]

ALLOWED_LEGACY_SYNC_BOUNDARIES = {
    "backend/trading-tool-backend/backend/ai_agents/macro_ai_agent.py",
    "backend/trading-tool-backend/backend/ai_agents/market_ai_agent.py",
    "backend/trading-tool-backend/backend/ai_agents/monthly_report_agent.py",
    "backend/trading-tool-backend/backend/ai_agents/quarterly_report_agent.py",
    "backend/trading-tool-backend/backend/ai_agents/report_ai_agent.py",
    "backend/trading-tool-backend/backend/ai_agents/score_ai_agent.py",
    "backend/trading-tool-backend/backend/ai_agents/setup_ai_agent.py",
    "backend/trading-tool-backend/backend/ai_agents/strategy_ai_agent.py",
    "backend/trading-tool-backend/backend/ai_agents/technical_ai_agent.py",
    "backend/trading-tool-backend/backend/ai_agents/trading_bot_agent.py",
    "backend/trading-tool-backend/backend/ai_agents/weekly_report_agent.py",
    "backend/trading-tool-backend/backend/celery_task/btc_price_history_task.py",
    "backend/trading-tool-backend/backend/celery_task/celery_task_generate_pdf.py",
    "backend/trading-tool-backend/backend/celery_task/daily_usage_reset.py",
    "backend/trading-tool-backend/backend/celery_task/dispatcher.py",
    "backend/trading-tool-backend/backend/celery_task/global_ingestion_task.py",
    "backend/trading-tool-backend/backend/celery_task/macro_task.py",
    "backend/trading-tool-backend/backend/celery_task/market_task.py",
    "backend/trading-tool-backend/backend/celery_task/monthly_report_task.py",
    "backend/trading-tool-backend/backend/celery_task/onboarding_task.py",
    "backend/trading-tool-backend/backend/celery_task/quarterly_report_task.py",
    "backend/trading-tool-backend/backend/celery_task/setup_task.py",
    "backend/trading-tool-backend/backend/celery_task/store_daily_scores_task.py",
    "backend/trading-tool-backend/backend/celery_task/strategy_task.py",
    "backend/trading-tool-backend/backend/celery_task/technical_task.py",
    "backend/trading-tool-backend/backend/celery_task/user_scoring_sync_task.py",
    "backend/trading-tool-backend/backend/celery_task/weekly_report_task.py",
    "backend/trading-tool-backend/backend/engine/backtest_engine.py",
    "backend/trading-tool-backend/backend/engine/market_intelligence_engine.py",
    "backend/trading-tool-backend/backend/engine/state_builder.py",
    "backend/trading-tool-backend/backend/engine/transition_detector.py",
    "backend/trading-tool-backend/backend/services/bot_service.py",
    "backend/trading-tool-backend/backend/services/macro_data_service.py",
    "backend/trading-tool-backend/backend/services/market_data_service.py",
    "backend/trading-tool-backend/backend/services/portfolio_snapshot_service.py",
    "backend/trading-tool-backend/backend/services/report_snapshot_service.py",
    "backend/trading-tool-backend/backend/services/technical_data_service.py",
}


def test_security_source_of_truth_stays_in_frontend_source_not_generated_out():
    security_tests = [
        TEST_ROOT / "test_security_phase1.py",
        TEST_ROOT / "test_security_phase3.py",
        TEST_ROOT / "test_security_phase7.py",
    ]

    for path in security_tests:
        source = path.read_text(encoding="utf-8")
        assert "frontend/trading-tool-frontend/out/" not in source
        assert "FRONTEND_ROOT" in source or "frontend" in source


def test_platform_status_documents_repo_and_runtime_commit_separately():
    source = STATUS_DOC.read_text(encoding="utf-8")

    assert "repo_head" in source
    assert "production_head" in source
    assert "LAST_GOOD_COMMIT" in source
    assert "Generated frontend `out/` artifacts are not a source of truth" in source


def test_request_path_services_do_not_import_legacy_sync_db_helper():
    for path in REQUEST_PATH_MODULES:
        source = path.read_text(encoding="utf-8")
        assert "from backend.utils.db import get_db_connection" not in source


def test_legacy_sync_db_usage_is_explicitly_allowlisted():
    roots = [
        BACKEND_ROOT / "services",
        BACKEND_ROOT / "ai_agents",
        BACKEND_ROOT / "celery_task",
        BACKEND_ROOT / "engine",
    ]
    direct_imports = set()
    for root in roots:
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            if "from backend.utils.db import get_db_connection" in source:
                direct_imports.add(path.relative_to(REPO_ROOT).as_posix())

    assert direct_imports == ALLOWED_LEGACY_SYNC_BOUNDARIES


def test_frontend_generated_output_is_not_treated_as_contract_authority():
    source = (FRONTEND_ROOT / "lib" / "api" / "ai.js").read_text(encoding="utf-8")
    generated_candidates = list((FRONTEND_ROOT / "out").glob("**/*"))

    assert "body: JSON.stringify({ action_id: actionId })" in source
    assert "localStorage.getItem('token')" not in source
    assert "buildAuthHeaders" in source
    assert generated_candidates, "Expected generated frontend artifacts to exist for drift protection."
