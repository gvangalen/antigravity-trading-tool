from pathlib import Path


def test_indicator_reconciliation_migration_preserves_unknown_asset_scope_for_user_choice():
    migration = (
        Path(__file__).resolve().parents[1]
        / "scripts/migrations/2026_08_25_finn_v2_indicator_config_reconciliation.py"
    )
    source = migration.read_text()

    assert "finn_v2_indicator_config_reconciliations" in source
    assert "asset_scope_required" in source
    assert "legacy_payload_migrated" in source
    assert "ON CONFLICT (source_key)" in source
    assert "COALESCE(LOWER(BTRIM(score_mode)), 'standard')" in source
    assert "ON CONFLICT (user_id, symbol, category, indicator)" in source
    assert "technical_indicator_rules" in source
    assert "market_indicator_rules" in source
    assert "macro_indicator_rules" in source
    assert "DROP TABLE IF EXISTS finn_v2_indicator_config_reconciliations" in source


def test_indicator_cutover_health_gate_requires_every_legacy_user_row_to_be_tracked():
    health_gate = (
        Path(__file__).resolve().parents[1]
        / "scripts/check_finn_v2_schema.py"
    ).read_text()

    assert "finn_v2_indicator_cutover_unreconciled_legacy_rows" in health_gate
    assert "source_record_ids @> jsonb_build_array(legacy.id)" in health_gate
