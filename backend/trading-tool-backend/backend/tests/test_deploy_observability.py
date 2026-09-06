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


def test_running_status_identifies_the_last_safe_deploy_checkpoint(tmp_path: Path) -> None:
    status_file = tmp_path / "production_last_deploy_status.json"

    _write_status(status_file, step="runtime_dependencies", outcome="running", exit_code=0)

    payload = json.loads(status_file.read_text(encoding="utf-8"))
    assert payload["current"]["outcome"] == "running"
    assert payload["current"]["step_id"] == "runtime_dependencies"


def test_deploy_script_uses_fixed_step_ids_and_preserves_rollback() -> None:
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "write_deploy_status.py" in source
    assert "DEPLOY_STATUS_WRITER_B64" in source
    assert "base64 -d | sudo python3 -" in source
    assert "DEPLOY_STEP_ID" in source
    assert "trap record_deploy_exit EXIT" in source
    assert "advance_deploy_step()" in source
    assert r'record_deploy_status \"\$DEPLOY_STEP_ID\" running 0' in source
    assert "Diagnostics must never block a release." in source
    assert "Unable to persist deploy checkpoint" in source
    assert 'if [ \\"\\$exit_code\\" -ne 0 ]; then' in source
    assert "cleanup_previous_frontend_static || true" in source
    assert "trap cleanup_previous_frontend_static EXIT" not in source
    assert "./ops/deploy/rollback_env.sh $ENVIRONMENT $ROLLBACK_COMMIT" in source
    for step in (
        "remote_preflight",
        "migration_plan",
        "schema_health",
        "memory_headroom",
        "pm2_core",
        "deep_health",
        "release_marker",
        "release_complete",
    ):
        assert step in source


def test_release_identity_is_written_before_pm2_and_loaded_by_every_process() -> None:
    deploy_source = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    rollback_source = (REPO_ROOT / "ops" / "deploy" / "rollback_env.sh").read_text(encoding="utf-8")
    ecosystem_source = (REPO_ROOT / "ops" / "deploy" / "ecosystem.shared.js").read_text(encoding="utf-8")

    assert 'metadata_path="ops/deploy/.release_metadata.env"' in deploy_source
    assert deploy_source.index("write_release_metadata") < deploy_source.index("pm2_start_app()")
    assert 'metadata_path="ops/deploy/.release_metadata.env"' in rollback_source
    assert "function loadReleaseMetadata()" in ecosystem_source
    assert "const RELEASE_METADATA_ENV = loadReleaseMetadata();" in ecosystem_source
    assert ecosystem_source.count("...RELEASE_METADATA_ENV,") == 8


def test_release_marker_remote_steps_are_independently_guarded() -> None:
    source = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    marker_start = source.index('DEPLOY_STEP_ID="release_marker"')
    marker_end = source.index('record_remote_deploy_status "release_complete"', marker_start)
    marker_block = source[marker_start:marker_end]

    # Each SSH boundary must have its own if-body; otherwise Bash treats the
    # second SSH invocation as part of the first conditional command list.
    assert marker_block.count('if ! ssh "${SSH_ARGS[@]}" "ubuntu@$SERVER_IP"') == 2
    assert marker_block.count('record_remote_deploy_status "$DEPLOY_STEP_ID" failure 1 || true') == 2
