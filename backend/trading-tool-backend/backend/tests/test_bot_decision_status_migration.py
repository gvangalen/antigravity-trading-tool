from pathlib import Path
import runpy


def test_decision_status_migration_preserves_existing_states_and_allows_execution_states():
    root = Path(__file__).resolve().parents[1]
    migration = root / "scripts/migrations/2026_10_12_bot_decision_execution_statuses.py"
    sql = runpy.run_path(str(migration))["SQL"]
    bootstrap = (root / "scripts/bootstrap_local_finn_schema.py").read_text()
    deploy = (root.parents[2] / "ops/deploy/deploy_env.sh").read_text()

    for status in (
        "planned", "ready", "approved", "executing", "executed",
        "failed_execution", "skipped", "failed",
    ):
        assert f"'{status}'" in sql
        assert f"'{status}'" in bootstrap
    assert "VALIDATE CONSTRAINT bot_decisions_status_check" in sql
    assert "run_migration backend/scripts/migrations/2026_10_12_bot_decision_execution_statuses.py" in deploy
