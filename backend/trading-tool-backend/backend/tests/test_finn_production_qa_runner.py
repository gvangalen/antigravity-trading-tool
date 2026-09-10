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


def test_internal_runtime_diagnostic_never_exports_raw_exception_text():
    module = _module()
    assert module.classify_internal_issue('duplicate key value violates unique constraint "secret_name"') == "database_unique_constraint"
    assert module.classify_internal_issue("ValidationError: private details") == "validation"
    assert module.classify_internal_issue("unrecognized internal message") == "internal_unclassified"


def test_runtime_diagnostic_reuses_one_private_event_loop(monkeypatch):
    module = _module()
    module._DIAGNOSTIC_LOOP = None
    calls = []

    async def diagnostic(run_id):
        calls.append(run_id)
        return {"run_error_code": None, "orchestrator_issue_categories": []}

    monkeypatch.setattr(module, "_load_runtime_diagnostic", diagnostic)
    assert module.runtime_diagnostic("run-one")["orchestrator_issue_categories"] == []
    first_loop = module._DIAGNOSTIC_LOOP
    assert module.runtime_diagnostic("run-two")["orchestrator_issue_categories"] == []
    assert module._DIAGNOSTIC_LOOP is first_loop
    assert calls == ["run-one", "run-two"]


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
        list(module.load_manifest(
            manifest_root=manifest_dir,
            manifest_id="unsafe",
            fixture_namespace="qa-34510823510-f8cbd9c1-a1b2c3d4",
        ))
    with pytest.raises(ValueError, match="manifest_id_invalid"):
        module.manifest_path(manifest_root=manifest_dir, manifest_id="../escape")


def test_manifest_allows_explicitly_authorized_safe_fixture_execution(monkeypatch, tmp_path):
    module = _module()
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "safe.json").write_text(json.dumps({"cases": [{"case_id": "one", "message": "add BTC", "expected_operation_id": "watchlist_add", "fixture_action": "safe_execution", "idempotency_replay": True}]}), encoding="utf-8")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_ACTIONS", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "1")
    assert list(module.load_manifest(
        manifest_root=manifest_dir,
        manifest_id="safe",
        fixture_namespace="qa-34510823510-f8cbd9c1-a1b2c3d4",
    ))[0]["fixture_action"] == "safe_execution"


def test_workflow_scopes_fixture_authorization_to_the_runner_subprocess():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "export FINN_QA_ALLOW_FIXTURE_ACTIONS=0" in workflow
    assert "export FINN_QA_ALLOW_FIXTURE_EXECUTION=0" in workflow
    assert "allow_fixture_actions=\"$9\"" in workflow
    assert "allow_safe_fixture_execution=\"${10}\"" in workflow
    assert "Create isolated fixture namespace" in workflow
    assert "FINN_QA_FIXTURE_NAMESPACE" in workflow
    assert "--fixture-namespace \"$fixture_namespace\"" in workflow


def test_workflow_runs_hashed_control_plane_runner_against_product_checkout():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "Checkout QA control plane" in workflow
    assert "path: .qa-control-plane" in workflow
    assert "control_plane_runner=\".qa-control-plane/backend/trading-tool-backend/backend/scripts/run_finn_production_qa.py\"" in workflow
    assert "runner_sha256=\"$(sha256sum \"$control_plane_runner\"" in workflow
    assert "test \"$(sha256sum \"$runner_path\"" in workflow
    assert "python3 \"$runner_path\"" in workflow
    assert "--runner-revision \"$runner_revision\"" in workflow
    assert "python3 backend/trading-tool-backend/backend/scripts/run_finn_production_qa.py" not in workflow


