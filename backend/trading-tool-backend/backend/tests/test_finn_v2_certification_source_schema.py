from pathlib import Path


def test_active_finn_reader_sources_have_an_additive_schema_migration():
    migration = Path(__file__).parents[1] / "scripts/migrations/2026_09_12_finn_v2_certification_source_schema.py"
    sql = migration.read_text(encoding="utf-8")

    for identifier in (
        "macro_interpretation",
        "technical_interpretation",
        "market_interpretation",
        "cash_eur",
        "CREATE TABLE IF NOT EXISTS daily_reports",
        "ix_daily_reports_user_date",
    ):
        assert identifier in sql


def test_retired_reflection_table_is_not_recreated_and_is_removed_on_deploy():
    backend = Path(__file__).parents[1]
    old_migration = (backend / "scripts/migrations/2026_09_12_finn_v2_certification_source_schema.py").read_text(encoding="utf-8")
    retirement = (backend / "scripts/migrations/2026_10_09_retire_ai_reflections.py").read_text(encoding="utf-8")
    deploy = (backend.parents[2] / "ops/deploy/deploy_env.sh").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS ai_reflections" not in old_migration
    assert "DROP TABLE IF EXISTS ai_reflections" in retirement
    assert "run_migration backend/scripts/migrations/2026_10_09_retire_ai_reflections.py" in deploy


def test_certification_fixture_seeds_released_score_evidence():
    source = (Path(__file__).parents[1] / "scripts/run_finn_v2_full_action_matrix.py").read_text(encoding="utf-8")

    assert "INSERT INTO daily_scores" in source
    assert "macro_interpretation" in source
