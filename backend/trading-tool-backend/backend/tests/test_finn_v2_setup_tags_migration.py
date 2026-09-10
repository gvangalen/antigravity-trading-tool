from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "scripts/migrations/2026_09_10_finn_v2_setup_tags_text_array.py"
)


def test_setup_tags_migration_converts_legacy_jsonb_to_the_adapter_text_array_contract():
    source = MIGRATION.read_text(encoding="utf-8")

    assert "finn_v2_jsonb_to_text_array" in source
    assert "ALTER COLUMN tags TYPE TEXT[]" in source
    assert "ALTER COLUMN tags SET DEFAULT ARRAY[]::TEXT[]" in source
