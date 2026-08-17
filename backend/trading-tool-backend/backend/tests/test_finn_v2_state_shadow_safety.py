from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_state_shadow_requires_flags_and_has_no_public_endpoint():
    flags = (ROOT / "services" / "finn_v2_flag_service.py").read_text(encoding="utf-8")
    execution = (ROOT / "services" / "finn_v2_tool_execution_service.py").read_text(encoding="utf-8")
    api = (ROOT / "api" / "finn_v2_api.py").read_text(encoding="utf-8")

    assert "FINN_V2_STATE_ASSEMBLY_ENABLED" in flags
    assert "FINN_V2_STATE_SHADOW_ENABLED" in flags
    assert "_run_state_pipeline" in execution
    assert ".delay(" not in execution
    assert "assemble-state" not in api
    assert "validate" not in api

