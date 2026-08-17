from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_tool_shadow_execution_is_gated_and_read_only():
    source = (ROOT / "services" / "finn_v2_tool_execution_service.py").read_text(encoding="utf-8")

    assert "FINN_V2_TOOL_SHADOW_EXECUTION_ENABLED" in (ROOT / "services" / "finn_v2_flag_service.py").read_text(encoding="utf-8")
    assert "execute_shadow_tool_chain" in source
    assert "timeout_seconds=2.0" in source
    assert "tool_readonly_violation" in source
    assert ".delay(" not in source

