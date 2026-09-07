from __future__ import annotations

import importlib.util
import json
import socket
import ssl
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO_ROOT / "backend" / "trading-tool-backend" / "backend" / "scripts" / "run_finn_production_qa.py"
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "finn-production-qa.yml"
CRYPTO_SCRIPT_PATH = REPO_ROOT / "ops" / "qa" / "finn_qa_manifest_bundle.py"


def _module():
    spec = importlib.util.spec_from_file_location("finn_production_qa_runner", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_workflow_is_manual_protected_and_serialized():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "environment: production" in workflow
    assert "finn-production-qa-${{ inputs.release_sha }}-${{ inputs.qa_profile }}" in workflow
    assert "persist-credentials: false" in workflow
    assert "actions/upload-artifact@" in workflow
    assert "QA_SSH_KNOWN_HOSTS" in workflow
    assert "StrictHostKeyChecking=yes" in workflow
    assert "manifest_key" in workflow
    assert "manifest_bundle" in workflow
    assert "allow_fixture_actions" in workflow
    assert "allow_safe_fixture_execution" in workflow
    assert "Safe fixture execution requires fixture-action authorization." in workflow


def test_workflow_never_exports_fixture_or_bearer_token():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "FINN_QA_USER_ID" not in workflow
    assert "FINN_QA_BEARER_TOKEN" not in workflow
    assert "authorization_header" not in workflow
    assert "set +x" in workflow


def test_transport_errors_have_typed_599_categories():
    module = _module()
    assert module.classify_transport_error(TimeoutError()) == "clienttimeout"
    assert module.classify_transport_error(socket.gaierror()) == "dns"
    assert module.classify_transport_error(ssl.SSLError()) == "tls"


def test_redaction_removes_credentials_and_fixture_identity():
    module = _module()
    report = module.redact({"access_token": "secret", "user_id": 7, "run_id": "safe", "nested": {"email": "x@example.test"}})
    assert report == {"access_token": "[REDACTED]", "user_id": "[REDACTED]", "run_id": "safe", "nested": {"email": "[REDACTED]"}}
    assert "secret" not in json.dumps(report)


def test_manifest_rejects_unsafe_fixture_actions_and_path_escape(monkeypatch, tmp_path):
    module = _module()
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "unsafe.json").write_text(json.dumps({"cases": [{"case_id": "one", "message": "buy", "expected_operation_id": "manual_order", "fixture_action": "safe_execution"}]}), encoding="utf-8")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_ACTIONS", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "1")
    with pytest.raises(ValueError, match="fixture_action_operation_blocked"):
        list(module.load_manifest(manifest_root=manifest_dir, manifest_id="unsafe"))
    with pytest.raises(ValueError, match="manifest_id_invalid"):
        module.manifest_path(manifest_root=manifest_dir, manifest_id="../escape")


def test_manifest_allows_explicitly_authorized_safe_fixture_execution(monkeypatch, tmp_path):
    module = _module()
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "safe.json").write_text(json.dumps({"cases": [{"case_id": "one", "message": "add BTC", "expected_operation_id": "watchlist_add", "fixture_action": "safe_execution", "idempotency_replay": True}]}), encoding="utf-8")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_ACTIONS", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "1")
    assert list(module.load_manifest(manifest_root=manifest_dir, manifest_id="safe"))[0]["fixture_action"] == "safe_execution"


def test_workflow_scopes_fixture_authorization_to_the_runner_subprocess():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "export FINN_QA_ALLOW_FIXTURE_ACTIONS=0" in workflow
    assert "export FINN_QA_ALLOW_FIXTURE_EXECUTION=0" in workflow
    assert "allow_fixture_actions=\"$9\"" in workflow
    assert "allow_safe_fixture_execution=\"${10}\"" in workflow


