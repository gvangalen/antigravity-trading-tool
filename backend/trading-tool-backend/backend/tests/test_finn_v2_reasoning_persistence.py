from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_reasoning_persistence_is_append_only_and_deduped():
    repo_source = (ROOT / "infrastructure" / "repositories" / "finn_v2_reasoning_repository.py").read_text(encoding="utf-8")
    migration_source = (ROOT / "scripts" / "migrations" / "2026_08_17_finn_v2_reasoning.py").read_text(encoding="utf-8")

    assert "async def create" in repo_source
    assert ".update(" not in repo_source
    assert "ux_finn_v2_reasoning_dedupe" in migration_source
