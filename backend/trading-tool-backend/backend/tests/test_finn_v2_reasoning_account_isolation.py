from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_reasoning_repository_is_owner_scoped():
    source = (ROOT / "infrastructure" / "repositories" / "finn_v2_reasoning_repository.py").read_text(encoding="utf-8")

    assert "FinnV2ReasoningResult.user_id == user_id" in source