def test_encrypted_manifest_is_only_staged_after_server_side_decryption(tmp_path):
    module = _module()
    private_key = tmp_path / "secrets" / "manifest.key"
    manifest = tmp_path / "sealed.json"
    manifest.write_text(json.dumps({"cases": [{"case_id": "one", "message": "Wat betekent RSI?"}]}), encoding="utf-8")
    public_key = module.manifest_public_key(crypto_script=CRYPTO_SCRIPT_PATH, private_key_path=private_key)
    bundle = tmp_path / "manifest.bundle"
    import subprocess
    subprocess.run(
        ["python3", str(CRYPTO_SCRIPT_PATH), "encrypt", "--public-key", public_key, "--manifest", str(manifest)],
        check=True,
        stdout=bundle.open("w", encoding="utf-8"),
    )
    root = tmp_path / "qa-manifests"
    staged = module.stage_manifest_bundle(
        crypto_script=CRYPTO_SCRIPT_PATH,
        private_key_path=private_key,
        bundle_path=bundle,
        manifest_root=root,
        manifest_id="qa-scope",
    )
    assert staged == root / "qa-scope.json"
    assert json.loads(staged.read_text(encoding="utf-8"))["cases"][0]["case_id"] == "one"
    assert oct(staged.stat().st_mode & 0o777) == "0o600"


def test_auth_preflight_does_not_persist_auth_payload(monkeypatch):
    module = _module()
    monkeypatch.setattr(module, "request_json", lambda **_kwargs: (200, {"email": "fixture@example.test", "id": 99}, 12.0, None))
    result = module.authenticated_preflight(base_url="https://example.test", token="never-persist")
    assert result == {"http_status": 200, "latency_ms": 12.0, "error_category": None, "fixture_authenticated": True}


def test_missing_fixture_binding_fails_without_invoking_the_issuer(monkeypatch, tmp_path):
    module = _module()
    monkeypatch.delenv("FINN_QA_USER_ID", raising=False)
    with pytest.raises(RuntimeError, match="fixture_binding_invalid"):
        module.issue_fixture_token(issuer=tmp_path / "issuer.py")


def test_release_identity_marks_any_sha_mismatch(monkeypatch, tmp_path):
    module = _module()

    class Completed:
        stdout = "a" * 40

    monkeypatch.setattr(module.subprocess, "run", lambda *_args, **_kwargs: Completed())
    monkeypatch.setattr(module, "request_json", lambda **_kwargs: (200, {"commit_sha": "b" * 40}, 1.0, None))
    marker = tmp_path / "LAST_GOOD_COMMIT"
    marker.write_text("a" * 40, encoding="utf-8")
    result = module.release_identity(release_sha="a" * 40, checkout=tmp_path, release_marker=marker, base_url="https://example.test")
    assert result["matches"] is False


def test_release_identity_accepts_nested_backend_build_sha(monkeypatch, tmp_path):
    module = _module()

    class Completed:
        stdout = "a" * 40

    responses = iter([
        (200, {"status": "ok", "build": {"commit_sha": "a" * 40}}, 1.0, None),
        (200, {"service": "frontend", "commit_sha": "a" * 40}, 1.0, None),
    ])
    monkeypatch.setattr(module.subprocess, "run", lambda *_args, **_kwargs: Completed())
    monkeypatch.setattr(module, "request_json", lambda **_kwargs: next(responses))
    marker = tmp_path / "LAST_GOOD_COMMIT"
    marker.write_text("a" * 40, encoding="utf-8")

    result = module.release_identity(release_sha="a" * 40, checkout=tmp_path, release_marker=marker, base_url="https://example.test")

    assert result["public_backend"]["sha"] == "a" * 40
    assert result["matches"] is True


def test_safe_projection_excludes_response_content_and_preserves_contract_metadata():
    module = _module()
    projection = module.safe_projection({
        "run_id": "run-1", "status": "completed", "mode": "READ",
        "response": {"mode": "READ", "content": "private response"},
        "runtime_trace": {"initial_operation_id": "capability", "final_operation_id": "capability", "private": "omit"},
    })
    assert projection["runtime_trace"]["initial_operation_id"] == "capability"
    assert "private response" not in json.dumps(projection)
    assert "private" not in projection["runtime_trace"]