def test_encrypted_manifest_is_only_staged_after_server_side_decryption(tmp_path):
    module = _module()
    private_key = tmp_path / "secrets" / "manifest.key"
    manifest = tmp_path / "sealed.json"
    manifest.write_text(json.dumps({"cases": [{"case_id": "one", "message": "Wat betekent RSI?"}]}), encoding="utf-8")
    public_key = module.manifest_public_key(crypto_script=CRYPTO_SCRIPT_PATH, private_key_path=private_key)
    bundle = tmp_path / "manifest.bundle"
    import subprocess
    subprocess.run(
        ["python3", str(CRYPTO_SCRIPT_PATH), "encrypt", f"--public-key={public_key}", "--manifest", str(manifest)],
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
    assert result == {"http_status": 200, "latency_ms": 12.0, "error_category": None, "fixture_authenticated": True, "attempt_count": 1}


def test_auth_preflight_retries_only_a_transient_read_failure(monkeypatch):
    module = _module()
    responses = iter([
        (599, {}, 10_000.0, "clienttimeout"),
        (200, {"id": 99}, 15.0, None),
    ])
    monkeypatch.setattr(module, "request_json", lambda **_kwargs: next(responses))
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)

    result = module.authenticated_preflight(base_url="https://example.test", token="never-persist")

    assert result == {"http_status": 200, "latency_ms": 10015.0, "error_category": None, "fixture_authenticated": True, "attempt_count": 2}


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
        "runtime_trace": {
            "contract_id": "contract-1", "contract_revision": 4,
            "initial_operation_id": "capability", "final_operation_id": "capability",
            "dispatch_id": "dispatch-1", "dispatch_count": 1, "attempt_count": 1,
            "supplied_inputs": {"asset": "BTC"}, "missing_inputs": [],
            "required_inputs": ["asset"], "action_polarity": "add",
            "private": "omit",
        },
    })
    assert projection["runtime_trace"]["initial_operation_id"] == "capability"
    assert projection["runtime_trace"]["contract_id"] == "contract-1"
    assert projection["runtime_trace"]["contract_revision"] == 4
    assert projection["runtime_trace"]["supplied_inputs"] == {"asset": "BTC"}
    assert projection["runtime_trace"]["required_inputs"] == ["asset"]
    assert projection["runtime_trace"]["action_polarity"] == "add"
    assert projection["runtime_trace"]["dispatch_count"] == 1
    assert "private response" not in json.dumps(projection)
    assert "private" not in projection["runtime_trace"]


def test_failed_terminal_is_a_product_failure_even_when_delivery_is_consistent():
    module = _module()
    assert module.classify_case_failure({
        "create_http_status": 200,
        "polling_sse_equal": True,
        "terminal": {"status": "failed"},
        "fixture_action": {"mode": "read_only"},
    }) == "product"


def test_runner_uses_gateway_created_conversation_for_follow_up(monkeypatch):
    module = _module()
    calls = []
    responses = iter([
        (200, {"run_id": "run-parent", "conversation_id": "conversation-live", "status": "pending"}, 1.0, None),
        (200, {"run_id": "run-parent", "conversation_id": "conversation-live", "status": "completed", "mode": "READ", "response": {}, "runtime_trace": {"initial_operation_id": "capability"}}, 1.0, None),
        (200, {"run_id": "run-child", "conversation_id": "conversation-live", "status": "pending"}, 1.0, None),
        (200, {"run_id": "run-child", "conversation_id": "conversation-live", "status": "completed", "mode": "READ", "response": {}, "runtime_trace": {"initial_operation_id": "explain_previous_evidence"}}, 1.0, None),
    ])

    def request(**kwargs):
        calls.append(kwargs)
        return next(responses)

    monkeypatch.setattr(module, "request_json", request)
    monkeypatch.setattr(module, "request_sse_terminal", lambda **kwargs: (
        {"run_id": "run-parent" if "run-parent" in kwargs["url"] else "run-child", "conversation_id": "conversation-live", "status": "completed", "mode": "READ", "response": {}, "runtime_trace": {"initial_operation_id": "capability" if "run-parent" in kwargs["url"] else "explain_previous_evidence"}},
        None,
    ))
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)

    result = module.run_cases(base_url="https://example.test", token="token", cases=[
        {"case_id": "parent", "message": "Wat kan je?", "conversation_id": "logical-flow", "expected_operation_id": "capability"},
        {"case_id": "child", "message": "Waarom?", "conversation_id": "logical-flow", "expected_operation_id": "explain_previous_evidence"},
    ])

    create_calls = [call for call in calls if call.get("method") == "POST"]
    assert "conversation_id" not in create_calls[0]["payload"]
    assert create_calls[1]["payload"]["conversation_id"] == "conversation-live"
    assert result[1]["conversation_id"] == "conversation-live"


