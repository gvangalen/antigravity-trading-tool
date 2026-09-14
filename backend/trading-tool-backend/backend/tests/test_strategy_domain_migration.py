from pathlib import Path


def test_strategy_domain_migration_preserves_legacy_rows_and_allows_multiple_names():
    migration = Path(__file__).parents[1] / "scripts" / "migrations" / "2026_09_14_strategy_domain_multiple_strategies.py"
    source = migration.read_text()

    assert "ADD COLUMN IF NOT EXISTS canonical_name" in source
    assert "ADD COLUMN IF NOT EXISTS symbol" in source
    assert "ADD COLUMN IF NOT EXISTS timeframe" in source
    assert "strategies_owner_setup_canonical_name_uq" in source
    assert "(user_id, setup_id, canonical_name)" in source
