from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "scripts" / "migrations" / "2026_08_17_finn_v2_foundation.py"


def test_finn_v2_migration_contains_expected_tables_constraints_and_indexes():
    source = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS finn_v2_conversations" in source
    assert "CREATE TABLE IF NOT EXISTS finn_v2_runs" in source
    assert "CREATE TABLE IF NOT EXISTS finn_v2_run_traces" in source
    assert "TIMESTAMPTZ" in source
    assert "ux_finn_v2_runs_user_idempotency_key" in source
    assert "ux_finn_v2_run_traces_run_order" in source
    assert "idx_finn_v2_runs_trace_id" in source
    assert "idx_finn_v2_run_traces_trace_id" in source
    assert "REFERENCES users(id) ON DELETE CASCADE" in source
    assert "status IN ('created', 'collecting', 'planned', 'blocked', 'completed', 'failed', 'canceled')" in source


def test_finn_v2_migration_exposes_rollback_sql_and_is_idempotent():
    source = MIGRATION.read_text(encoding="utf-8")

    assert "ROLLBACK_SQL" in source
    assert "DROP TABLE IF EXISTS finn_v2_run_traces" in source
    assert "DROP TABLE IF EXISTS finn_v2_runs" in source
    assert "DROP TABLE IF EXISTS finn_v2_conversations" in source
    assert source.count("CREATE TABLE IF NOT EXISTS") == 3
