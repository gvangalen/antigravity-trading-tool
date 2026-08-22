from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "scripts" / "migrations" / "2026_08_22_finn_v2_run_lifecycle_statuses.py"


def test_run_status_migration_expands_lifecycle_status_constraint():
    source = MIGRATION.read_text(encoding="utf-8")

    assert "DROP CONSTRAINT IF EXISTS ck_finn_v2_runs_status" in source
    assert "'queued'" in source
    assert "'reasoning'" in source
    assert "'verifying'" in source
    assert "'clarification_required'" in source
    assert "'unavailable'" in source
    assert "'downgraded'" in source
    assert "'rejected'" in source


def test_run_status_migration_keeps_rollback_to_foundation_statuses():
    source = MIGRATION.read_text(encoding="utf-8")

    assert "ROLLBACK_SQL" in source
    assert "status IN ('created', 'collecting', 'planned', 'blocked', 'completed', 'failed', 'canceled')" in source
