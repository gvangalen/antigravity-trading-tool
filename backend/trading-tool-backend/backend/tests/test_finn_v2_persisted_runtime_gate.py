from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_persisted_runtime_gate_uses_public_gateway_polling_and_sse_only():
    source = (ROOT / "scripts" / "run_finn_v2_persisted_runtime_gate.py").read_text(encoding="utf-8")

    assert "/api/assistant/v2/runs" in source
    assert "/stream" in source
    assert "FinnV2GatewayService" not in source
    assert "async_session_factory" not in source
    assert "runtime_gate_contract_missing_at_run_creation" in source
    assert "runtime_gate_polling_sse_envelope_mismatch" in source
    assert "runtime_gate_legacy_compact_for_new_run" in source
    assert "status in {502, 503, 504}" in source
    assert "json.JSONDecodeError" in source
    assert "ThreadPoolExecutor" in source
    assert "sse_future = executor.submit" in source
    assert source.index("sse_future = executor.submit") < source.index("while time.monotonic() - started_at")
