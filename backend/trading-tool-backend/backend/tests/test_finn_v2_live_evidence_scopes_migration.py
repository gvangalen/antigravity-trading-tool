from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_live_evidence_scope_migration_extends_the_canonical_constraint():
    source = (
        ROOT / "scripts" / "migrations" / "2026_09_21_finn_v2_live_evidence_scopes.py"
    ).read_text(encoding="utf-8")

    assert "DROP CONSTRAINT IF EXISTS ck_finn_v2_evidence_information_scope" in source
    assert "ADD CONSTRAINT ck_finn_v2_evidence_information_scope" in source
    assert "'macro_snapshot'" in source
    assert "'technical_snapshot'" in source


def test_live_evidence_scope_migration_runs_before_schema_health():
    deploy_source = (ROOT.parents[2] / "ops" / "deploy" / "deploy_env.sh").read_text(encoding="utf-8")
    migration = "2026_09_21_finn_v2_live_evidence_scopes.py"

    assert f"run_migration backend/scripts/migrations/{migration}" in deploy_source
    assert deploy_source.index(migration) < deploy_source.index("advance_deploy_step 'schema_health'")


def test_replayed_historical_scope_constraints_accept_live_evidence():
    for name in (
        "2026_08_23_finn_v2_evidence_information_scope.py",
        "2026_09_07_finn_v2_action_contract_completion.py",
    ):
        source = (ROOT / "scripts" / "migrations" / name).read_text(encoding="utf-8")
        assert "'macro_snapshot'" in source
        assert "'technical_snapshot'" in source
