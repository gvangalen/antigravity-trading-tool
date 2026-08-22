from pathlib import Path


def test_finn_v2_conversation_context_migration_is_idempotent_and_reversible():
    migration = Path(__file__).resolve().parents[1] / "scripts/migrations/2026_08_23_finn_v2_conversation_context.py"
    source = migration.read_text()

    assert "ADD COLUMN IF NOT EXISTS context_json JSONB" in source
    assert "DROP COLUMN IF EXISTS context_json" in source
    assert "ROLLBACK_SQL" in source
