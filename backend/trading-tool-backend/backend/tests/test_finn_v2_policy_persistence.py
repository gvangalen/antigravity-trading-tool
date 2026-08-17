from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_policy_persistence_is_append_only():
    repo_source = (ROOT / "infrastructure" / "repositories" / "finn_v2_policy_repository.py").read_text(encoding="utf-8")
    migration_source = (ROOT / "scripts" / "migrations" / "2026_08_17_finn_v2_policy_confirmation.py").read_text(encoding="utf-8")

    assert "async def create" in repo_source
    assert ".update(" not in repo_source
    assert "UNIQUE (run_id, policy_version)".replace(" ", "") in migration_source.replace(" ", "")