def test_runner_materializes_a_unique_natural_fixture_namespace_without_ids():
    module = _module()
    case = {
        "case_id": "setup",
        "message": "Maak een setup met de naam {{qa_run_namespace}}-setup.",
        "workspace_hints": {"label": "{{qa_run_namespace}}"},
    }

    materialized = module.materialize_fixture_namespace(case, namespace="qa-34454930988")

    assert materialized["message"] == "Maak een setup met de naam qa-34454930988-setup."
    assert materialized["workspace_hints"]["label"] == "qa-34454930988"
    assert case["message"].endswith("{{qa_run_namespace}}-setup.")
    assert "setup_id" not in json.dumps(materialized)


def test_manifest_rejects_an_object_create_case_without_a_workflow_namespace(tmp_path, monkeypatch):
    module = _module()
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_ACTIONS", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "1")
    (tmp_path / "matrix.json").write_text(json.dumps({"cases": [{
        "case_id": "setup-create",
        "message": "Maak een setup met de naam vaste naam.",
        "fixture_action": "safe_execution",
        "expected_operation_id": "create_setup",
    }]}), encoding="utf-8")

    with pytest.raises(ValueError, match="fixture_namespace_required"):
        list(module.load_manifest(manifest_root=tmp_path, manifest_id="matrix"))


def test_sealed_manifest_without_token_accepts_a_runtime_namespace_and_stays_immutable(tmp_path, monkeypatch):
    module = _module()
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_ACTIONS", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "1")
    manifest = tmp_path / "matrix.json"
    manifest.write_text(json.dumps({"cases": [{
        "case_id": "setup-create",
        "message": "Maak een setup met de naam momentum.",
        "fixture_action": "safe_execution",
        "expected_operation_id": "create_setup",
    }]}), encoding="utf-8")
    before = module.sha256_file(manifest)

    cases = list(module.load_manifest(
        manifest_root=tmp_path,
        manifest_id="matrix",
        fixture_namespace="qa-34510823510-f8cbd9c1-a1b2c3d4",
    ))

    assert cases[0]["message"] == "Maak een setup met de naam momentum."
    assert module.sha256_file(manifest) == before


def test_fixture_preflight_recognizes_full_matrix_without_product_calls(tmp_path, monkeypatch):
    module = _module()
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_ACTIONS", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "1")
    operations = [
        "select_asset", "watchlist_add", "watchlist_remove",
        "create_indicator_configuration", "update_indicator_configuration", "delete_indicator_configuration",
        "create_setup", "update_setup", "create_strategy", "update_strategy",
        "create_bot", "update_bot", "deactivate_bot", "delete_bot", "delete_strategy", "delete_setup",
    ]
    cases = [
        {"case_id": f"write-{index}", "message": f"fixture {index}", "fixture_action": "safe_execution", "expected_operation_id": operation}
        for index, operation in enumerate(operations)
    ]
    cases.extend({"case_id": f"read-{index}", "message": "Lees status"} for index in range(21))
    manifest = tmp_path / "matrix.json"
    manifest.write_text(json.dumps({"cases": cases}), encoding="utf-8")
    base_hash = module.sha256_file(manifest)

    loaded = list(module.load_manifest(
        manifest_root=tmp_path,
        manifest_id="matrix",
        fixture_namespace="qa-34510823510-f8cbd9c1-a1b2c3d4",
    ))
    preflight = module.fixture_preflight(loaded, fixture_namespace="qa-34510823510-f8cbd9c1-a1b2c3d4")

    assert preflight == {
        "planned_cases": 37,
        "write_contracts_recognized": 16,
        "lineage_dependencies_recognized": 9,
        "fixture_namespace_present": True,
        "product_calls_executed": 0,
    }
    assert module.sha256_file(manifest) == base_hash


