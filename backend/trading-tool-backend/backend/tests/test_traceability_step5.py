from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_assistant_execution_uses_owner_bound_v2_contract():
    api_source = _read(BACKEND_ROOT / "api" / "ai_assistant_api.py")

    assert '"/assistant/actions/execute"' not in api_source
    assert "idempotency_key=request.idempotency_key" in api_source
    assert 'user_id=current_user["id"]' in api_source
    assert "expected_payload_hash=request.expected_payload_hash" in api_source


def test_manual_order_and_preflight_propagate_trace_to_results_and_audit():
    api_source = _read(BACKEND_ROOT / "api" / "bot_api.py")
    service_source = _read(BACKEND_ROOT / "services" / "bot_service.py")

    assert "create_manual_order(payload, current_user[\"id\"], trace_id=trace_id)" in api_source
    assert "preflight_manual_order(payload, current_user[\"id\"], trace_id=trace_id)" in api_source
    assert "record_live_order_block_from_exception(" in api_source
    assert "trace_id=trace_id" in api_source

    assert "async def create_manual_order(self, payload: BotManualOrderSchema, user_id: int, trace_id: Optional[str] = None)" in service_source
    assert "async def preflight_manual_order(self, payload: BotManualOrderSchema, user_id: int, trace_id: Optional[str] = None)" in service_source
    assert '"trace_id": trace_id' in service_source
    assert "INSERT INTO ai_pending_actions (id, user_id, type, payload, status, expires_at, trace_id)" in service_source


def test_bot_decision_execution_endpoints_include_trace_id_in_response_shape():
    api_source = _read(BACKEND_ROOT / "api" / "bot_api.py")
    service_source = _read(BACKEND_ROOT / "services" / "bot_service.py")

    assert "run_bot_agent_generate(" in api_source
    assert "trace_id=getattr(request.state, \"trace_id\", None)" in api_source
    assert 'result["trace_id"] = getattr(request.state, "trace_id", None)' in api_source
    assert "trace_id: Optional[str] = None" in service_source
    assert '"trace_id": trace_id' in service_source
