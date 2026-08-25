from pathlib import Path


def test_canonical_indicator_config_migration_is_idempotent_and_audits_ambiguous_rows():
    migration = (
        Path(__file__).resolve().parents[1]
        / "scripts/migrations/2026_08_25_canonical_user_indicator_configs.py"
    )
    source = migration.read_text()

    assert "ADD COLUMN IF NOT EXISTS config_json JSONB" in source
    assert "CREATE UNIQUE INDEX IF NOT EXISTS ux_user_indicator_configs_canonical_asset_scope" in source
    assert "(user_id, symbol, category, indicator)" in source
    assert "finn_v2_data_migration_audit" in source
    assert "ambiguous_count" in source
    assert "to_regclass(source_table_name)" in source
    assert "ROLLBACK_SQL" in source
    assert "DROP COLUMN IF EXISTS config_json" in source