def test_missing_namespace_is_blocked_before_any_product_call(tmp_path, monkeypatch):
    module = _module()
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_ACTIONS", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "1")
    (tmp_path / "matrix.json").write_text(json.dumps({"cases": [{
        "case_id": "setup-create", "message": "Maak setup.",
        "fixture_action": "safe_execution", "expected_operation_id": "create_setup",
    }]}), encoding="utf-8")
    report = tmp_path / "report.json"
    monkeypatch.setattr(module, "parse_args", lambda: type("Args", (), {
        "release_sha": "a" * 40, "profile": "full_release_acceptance", "manifest_id": "matrix",
        "run_label": "blocked-preflight", "base_url": "https://example.test", "checkout": str(tmp_path),
        "release_marker": str(tmp_path / "marker"), "manifest_root": str(tmp_path),
        "manifest_bundle_path": None, "manifest_private_key_path": str(tmp_path / "key"),
        "manifest_crypto_script": None, "report_path": str(report), "workflow_run_id": "34510823510",
        "fixture_namespace": None, "dry_preflight": True,
    })())
    monkeypatch.setattr(module, "request_json", lambda **_kwargs: pytest.fail("product call"))

    assert module.main() == 1
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["outcome"] == "blocked"
    assert payload["qa_status"] == "QA BLOCKED / NOT STARTED"
    assert payload["planned_count"] == 1
    assert payload["cases"] == []


def test_all_downstream_fixture_cases_receive_the_same_execution_namespace():
    module = _module()
    namespace = "qa-34510823510-f8cbd9c1-a1b2c3d4"
    create = module.materialize_fixture_namespace({
        "case_id": "create", "message": "Maak een setup.", "fixture_action": "safe_execution",
        "expected_operation_id": "create_setup",
    }, namespace=namespace)
    downstream = module.materialize_fixture_namespace({
        "case_id": "update", "message": "Wijzig die setup.", "fixture_action": "safe_execution",
        "expected_operation_id": "update_setup",
    }, namespace=namespace)

    assert create["client_context"]["fixture_namespace"] == namespace
    assert create["client_context"]["fixture_name_suffix"] == namespace
    assert namespace in create["message"]
    assert downstream["client_context"]["fixture_namespace"] == namespace
    assert downstream["client_context"]["fixture_lineage_namespace"] == namespace
    assert namespace in downstream["message"]
    assert "setup_id" not in json.dumps(create)


def test_distinct_workflow_namespaces_are_not_interchangeable():
    module = _module()
    first = module.materialize_fixture_namespace(
        {"case_id": "one", "message": "Maak setup.", "fixture_action": "safe_execution", "expected_operation_id": "create_setup"},
        namespace="qa-34510823510-f8cbd9c1-a1b2c3d4",
    )
    second = module.materialize_fixture_namespace(
        {"case_id": "two", "message": "Maak setup.", "fixture_action": "safe_execution", "expected_operation_id": "create_setup"},
        namespace="qa-34510823511-f8cbd9c1-e5f6a7b8",
    )

    assert first["client_context"]["fixture_namespace"] != second["client_context"]["fixture_namespace"]


def test_fixture_confirmation_includes_required_idempotency_key(monkeypatch):
    module = _module()
    calls = []
    responses = iter([
        (200, {"proposal_id": "proposal-1", "status": "pending", "proposal_version": "v1", "payload_hash": "hash", "confirmation_required": True}, 1.0, None),
        (200, {"confirmation_token": "secret", "payload_hash": "hash"}, 1.0, None),
        (200, {"status": "succeeded"}, 1.0, None),
    ])
    monkeypatch.setattr(module, "request_json", lambda **kwargs: (calls.append(kwargs) or next(responses)))
    result = module._run_fixture_action(
        base_url="https://example.test", token="token",
        case={"fixture_action": "confirmation"},
        terminal={"response": {"proposal_id": "proposal-1"}, "runtime_trace": {"contract_revision": 3}},
    )
    confirm_call = calls[2]
    assert result["confirm_status"] == 200
    assert result["proposal"]["contract_revision"] == 3
    assert confirm_call["payload"]["idempotency_key"].startswith("qa-confirm-")
    assert "secret" not in json.dumps(result)


