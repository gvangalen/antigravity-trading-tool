from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
TOKEN_SCRIPT = REPO_ROOT / "backend" / "trading-tool-backend" / "backend" / "scripts" / "qa_issue_finn_token.py"
PLAYBOOK = REPO_ROOT / "docs" / "operations" / "finn-qa-rerun-playbook.md"


def test_qa_token_script_exists_and_mentions_authorization_header():
    source = TOKEN_SCRIPT.read_text(encoding="utf-8")
    assert "authorization_header" in source
    assert "create_access_token" in source
    assert "--email" in source


def test_qa_rerun_playbook_mentions_token_and_replay_flow():
    source = PLAYBOOK.read_text(encoding="utf-8")
    assert "qa_issue_finn_token.py" in source
    assert "run_finn_qa_replay.py" in source
    assert "delay-seconds 2.6" in source
    assert "previous valid full FINN report remains the best reference baseline" in source
