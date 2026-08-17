from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_policy_block_has_no_public_endpoints_or_execution_dispatch():
    orchestrator_source = (ROOT / "services" / "finn_v2_orchestrator_service.py").read_text(encoding="utf-8")
    policy_source = (ROOT / "services" / "finn_v2_policy_engine_service.py").read_text(encoding="utf-8")
    proposal_source = (ROOT / "services" / "finn_v2_proposal_service.py").read_text(encoding="utf-8")

    assert "policy_evaluation_started" in orchestrator_source
    assert "/confirm" not in orchestrator_source
    assert ".delay(" not in policy_source
    assert ".delay(" not in proposal_source
    assert "openai" not in policy_source.lower()