def test_fixture_execution_requires_a_successful_terminal_execution_status(monkeypatch):
    module = _module()
    responses = iter([
        (200, {"proposal_id": "proposal-1", "status": "pending", "payload_hash": "hash", "confirmation_required": True}, 1.0, None),
        (200, {"confirmation_token": "secret", "payload_hash": "hash"}, 1.0, None),
        (200, {}, 1.0, None),
        (200, {"status": "blocked"}, 1.0, None),
    ])
    monkeypatch.setattr(module, "request_json", lambda **_kwargs: next(responses))

    result = module._run_fixture_action(
        base_url="https://example.test", token="token", case={"fixture_action": "safe_execution"},
        terminal={"response": {"proposal_id": "proposal-1"}, "runtime_trace": {}},
    )

    assert result["execute_status"] == 200
    assert result["execution_status"] == "blocked"
    assert result["error_category"] == "proposal_execute_failed"


def test_incomplete_action_is_a_typed_contract_outcome_not_proposal_missing():
    module = _module()
    result = module._run_fixture_action(
        base_url="https://example.test", token="token",
        case={"fixture_action": "proposal", "expected_missing_inputs": ["name", "timeframe"]},
        terminal={"runtime_trace": {"missing_inputs": ["timeframe", "name"]}},
    )

    assert result == {
        "mode": "proposal", "proposal": {}, "publish_status": None, "confirm_status": None,
        "execute_status": None, "idempotency_replay_status": None, "outcome": "missing_inputs",
        "missing_inputs": ["timeframe", "name"],
    }


def test_case_content_failure_is_reported_without_runner_failure(monkeypatch, tmp_path):
    module = _module()
    monkeypatch.setattr(module, "release_identity", lambda **_kwargs: {"matches": True})
    monkeypatch.setattr(module, "issue_fixture_token", lambda **_kwargs: "token")
    monkeypatch.setattr(module, "authenticated_preflight", lambda **_kwargs: {"fixture_authenticated": True})
    monkeypatch.setattr(module, "sha256_file", lambda _path: "a" * 64)
    monkeypatch.setattr(module, "manifest_path", lambda **_kwargs: tmp_path / "manifest.json")
    monkeypatch.setattr(module, "manifest_cases", lambda _path: [{"case_id": "case", "message": "x"}])
    monkeypatch.setattr(module, "load_manifest", lambda **_kwargs: [{"case_id": "case", "message": "x"}])
    monkeypatch.setattr(module, "run_cases", lambda **_kwargs: [{"case_id": "case", "create_http_status": 200, "terminal": {"status": "completed"}, "polling_sse_equal": True, "operation_matches": False, "fixture_action": {"mode": "read_only"}}])
    report = tmp_path / "report.json"
    monkeypatch.setattr(module, "parse_args", lambda: type("Args", (), {
        "release_sha": "a" * 40, "profile": "targeted_regression", "manifest_id": "scope", "run_label": "run", "base_url": "https://example.test", "checkout": str(tmp_path), "release_marker": str(tmp_path / "marker"), "manifest_root": str(tmp_path), "manifest_bundle_path": None, "manifest_private_key_path": str(tmp_path / "key"), "manifest_crypto_script": None, "report_path": str(report), "workflow_run_id": "local",
    })())

    assert module.main() == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["outcome"] == "failed"
    assert payload["error_category"] is None


def test_case_failure_categories_do_not_count_transport_as_selector_failures():
    module = _module()
    cases = [
        {"error_category": "clienttimeout", "fixture_action": {}},
        {"create_http_status": 200, "terminal": {"status": "completed"}, "polling_sse_equal": True, "operation_matches": False, "fixture_action": {}},
        {"create_http_status": 200, "terminal": {"status": "completed"}, "polling_sse_equal": True, "operation_matches": True, "fixture_action": {"error_category": "proposal_missing"}},
    ]

    assert [module.classify_case_failure(case) for case in cases] == ["infrastructure", "product", "product"]
    assert module.failure_summary(cases) == {"product": 2, "runner": 0, "infrastructure": 1}


