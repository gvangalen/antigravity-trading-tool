from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_verifier_persistence_is_append_only_and_versioned():
    verifier_repo = (ROOT / "infrastructure" / "repositories" / "finn_v2_verifier_repository.py").read_text(encoding="utf-8")
    verified_repo = (ROOT / "infrastructure" / "repositories" / "finn_v2_verified_response_repository.py").read_text(encoding="utf-8")
    migration_source = (ROOT / "scripts" / "migrations" / "2026_08_17_finn_v2_verified_delivery.py").read_text(encoding="utf-8")

    assert "async def create" in verifier_repo
    assert ".update(" not in verifier_repo
    assert "UNIQUE (run_id, response_version)" in migration_source
    assert "async def create" in verified_repo
