from pathlib import Path


def test_active_finn_reader_sources_have_an_additive_schema_migration():
    migration = Path(__file__).parents[1] / "scripts/migrations/2026_09_12_finn_v2_certification_source_schema.py"
    sql = migration.read_text(encoding="utf-8")

    for identifier in (
        "macro_interpretation",
        "technical_interpretation",
        "market_interpretation",
        "cash_eur",
        "CREATE TABLE IF NOT EXISTS ai_reflections",
        "ix_ai_reflections_user_category_date",
        "CREATE TABLE IF NOT EXISTS daily_reports",
        "ix_daily_reports_user_date",
    ):
        assert identifier in sql


def test_certification_fixture_seeds_released_score_evidence():
    source = (Path(__file__).parents[1] / "scripts/run_finn_v2_full_action_matrix.py").read_text(encoding="utf-8")

    assert "INSERT INTO daily_scores" in source
    assert "macro_interpretation" in source
