from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
STATUS_WRITER = REPO_ROOT / "ops" / "deploy" / "write_deploy_status.py"
DEPLOY_SCRIPT = REPO_ROOT / "ops" / "deploy" / "deploy_env.sh"
SHA = "a" * 40


def _write_status(status_file: Path, *, step: str, outcome: str, exit_code: int) -> None:
    subprocess.run(
        [
            sys.executable,
            str(STATUS_WRITER),
            "--status-file",
            str(status_file),
            "--release-sha",
            SHA,
            "--step-id",
            step,
            "--outcome",
            outcome,
            "--exit-code",
            str(exit_code),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def test_deploy_status_writer_persists_a_sanitized_failure_atomically(tmp_path: Path) -> None:
    status_file = tmp_path / "production_last_deploy_status.json"

    _write_status(status_file, step="schema_health", outcome="failure", exit_code=17)

    payload = json.loads(status_file.read_text(encoding="utf-8"))
    assert payload["format_version"] == 1
    assert payload["current"] == payload["last_failure"]
    assert payload["current"] == {
        "release_sha": SHA,
        "step_id": "schema_health",
        "outcome": "failure",
        "exit_code": 17,
        "timestamp_utc": payload["current"]["timestamp_utc"],
    }
    assert oct(status_file.stat().st_mode & 0o777) == "0o640"
    assert "DATABASE_URL" not in status_file.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY" not in status_file.read_text(encoding="utf-8")


def test_success_status_preserves_the_previous_failure_for_diagnostics(tmp_path: Path) -> None:
    status_file = tmp_path / "production_last_deploy_status.json"
    _write_status(status_file, step="deep_health", outcome="failure", exit_code=1)

    _write_status(status_file, step="release_complete", outcome="success", exit_code=0)

    payload = json.loads(status_file.read_text(encoding="utf-8"))
    assert payload["current"]["outcome"] == "success"
    assert payload["current"]["step_id"] == "release_complete"
    assert payload["last_failure"]["outcome"] == "failure"
    assert payload["last_failure"]["step_id"] == "deep_health"


def test_deploy_script_uses_fixed_step_ids_and_preserves_rollback() -> None:
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "write_deploy_status.py" in source
    assert "DEPLOY_STATUS_WRITER_B64" in source
    assert "base64 -d | sudo python3 -" in source
    assert "DEPLOY_STEP_ID" in source
    assert "trap record_deploy_exit EXIT" in source
    assert 'if [ \\"\\$exit_code\\" -ne 0 ]; then' in source
    assert "cleanup_previous_frontend_static || true" in source
    assert "trap cleanup_previous_frontend_static EXIT" not in source
    assert "./ops/deploy/rollback_env.sh $ENVIRONMENT $ROLLBACK_COMMIT" in source
    for step in (
        "remote_preflight",
        "migration_plan",
        "schema_health",
        "pm2_core",
        "deep_health",
        "release_marker",
        "release_complete",
    ):
        assert step in source