def test_case_timeout_is_checkpointed_and_does_not_block_the_next_case(monkeypatch):
    module = _module()
    original_sleep = module.time.sleep
    calls = []
    responses = iter([
        (200, {"run_id": "slow", "conversation_id": "c1", "status": "pending"}, 1.0, None),
        (200, {"run_id": "slow", "conversation_id": "c1", "status": "pending"}, 1.0, None),
        (200, {"run_id": "fast", "conversation_id": "c2", "status": "pending"}, 1.0, None),
        (200, {"run_id": "fast", "conversation_id": "c2", "status": "completed", "runtime_trace": {"initial_operation_id": "capability"}}, 1.0, None),
    ])
    monkeypatch.setattr(module, "request_json", lambda **kwargs: (calls.append(kwargs) or next(responses)))
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: original_sleep(0.01))
    monkeypatch.setattr(module, "request_sse_terminal", lambda **_kwargs: ({"status": "completed", "runtime_trace": {"initial_operation_id": "capability"}}, None))
    checkpoints = []
    results = module.run_cases(base_url="https://example.test", token="token", case_timeout_seconds=0.005, checkpoint=lambda rows, **_kwargs: checkpoints.append(list(rows)), cases=[
        {"case_id": "slow", "message": "slow"},
        {"case_id": "fast", "message": "fast", "expected_operation_id": "capability"},
    ])
    assert results[0]["error_category"] == "case_timeout"
    assert results[1]["run_id"] == "fast"
    assert len(checkpoints) == 2


def test_timeout_checkpoint_is_a_valid_partial_artifact(tmp_path):
    report = tmp_path / "report.json"
    payload = {"schema_version": 1, "cases": [{"case_id": "slow", "error_category": "case_timeout"}], "incomplete": True}
    temporary = report.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(report)
    assert json.loads(report.read_text(encoding="utf-8")) == payload


def test_matrix_deadline_marks_each_unattempted_case_and_preserves_prior_failure(monkeypatch):
    module = _module()
    clock_calls = 0

    def monotonic():
        nonlocal clock_calls
        clock_calls += 1
        return 0.0 if clock_calls <= 3 else 2.0

    monkeypatch.setattr(module.time, "monotonic", monotonic)
    monkeypatch.setattr(module, "request_json", lambda **_kwargs: (500, {}, 1.0, "server_http_response"))
    checkpoints = []

    results = module.run_cases(
        base_url="https://example.test",
        token="token",
        matrix_deadline_seconds=1.0,
        cases=[
            {"case_id": "executed", "message": "first"},
            {"case_id": "not-run-1", "message": "second"},
            {"case_id": "not-run-2", "message": "third"},
            {"case_id": "not-run-3", "message": "fourth"},
            {"case_id": "not-run-4", "message": "fifth"},
            {"case_id": "not-run-5", "message": "sixth"},
        ],
        checkpoint=lambda rows, **kwargs: checkpoints.append((list(rows), kwargs)),
    )

    assert [item["case_id"] for item in results] == ["executed", "not-run-1", "not-run-2", "not-run-3", "not-run-4", "not-run-5"]
    assert all(item["case_status"] == "not_run" for item in results[1:])
    progress = module.case_progress(cases=results, planned_count=6)
    assert progress == {
        "planned_count": 6,
        "attempted_count": 1,
        "completed_count": 1,
        "failed_count": 1,
        "not_run_count": 5,
        "incomplete": True,
    }
    assert checkpoints[-1][1]["planned_count"] == 6


def test_case_progress_marks_thirty_two_of_thirty_seven_as_incomplete():
    module = _module()
    cases = [
        {"case_id": f"done-{index}", "case_status": "completed", "create_http_status": 200,
         "terminal": {"status": "completed"}, "polling_sse_equal": True,
         "operation_matches": True, "fixture_action": {}}
        for index in range(32)
    ]
    cases.extend({"case_id": f"not-run-{index}", "case_status": "not_run", "error_category": "matrix_deadline"} for index in range(5))

    progress = module.case_progress(cases=cases, planned_count=37)

    assert progress["attempted_count"] == 32
    assert progress["completed_count"] == 32
    assert progress["not_run_count"] == 5
    assert progress["incomplete"] is True
