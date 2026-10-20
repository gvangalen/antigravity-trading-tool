from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend" / "trading-tool-backend" / "backend"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_retired_assistant_action_route_is_not_exposed():
    source = _read(BACKEND_ROOT / "api" / "ai_assistant_api.py")

    assert '"/assistant/actions/execute"' not in source
    assert '"/assistant/v2/proposals/{proposal_id}/execute"' in source


def test_execution_replay_inventory_documents_current_guards():
    source = _read(REPO_ROOT / "docs" / "operations" / "replay-exactly-once-inventory.md")

    assert "Assistant pending action execute" in source
    assert "Manual orders" in source
    assert "Live preflight token usage" in source
    assert "Bot decision generation" in source
    assert "Bot-generated execution" in source
    assert "pending -> executing" in source
    assert "planned -> executing -> executed/failed_execution" in source
