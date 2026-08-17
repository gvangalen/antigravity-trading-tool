from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_orchestrator_repository_reads_are_owner_scoped():
    source = (ROOT / "infrastructure" / "repositories" / "finn_v2_orchestrator_repository.py").read_text(encoding="utf-8")

    assert "FinnV2OrchestratorResult.run_id == run_id" in source
    assert "FinnV2OrchestratorResult.user_id == user_id" in source
