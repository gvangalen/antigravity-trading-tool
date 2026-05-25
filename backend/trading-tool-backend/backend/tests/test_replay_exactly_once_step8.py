from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend" / "trading-tool-backend" / "backend"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_assistant_pending_action_execute_uses_atomic_claim_and_stored_replay_result():
    source = _read(BACKEND_ROOT / "services" / "ai_action_engine.py")

    assert "UPDATE ai_pending_actions" in source
    assert "SET status = 'executing'" in source
    assert "AND status = 'pending'" in source
    assert "RETURNING id" in source
    assert '"replayed": True' in source
    assert '"_execution_result": result_data' in source
    assert "Deze actie wordt al verwerkt of is net verwerkt" in source


def test_assistant_pending_action_failures_leave_clean_failed_state():
    source = _read(BACKEND_ROOT / "services" / "ai_action_engine.py")

    assert "SET status = 'failed'" in source
    assert '"_execution_error"' in source
    assert '"_failed_at"' in source


def test_finn_maintenance_actions_keep_deterministic_idempotency_boundary():
    source = _read(BACKEND_ROOT / "services" / "finn_plan_service.py")

    for action_type in (
        "skip_bot_decision",
        "resolve_mission_item",
        "agent_controller_handoff",
    ):
        assert action_type in source

    assert "ON CONFLICT (id) DO NOTHING" in source
    assert "_try_create_pending_action" in source
    assert "_wait_for_action_result" in source


def test_execution_replay_inventory_documents_current_guards():
    source = _read(REPO_ROOT / "docs" / "operations" / "replay-exactly-once-inventory.md")

    assert "Assistant pending action execute" in source
    assert "Manual orders" in source
    assert "Live preflight token usage" in source
    assert "Bot decision generation" in source
    assert "pending -> executing" in source
