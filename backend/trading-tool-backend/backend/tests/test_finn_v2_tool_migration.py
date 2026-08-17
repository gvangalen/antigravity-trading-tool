from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "scripts" / "migrations" / "2026_08_17_finn_v2_tool_registry.py"


def test_tool_migration_contains_expected_table_constraints_and_indexes():
    source = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS finn_v2_tool_calls" in source
    assert "status IN ('requested', 'executing', 'completed', 'failed')" in source
    assert "freshness_status IN ('fresh', 'stale', 'unknown', 'not_applicable')" in source
    assert "idx_finn_v2_tool_calls_run_id" in source
    assert "idx_finn_v2_tool_calls_user_started" in source
    assert "error_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb" in source

