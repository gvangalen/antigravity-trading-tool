from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_assistant_action_execution_propagates_request_trace_id():
    api_source = _read(BACKEND_ROOT / "api" / "ai_assistant_api.py")
    action_engine_source = _read(BACKEND_ROOT / "services" / "ai_action_engine.py")
    finn_source = _read(BACKEND_ROOT / "services" / "finn_plan_service.py")

    assert 'trace_id = getattr(request.state, "trace_id", None)' in api_source
    assert "FinnPlanService(db, trace_id=trace_id)" in api_source
    assert "execute_pending_action(action_id, user_id, trace_id=trace_id)" in api_source
    assert "execution_trace_id = trace_id or action_record.trace_id" in action_engine_source
    assert '"trace_id": execution_trace_id' in action_engine_source
    assert "trace_id = COALESCE(EXCLUDED.trace_id, ai_pending_actions.trace_id)" in finn_source
    assert "SELECT id, status, payload, trace_id, created_at" in finn_source


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
