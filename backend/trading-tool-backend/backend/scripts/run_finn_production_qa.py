#!/usr/bin/env python3
"""Run a sanitized FINN production-QA profile from the protected host.

This program is invoked by the GitHub Actions QA runner on the production host.
It never prints the fixture token and writes only a redacted report.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

from backend.scripts.finn_v2_matrix_transport import TERMINAL_STATUSES, observe_terminal


ALLOWED_PROFILES = {
    "auth_preflight",
    "manifest_key",
    "targeted_regression",
    "runtime_acceptance",
    "full_release_acceptance",
    "safety",
    "latency",
}
SENSITIVE_KEYS = {"access_token", "authorization", "authorization_header", "cookie", "email", "password", "private_key", "secret", "token", "user_id"}
FIXTURE_ACTION_MODES = {"read_only", "proposal", "confirmation", "safe_execution"}
INFRASTRUCTURE_ERROR_CATEGORIES = {"dns", "connect", "tls", "clienttimeout", "client", "ssh"}
_DIAGNOSTIC_LOOP: Optional[asyncio.AbstractEventLoop] = None
QA_NAMESPACE_TOKEN = "{{qa_run_namespace}}"
NAMESPACED_FIXTURE_CREATE_OPERATIONS = {
    "create_setup",
    "create_strategy",
    "create_bot",
}
LINEAGE_DEPENDENT_FIXTURE_OPERATIONS = {
    "update_setup",
    "create_strategy",
    "update_strategy",
    "create_bot",
    "update_bot",
    "deactivate_bot",
    "delete_bot",
    "delete_strategy",
    "delete_setup",
}


def classify_internal_issue(value: object) -> str:
    """Expose a stable error class without exporting database or exception text."""
    text = str(value or "").lower()
    if "unique" in text or "duplicate" in text:
        return "database_unique_constraint"
    if "foreign key" in text:
        return "database_foreign_key"
    if "not null" in text:
        return "database_not_null"
    if "undefinedcolumn" in text or "does not exist" in text or "column" in text:
        return "database_schema"
    if "timeout" in text or "deadline" in text:
        return "timeout"
    if "validation" in text or "pydantic" in text:
        return "validation"
    if "orchestrator_result_exists" in text:
        return "orchestrator_result_exists"
    if "reasoning_dependencies_missing" in text:
        return "reasoning_dependencies_missing"
    return "internal_unclassified"


async def _load_runtime_diagnostic(run_id: str) -> Dict[str, Any]:
    """Read only typed failure categories for a QA-created run on this host."""
    from sqlalchemy import select

    from backend.infrastructure.database import async_session_factory
    from backend.infrastructure.models import FinnV2Run, FinnV2RunTrace

    async with async_session_factory() as session:
        run = (
            await session.execute(select(FinnV2Run).where(FinnV2Run.id == run_id).limit(1))
        ).scalars().first()
        traces = (
            await session.execute(
                select(FinnV2RunTrace)
                .where(
                    FinnV2RunTrace.run_id == run_id,
                    FinnV2RunTrace.event_type == "orchestrator_failed",
                )
                .order_by(FinnV2RunTrace.event_order.desc())
                .limit(1)
            )
        ).scalars().first()

    issues = []
    if traces is not None:
        payload = traces.payload_json if isinstance(traces.payload_json, dict) else {}
        issues = list(payload.get("issue_codes") or [])
    return {
        "run_error_code": getattr(run, "error_code", None),
        "orchestrator_issue_categories": sorted({classify_internal_issue(issue) for issue in issues}),
    }


def runtime_diagnostic(run_id: str) -> Dict[str, Any]:
    """Keep diagnostic read failures separate from the product result."""
    global _DIAGNOSTIC_LOOP
    try:
        # SQLAlchemy's async pool belongs to an event loop. Reusing one loop
        # for this short-lived runner avoids cross-loop transport failures on
        # later cases without touching the production application's loop.
        if _DIAGNOSTIC_LOOP is None:
            _DIAGNOSTIC_LOOP = asyncio.new_event_loop()
        return _DIAGNOSTIC_LOOP.run_until_complete(_load_runtime_diagnostic(run_id))
    except Exception:
        return {"diagnostic_status": "unavailable"}


def redact(value: Any) -> Any:
    """Remove credentials and private fixture identity from persisted reports."""
    if isinstance(value, dict):
        return {key: "[REDACTED]" if key.lower() in SENSITIVE_KEYS else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def classify_transport_error(error: BaseException) -> str:
    if isinstance(error, ssl.SSLError):
        return "tls"
    if isinstance(error, (TimeoutError, socket.timeout)):
        return "clienttimeout"
    if isinstance(error, socket.gaierror):
        return "dns"
    if isinstance(error, urllib.error.URLError):
        reason = error.reason
        if isinstance(reason, ssl.SSLError):
            return "tls"
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return "clienttimeout"
        if isinstance(reason, socket.gaierror):
            return "dns"
        return "connect"
    if isinstance(error, ConnectionError):
        return "connect"
    return "client"


def request_json(
    *, url: str, method: str = "GET", token: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None, timeout_seconds: float = 15.0,
) -> Tuple[int, Dict[str, Any], float, Optional[str]]:
    # Every request is deliberately short-lived.  A matrix must not retain a
    # socket from a timed-out case and let it contaminate a later case.
    headers = {
        "Accept": "application/json",
        "Connection": "close",
        "User-Agent": "FINN-Production-QA-Runner/1.0",
    }
    body = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    started = time.monotonic()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers, method=method), timeout=timeout_seconds) as response:
            raw = response.read()
            parsed = json.loads(raw.decode("utf-8")) if raw else {}
            return int(response.status), parsed if isinstance(parsed, dict) else {}, (time.monotonic() - started) * 1000, None
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            parsed = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = {}
        return int(error.code), parsed if isinstance(parsed, dict) else {}, (time.monotonic() - started) * 1000, "server_http_response"
    except (urllib.error.URLError, TimeoutError, socket.timeout, ssl.SSLError, ConnectionError) as error:
        return 599, {}, (time.monotonic() - started) * 1000, classify_transport_error(error)


def request_sse_terminal(*, url: str, token: str, timeout_seconds: float = 35.0) -> Tuple[Dict[str, Any], Optional[str]]:
    """Read only the terminal envelope from SSE and discard all response text."""
    headers = {
        "Accept": "text/event-stream",
        "Authorization": f"Bearer {token}",
        "Connection": "close",
        "User-Agent": "FINN-Production-QA-Runner/1.0",
    }
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout_seconds) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                try:
                    payload = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict) and payload.get("status") in TERMINAL_STATUSES:
                    return payload, None
        return {}, "client"
    except (urllib.error.URLError, TimeoutError, socket.timeout, ssl.SSLError, ConnectionError) as error:
        return {}, classify_transport_error(error)


def _read(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def published_build_sha(payload: Dict[str, Any]) -> Optional[str]:
    """Read the canonical build SHA from either supported public envelope."""
    build = payload.get("build")
    nested = build if isinstance(build, dict) else {}
    value = (
        payload.get("commit_sha")
        or payload.get("build_commit")
        or payload.get("sha")
        or nested.get("commit_sha")
        or nested.get("build_commit")
        or nested.get("sha")
    )
    return value if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) else None


def release_identity(*, release_sha: str, checkout: Path, release_marker: Path, base_url: str) -> Dict[str, Any]:
    head = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"], check=False, capture_output=True, text=True).stdout.strip() or None
    marker = _read(release_marker)
    health_status, health, health_latency, health_error = request_json(url=f"{base_url}/api/health")
    frontend_status, frontend, frontend_latency, frontend_error = request_json(url=f"{base_url}/build-info.json")
    backend_sha = published_build_sha(health)
    frontend_sha = published_build_sha(frontend)
    return {
        "expected_sha": release_sha, "checkout_sha": head, "release_marker_sha": marker,
        "public_backend": {"http_status": health_status, "sha": backend_sha, "latency_ms": round(health_latency, 2), "error_category": health_error},
        "public_frontend": {"http_status": frontend_status, "sha": frontend_sha, "latency_ms": round(frontend_latency, 2), "error_category": frontend_error},
        "matches": all(candidate == release_sha for candidate in (head, marker, backend_sha, frontend_sha)),
    }


def issue_fixture_token(*, issuer: Path) -> str:
    user_id = os.environ.get("FINN_QA_USER_ID", "")
    if not user_id.isdecimal() or int(user_id) <= 0:
        raise RuntimeError("fixture_binding_invalid")
    result = subprocess.run([sys.executable, str(issuer), "--user-id", user_id, "--minutes", "5"], check=False, capture_output=True, text=True, env=os.environ.copy())
    if result.returncode != 0:
        raise RuntimeError("token_issuance_failed")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("token_issuance_invalid") from error
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise RuntimeError("token_issuance_invalid")
    return token


def authenticated_preflight(*, base_url: str, token: str) -> Dict[str, Any]:
    """Authenticate the fixture without treating one transient read timeout as final.

    This is deliberately limited to the idempotent ``GET /api/auth/me`` preflight.
    Run creation, confirmation, and execution are never retried here because their
    side effects require their own idempotency contracts.
    """
    attempts = 0
    total_latency = 0.0
    status = 599
    error_category: Optional[str] = None
    for attempt in range(2):
        attempts += 1
        status, _payload, latency, error_category = request_json(
            url=f"{base_url}/api/auth/me", token=token, timeout_seconds=10.0
        )
        total_latency += latency
        if status == 200 or error_category not in {"clienttimeout", "connect", "tls", "dns"}:
            break
        # A short bounded pause lets an already-restarting public worker recover.
        if attempt == 0:
            time.sleep(0.25)
    return {
        "http_status": status,
        "latency_ms": round(total_latency, 2),
        "error_category": error_category,
        "fixture_authenticated": status == 200,
        "attempt_count": attempts,
    }


def safe_projection(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """Keep contract provenance while never persisting response or fixture data."""
    trace = envelope.get("runtime_trace") if isinstance(envelope.get("runtime_trace"), dict) else {}
    response = envelope.get("response") if isinstance(envelope.get("response"), dict) else {}
    allowed = {
        "contract_id", "contract_revision", "initial_operation_id", "final_operation_id",
        "operation_change_reason", "canonical_target", "target_source", "target_type",
        "conversation_reference", "conversation_reference_kind", "dispatch_id", "dispatch_count", "attempt_count",
        "projection_version", "projection_hash", "terminal_response_type", "terminal_status",
        "requested_mode", "final_mode", "action_polarity", "required_inputs", "supplied_inputs", "missing_inputs", "proposal_lifecycle",
        "error_code", "terminal_reason", "timings_ms",
    }
    safe_response = {
        key: response.get(key)
        for key in ("mode", "proposal_id", "confirmation_required", "verifier_status")
        if key in response
    }
    return {
        "run_id": envelope.get("run_id"),
        "conversation_id": envelope.get("conversation_id"),
        "status": envelope.get("status"),
        "mode": envelope.get("mode"),
        "response": safe_response,
        "runtime_trace": {key: trace.get(key) for key in allowed if key in trace},
    }


def manifest_path(*, manifest_root: Path, manifest_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,80}", manifest_id):
        raise ValueError("manifest_id_invalid")
    root = manifest_root.resolve()
    path = (root / f"{manifest_id}.json").resolve()
    if root not in path.parents or not path.is_file():
        raise ValueError("manifest_not_found")
    return path


def manifest_cases(path: Path) -> list[Dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ValueError("manifest_cases_invalid")
    return cases


def load_manifest(
    *, manifest_root: Path, manifest_id: str, fixture_namespace: Optional[str] = None,
) -> Iterable[Dict[str, Any]]:
    """Validate QA-owned scope without exposing its cases outside the host."""
    if fixture_namespace:
        validate_fixture_namespace(fixture_namespace)
    cases = manifest_cases(manifest_path(manifest_root=manifest_root, manifest_id=manifest_id))
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("case_id"), str) or not isinstance(case.get("message"), str):
            raise ValueError("manifest_case_invalid")
        action_mode = case.get("fixture_action", "read_only")
        if action_mode not in FIXTURE_ACTION_MODES:
            raise ValueError("manifest_fixture_action_invalid")
        if action_mode != "read_only":
            if not fixture_namespace:
                raise ValueError("fixture_namespace_required")
            if os.environ.get("FINN_QA_ALLOW_FIXTURE_ACTIONS") != "1":
                raise ValueError("fixture_actions_not_authorized")
            if not isinstance(case.get("expected_operation_id"), str):
                raise ValueError("fixture_action_operation_required")
            from backend.services.finn_v2_execution_gate_service import SAFE_FIXTURE_EXECUTION_OPERATION_TYPES
            if case["expected_operation_id"] not in SAFE_FIXTURE_EXECUTION_OPERATION_TYPES:
                raise ValueError("fixture_action_operation_blocked")
        if action_mode == "safe_execution":
            if os.environ.get("FINN_QA_ALLOW_FIXTURE_EXECUTION") != "1":
                raise ValueError("fixture_execution_not_authorized")
            # Namespace isolation is execution context, not sealed corpus
            # content. The workflow supplies it separately so an approved
            # manifest remains byte-for-byte immutable across runs.
        expected_missing = case.get("expected_missing_inputs")
        if expected_missing is not None and (
            not isinstance(expected_missing, list) or not all(isinstance(item, str) and item for item in expected_missing)
        ):
            raise ValueError("manifest_expected_missing_inputs_invalid")
    return cases


def manifest_public_key(*, crypto_script: Path, private_key_path: Path) -> str:
    """Return only the public half of the server-side manifest keypair."""
    result = subprocess.run(
        [sys.executable, str(crypto_script), "public-key", "--private-key-path", str(private_key_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    public_key = result.stdout.strip()
    if result.returncode != 0 or not re.fullmatch(r"[A-Za-z0-9_-]{40,100}", public_key):
        raise RuntimeError("manifest_key_unavailable")
    return public_key


def stage_manifest_bundle(*, crypto_script: Path, private_key_path: Path, bundle_path: Path, manifest_root: Path, manifest_id: str) -> Path:
    """Decrypt an externally supplied QA bundle only on the protected host."""
    destination = manifest_root / f"{manifest_id}.json"
    manifest_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    manifest_root.chmod(0o700)
    if not bundle_path.is_file() or bundle_path.stat().st_size > 96_000:
        raise ValueError("manifest_bundle_invalid")
    temporary = destination.with_name(destination.name + f".{uuid.uuid4().hex}.tmp")
    result = subprocess.run(
        [
            sys.executable, str(crypto_script), "decrypt", "--private-key-path", str(private_key_path),
            "--bundle-path", str(bundle_path), "--output", str(temporary),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        temporary.unlink(missing_ok=True)
        raise ValueError("manifest_bundle_invalid")
    try:
        # Validate before atomically publishing the new QA-owned manifest.
        json.loads(temporary.read_text(encoding="utf-8"))
        temporary.replace(destination)
        destination.chmod(0o600)
    except Exception as error:
        temporary.unlink(missing_ok=True)
        raise ValueError("manifest_bundle_invalid") from error
    return destination


def _proposal_id(envelope: Dict[str, Any]) -> Optional[str]:
    response = envelope.get("response") if isinstance(envelope.get("response"), dict) else {}
    candidate = response.get("proposal_id") or envelope.get("proposal_id")
    return candidate if isinstance(candidate, str) and candidate else None


def _logical_conversation_key(case: Dict[str, Any]) -> Optional[str]:
    """Treat manifest IDs as local aliases, never as production conversation IDs."""
    value = case.get("conversation_key", case.get("conversation_id"))
    return value if isinstance(value, str) and value else None


def validate_fixture_namespace(namespace: Optional[str]) -> str:
    value = str(namespace or "").strip()
    if not re.fullmatch(r"qa-[a-z0-9-]{8,80}", value):
        raise ValueError("fixture_namespace_invalid")
    return value


def materialize_fixture_namespace(case: Dict[str, Any], *, namespace: str) -> Dict[str, Any]:
    """Bind QA-owned natural object names without ever injecting IDs.

    QA manifests may use ``{{qa_run_namespace}}`` in messages or context. The
    runner substitutes it only in its ephemeral request copy, so a matrix run
    cannot match objects left by a prior QA workflow.  Object IDs remain solely
    a product-side lineage/resolution concern.
    """
    namespace = validate_fixture_namespace(namespace)

    def replace(value: Any) -> Any:
        if isinstance(value, str):
            return value.replace(QA_NAMESPACE_TOKEN, namespace)
        if isinstance(value, list):
            return [replace(item) for item in value]
        if isinstance(value, dict):
            return {key: replace(item) for key, item in value.items()}
        return value

    materialized = replace(dict(case))
    action_mode = materialized.get("fixture_action", "read_only")
    operation_id = materialized.get("expected_operation_id")
    if action_mode != "read_only":
        client_context = materialized.get("client_context")
        client_context = dict(client_context) if isinstance(client_context, dict) else {}
        # The API-visible context lets the QA fixture resolver isolate names
        # without leaking an internal ID into natural-language requests.
        client_context["fixture_namespace"] = namespace
        if operation_id in NAMESPACED_FIXTURE_CREATE_OPERATIONS:
            client_context["fixture_name_suffix"] = namespace
        if operation_id in LINEAGE_DEPENDENT_FIXTURE_OPERATIONS:
            client_context["fixture_lineage_namespace"] = namespace
        materialized["client_context"] = client_context
        # Keep fixture isolation out of the user's message.  Appending a
        # natural-language instruction made the product correctly parse the
        # suffix itself as a supplied action field (notably ``name``).  The
        # public client-context binding is the runner's execution metadata;
        # it is not an action input and cannot change the sealed prompt's
        # semantics.
    return materialized


def fixture_preflight(cases: Iterable[Dict[str, Any]], *, fixture_namespace: Optional[str]) -> Dict[str, Any]:
    """Validate a matrix's runtime binding without issuing product requests."""
    case_list = list(cases)
    write_cases = [case for case in case_list if case.get("fixture_action", "read_only") != "read_only"]
    lineage_cases = [
        case for case in case_list
        if case.get("expected_operation_id") in LINEAGE_DEPENDENT_FIXTURE_OPERATIONS
    ]
    return {
        "planned_cases": len(case_list),
        "write_contracts_recognized": len(write_cases),
        "lineage_dependencies_recognized": len(lineage_cases),
        "fixture_namespace_present": bool(fixture_namespace),
        "product_calls_executed": 0,
    }


def classify_case_failure(case_result: Dict[str, Any]) -> Optional[str]:
    """Keep runner, transport, and observed FINN behavior separately scored."""
    category = case_result.get("error_category")
    if case_result.get("case_status") == "not_run":
        return "infrastructure"
    if isinstance(category, str) and category in INFRASTRUCTURE_ERROR_CATEGORIES:
        return "infrastructure"
    if isinstance(category, str) and category in {"runner_internal", "manifest_case_invalid"}:
        return "runner"
    action_error = (case_result.get("fixture_action") or {}).get("error_category")
    if action_error:
        return "product"
    if case_result.get("create_http_status") != 200:
        return "product" if category == "server_http_response" else "infrastructure"
    terminal = case_result.get("terminal") or {}
    if terminal.get("status") not in TERMINAL_STATUSES or not case_result.get("polling_sse_equal"):
        return "product"
    if terminal.get("status") == "failed":
        return "product"
    if case_result.get("operation_matches") is False:
        return "product"
    return None


def failure_summary(cases: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    summary = {"product": 0, "runner": 0, "infrastructure": 0}
    for item in cases:
        kind = classify_case_failure(item)
        if kind:
            summary[kind] += 1
    return summary


def case_progress(*, cases: Iterable[Dict[str, Any]], planned_count: int) -> Dict[str, int | bool]:
    """Report matrix completion independently from product correctness.

    A delivery timeout must never turn a partially written checkpoint into a
    complete matrix.  ``not_run`` is reserved for cases the runner never
    attempted; every attempted case remains evidence even when it failed.
    """
    rows = list(cases)
    explicit_not_run = sum(1 for item in rows if item.get("case_status") == "not_run")
    attempted = sum(1 for item in rows if item.get("case_status") != "not_run")
    completed = sum(1 for item in rows if item.get("case_status") == "completed")
    failed = sum(1 for item in rows if item.get("case_status") == "completed" and classify_case_failure(item))
    not_run = max(explicit_not_run, planned_count - attempted)
    return {
        "planned_count": planned_count,
        "attempted_count": attempted,
        "completed_count": completed,
        "failed_count": failed,
        "not_run_count": not_run,
        "incomplete": attempted < planned_count or not_run > 0 or len(rows) < planned_count,
    }


def add_missing_not_run_cases(
    *,
    results: Iterable[Dict[str, Any]],
    cases: Iterable[Dict[str, Any]],
    error_category: str,
) -> list[Dict[str, Any]]:
    """Preserve every planned case when a runner process exits unexpectedly.

    A checkpoint contains completed evidence, but it cannot prove completion
    for manifest rows the process never reached.  Materialising those rows
    makes an interruption resumable without hiding the missing work.
    """
    materialized = [dict(item) for item in results]
    recorded_ids = {str(item.get("case_id")) for item in materialized if item.get("case_id")}
    for case in cases:
        case_id = str(case["case_id"])
        if case_id not in recorded_ids:
            materialized.append({
                "case_id": case_id,
                "case_status": "not_run",
                "error_category": error_category,
            })
    return materialized


def settle_timed_out_run(
    *,
    base_url: str,
    token: str,
    run_id: str,
) -> Dict[str, Any]:
    """Terminalise a timed-out case before the sequential matrix advances.

    The API cancellation route persists a typed terminal projection.  This
    prevents an abandoned worker lifecycle from accumulating behind later
    cases while retaining the original timeout as the case result.
    """
    cancel_status, _cancelled, _cancel_latency, cancel_error = request_json(
        url=f"{base_url}/api/assistant/v2/runs/{run_id}/cancel",
        method="POST",
        token=token,
        payload={},
        timeout_seconds=5.0,
    )
    status, projection, _status_latency, status_error = request_json(
        url=f"{base_url}/api/assistant/v2/runs/{run_id}",
        token=token,
        timeout_seconds=5.0,
    )
    terminal_status = projection.get("status") if status == 200 and not status_error else None
    return {
        "cancel_attempted": True,
        "cancel_http_status": cancel_status,
        "cancel_error": cancel_error,
        "server_status_after_cleanup": terminal_status,
        "server_active_after_cleanup": terminal_status not in TERMINAL_STATUSES,
    }


def write_report_atomic(report_path: Path, report: Mapping[str, Any]) -> None:
    """Publish a sanitized checkpoint or final report without a torn file."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = report_path.with_suffix(report_path.suffix + ".tmp")
    temporary.write_text(json.dumps(redact(dict(report)), sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(report_path)


def _run_fixture_action(
    *,
    base_url: str,
    token: str,
    case: Dict[str, Any],
    terminal: Dict[str, Any],
    remaining_seconds=None,
) -> Dict[str, Any]:
    """Exercise only an explicitly enabled non-financial QA fixture action."""
    action_mode = case.get("fixture_action", "read_only")
    result: Dict[str, Any] = {
        "mode": action_mode, "proposal": {}, "publish_status": None, "confirm_status": None,
        "execute_status": None, "idempotency_replay_status": None, "outcome": "not_applicable",
    }
    def action_timeout() -> float:
        if remaining_seconds is None:
            return 15.0
        return max(0.1, min(15.0, float(remaining_seconds())))

    if remaining_seconds is not None and remaining_seconds() <= 0:
        result["outcome"] = "case_timeout"
        result["error_category"] = "case_timeout"
        return result
    if action_mode == "read_only":
        return result
    proposal_id = _proposal_id(terminal)
    if not proposal_id:
        trace = terminal.get("runtime_trace") if isinstance(terminal.get("runtime_trace"), dict) else {}
        missing_inputs = trace.get("missing_inputs") if isinstance(trace.get("missing_inputs"), list) else []
        if missing_inputs:
            result["outcome"] = "missing_inputs"
            result["missing_inputs"] = list(missing_inputs)
            expected_missing = case.get("expected_missing_inputs")
            if expected_missing is not None and set(expected_missing) == set(missing_inputs):
                return result
            result["error_category"] = "missing_inputs_unexpected"
            return result
        result["outcome"] = "proposal_missing"
        result["error_category"] = "proposal_missing"
        return result
    proposal_status, proposal, _latency, proposal_error = request_json(
        url=f"{base_url}/api/assistant/v2/proposals/{proposal_id}", token=token,
        timeout_seconds=action_timeout(),
    )
    if proposal_status != 200 or proposal_error:
        result["error_category"] = proposal_error or "proposal_read_failed"
        return result
    result["proposal"] = {
        key: proposal.get(key)
        for key in ("proposal_id", "status", "operation_type", "proposal_version", "contract_revision",
                    "requires_step_up_auth", "payload_hash", "confirmation_required")
        if key in proposal
    }
    trace = terminal.get("runtime_trace") if isinstance(terminal.get("runtime_trace"), dict) else {}
    if "contract_revision" in trace:
        result["proposal"]["contract_revision"] = trace["contract_revision"]
    result["outcome"] = "proposal_created"
    status, published, _latency, error = request_json(
        url=f"{base_url}/api/assistant/v2/proposals/{proposal_id}/publish",
        method="POST", token=token, payload={}, timeout_seconds=action_timeout(),
    )
    result["publish_status"] = status
    if status != 200 or error:
        result["error_category"] = error or "proposal_publish_failed"
        return result
    if action_mode == "proposal":
        return result
    confirmation_token = published.get("confirmation_token") if isinstance(published.get("confirmation_token"), str) else None
    payload_hash = published.get("payload_hash") if isinstance(published.get("payload_hash"), str) else None
    if not confirmation_token or not payload_hash:
        result["error_category"] = "confirmation_material_missing"
        return result
    confirm_payload = {
        "idempotency_key": f"qa-confirm-{uuid.uuid4().hex}",
        "confirmation_token": confirmation_token,
        "expected_payload_hash": payload_hash,
    }
    status, _confirmed, _latency, error = request_json(
        url=f"{base_url}/api/assistant/v2/proposals/{proposal_id}/confirm",
        method="POST", token=token, payload=confirm_payload, timeout_seconds=action_timeout(),
    )
    result["confirm_status"] = status
    confirmation_token = None
    if status != 200 or error:
        result["error_category"] = error or "proposal_confirm_failed"
        return result
    if action_mode == "confirmation":
        result["outcome"] = "confirmed"
        return result
    idempotency_key = f"qa-execute-{uuid.uuid4().hex}"
    execute_payload = {"idempotency_key": idempotency_key, "expected_payload_hash": payload_hash}
    status, _executed, _latency, error = request_json(
        url=f"{base_url}/api/assistant/v2/proposals/{proposal_id}/execute",
        method="POST", token=token, payload=execute_payload, timeout_seconds=action_timeout(),
    )
    result["execute_status"] = status
    execution_status = _executed.get("status") if isinstance(_executed.get("status"), str) else None
    result["execution_status"] = execution_status
    if status != 200 or error or execution_status not in {"succeeded", "already_executed"}:
        result["error_category"] = error or "proposal_execute_failed"
        return result
    if case.get("idempotency_replay") is True:
        replay_status, _replayed, _latency, replay_error = request_json(
            url=f"{base_url}/api/assistant/v2/proposals/{proposal_id}/execute",
            method="POST", token=token, payload=execute_payload, timeout_seconds=action_timeout(),
        )
        result["idempotency_replay_status"] = replay_status
        replay_execution_status = _replayed.get("status") if isinstance(_replayed.get("status"), str) else None
        result["idempotency_replay_execution_status"] = replay_execution_status
        if replay_status != 200 or replay_error or replay_execution_status not in {"succeeded", "already_executed"}:
            result["error_category"] = replay_error or "idempotency_replay_failed"
    if not result.get("error_category"):
        result["outcome"] = "executed"
    return result


def run_cases(
    *,
    base_url: str,
    token: str,
    cases: Iterable[Dict[str, Any]],
    matrix_deadline_seconds: float = 2100.0,
    case_timeout_seconds: float = 60.0,
    fixture_namespace: Optional[str] = None,
    checkpoint=None,
    existing_results: Optional[Iterable[Dict[str, Any]]] = None,
) -> list[Dict[str, Any]]:
    case_list = list(cases)
    case_ids = [str(case["case_id"]) for case in case_list]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("manifest_case_ids_not_unique")
    # ``not_run`` rows are evidence for an interrupted attempt, not completed
    # work.  Drop only those rows when resuming so their manifest cases run
    # exactly once and no stale placeholder survives a completed retry.
    results = [
        dict(item)
        for item in (existing_results or [])
        if item.get("case_status") != "not_run"
    ]
    completed_ids = {
        str(item.get("case_id"))
        for item in results
        if item.get("case_id") and item.get("case_status") != "not_run"
    }
    unknown_ids = completed_ids.difference(case_ids)
    if unknown_ids:
        raise ValueError("checkpoint_case_not_in_manifest")
    conversations: Dict[str, str] = {
        str(item["conversation_key"]): str(item["conversation_id"])
        for item in results
        if item.get("conversation_key") and item.get("conversation_id")
        and item.get("case_status") != "not_run"
    }
    matrix_deadline = time.monotonic() + matrix_deadline_seconds
    for index, case in enumerate(case_list):
        if str(case["case_id"]) in completed_ids:
            continue
        if time.monotonic() >= matrix_deadline:
            # Preserve every remaining manifest case as explicit evidence. A
            # single synthetic deadline row previously hid the final cases.
            results.extend(
                {
                    "case_id": pending_case["case_id"],
                    "case_status": "not_run",
                    "error_category": "matrix_deadline",
                }
                for pending_case in case_list[index:]
                if str(pending_case["case_id"]) not in completed_ids
            )
            if checkpoint:
                checkpoint(results, planned_count=len(case_list))
            break
        if fixture_namespace:
            case = materialize_fixture_namespace(case, namespace=fixture_namespace)
        case_deadline = time.monotonic() + case_timeout_seconds
        def remaining() -> float:
            return case_deadline - time.monotonic()
        conversation_key = _logical_conversation_key(case)
        request_payload = {
            "message": case["message"],
            "workspace_hints": case.get("workspace_hints") or {},
            "client_context": case.get("client_context") or {},
            "idempotency_key": f"qa-{uuid.uuid4().hex}",
            "transport": "chat",
        }
        if conversation_key in conversations:
            request_payload["conversation_id"] = conversations[conversation_key]
        status, created, latency, error_category = request_json(url=f"{base_url}/api/assistant/v2/runs", method="POST", token=token, payload=request_payload, timeout_seconds=max(0.1, min(20.0, remaining())))
        run_id = created.get("run_id") if isinstance(created.get("run_id"), str) else None
        conversation_id = created.get("conversation_id") if isinstance(created.get("conversation_id"), str) else None
        if conversation_key and conversation_id:
            conversations[conversation_key] = conversation_id
        result: Dict[str, Any] = {
            "case_id": case["case_id"], "conversation_key": conversation_key,
            "create_http_status": status, "run_id": run_id, "conversation_id": conversation_id,
            "create_latency_ms": round(latency, 2), "error_category": error_category,
            "case_status": "completed",
            "fixture_action": {"mode": case.get("fixture_action", "read_only")},
        }
        if status != 200 or not run_id:
            results.append(result)
            if checkpoint:
                checkpoint(results, planned_count=len(case_list))
            continue
        # Both public Build matrices and the protected QA runner use the same
        # bounded SSE-first observation engine.  The QA layer only supplies
        # redaction, fixture authorization, and scoring around this result.
        def read_sse(timeout_seconds: float) -> Tuple[Dict[str, Any], Optional[str]]:
            return request_sse_terminal(
                url=f"{base_url}/api/assistant/v2/runs/{run_id}/stream",
                token=token,
                timeout_seconds=timeout_seconds,
            )

        def fetch_projection(timeout_seconds: float) -> Tuple[Dict[str, Any], Optional[str]]:
            snapshot_status, snapshot, _snapshot_latency, snapshot_error = request_json(
                url=f"{base_url}/api/assistant/v2/runs/{run_id}",
                token=token,
                timeout_seconds=timeout_seconds,
            )
            return (snapshot if snapshot_status == 200 else {}), snapshot_error or (
                "server_http_response" if snapshot_status != 200 else None
            )

        observation = observe_terminal(
            remaining_seconds=remaining,
            read_sse_terminal=read_sse,
            fetch_persisted_projection=fetch_projection,
            initial_projection=created,
        )
        terminal = observation.terminal
        sse_envelope = observation.sse_terminal
        sse_error = observation.sse_error
        poll_error = observation.fallback_poll_error
        terminal_snapshot_error = observation.snapshot_error
        projection = safe_projection(terminal)
        sse_projection = safe_projection(sse_envelope) if sse_envelope else {}
        actual = projection["runtime_trace"].get("final_operation_id") or projection["runtime_trace"].get("initial_operation_id")
        result["terminal"] = projection
        result["sse_terminal"] = sse_projection
        if terminal.get("status") in {"failed", "downgraded", "rejected", "blocked"}:
            result["runtime_diagnostic"] = runtime_diagnostic(run_id)
        result["polling_sse_equal"] = bool(sse_projection) and projection == sse_projection
        result["poll_error"] = poll_error
        result["sse_error"] = sse_error
        result["terminal_snapshot_error"] = terminal_snapshot_error
        if terminal.get("status") not in TERMINAL_STATUSES or sse_error == "case_timeout":
            result["error_category"] = "case_timeout" if remaining() <= 0 or sse_error == "case_timeout" else (sse_error or poll_error or "terminal_timeout")
            # A final bounded status read records whether server work remains
            # active before a following case may begin.  It never retries or
            # duplicates the run.
            _, settled, _settle_latency, settle_error = request_json(
                url=f"{base_url}/api/assistant/v2/runs/{run_id}",
                token=token,
                timeout_seconds=5.0,
            )
            result["server_status_after_timeout"] = settled.get("status") if not settle_error else None
            result["server_active_after_timeout"] = result["server_status_after_timeout"] not in TERMINAL_STATUSES
            if result["server_active_after_timeout"]:
                result["timeout_cleanup"] = settle_timed_out_run(
                    base_url=base_url,
                    token=token,
                    run_id=run_id,
                )
        result["operation_matches"] = case.get("expected_operation_id") is None or actual == case["expected_operation_id"]
        # A timed-out lifecycle never progresses into a proposal/confirmation
        # action.  The runner records the terminal cleanup and leaves any
        # explicit safe fixture action untouched for a later resumed matrix.
        result["fixture_action"] = (
            _run_fixture_action(
                base_url=base_url,
                token=token,
                case=case,
                terminal=terminal,
                remaining_seconds=remaining,
            )
            if terminal.get("status") in TERMINAL_STATUSES and not result.get("error_category")
            else {"mode": case.get("fixture_action", "read_only"), "outcome": "not_run", "error_category": None}
        )
        result["failure_classification"] = classify_case_failure(result)
        results.append(result)
        if checkpoint:
            checkpoint(results, planned_count=len(case_list))
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Protected FINN production QA runner")
    parser.add_argument("--release-sha", required=True)
    parser.add_argument("--profile", required=True, choices=sorted(ALLOWED_PROFILES))
    parser.add_argument("--manifest-id", default="none")
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--base-url", default="https://tradamind.com")
    parser.add_argument("--checkout", required=True)
    parser.add_argument("--release-marker", required=True)
    parser.add_argument("--manifest-root", default="/home/ubuntu/ops/finn-qa-manifests")
    parser.add_argument("--manifest-bundle-path")
    parser.add_argument("--manifest-private-key-path", default="/home/ubuntu/.secrets/finn-qa-manifest.key")
    parser.add_argument("--manifest-crypto-script")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--workflow-run-id", default="local")
    parser.add_argument("--fixture-namespace", default=os.environ.get("FINN_QA_FIXTURE_NAMESPACE"))
    parser.add_argument("--runner-revision")
    parser.add_argument("--matrix-deadline-seconds", type=float, default=2100.0)
    parser.add_argument("--case-timeout-seconds", type=float, default=60.0)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume this exact matrix from its atomic checkpoint without rerunning cases.",
    )
    parser.add_argument("--dry-preflight", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.release_sha):
        raise SystemExit("release_sha must be a full lowercase SHA")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}", args.run_label):
        raise SystemExit("run_label is invalid")
    runner_revision = getattr(args, "runner_revision", None)
    if runner_revision is not None and not re.fullmatch(r"[0-9a-f]{40}", runner_revision):
        raise SystemExit("runner_revision must be a full lowercase SHA")
    report_path = Path(args.report_path)
    fixture_namespace = getattr(args, "fixture_namespace", None)
    report: Dict[str, Any] = {"schema_version": 1, "workflow": "finn-production-qa", "workflow_run_id": args.workflow_run_id, "runner_revision": runner_revision, "target_sha": args.release_sha, "profile": args.profile, "run_label": args.run_label, "manifest_id": args.manifest_id, "manifest_sha256": None, "base_manifest_hash": None, "manifest_public_key": None, "fixture_namespace_present": bool(fixture_namespace), "release_identity": {}, "auth_preflight": {}, "cases": [], "planned_count": 0, "attempted_count": 0, "completed_count": 0, "failed_count": 0, "not_run_count": 0, "incomplete": False, "failure_summary": {"product": 0, "runner": 0, "infrastructure": 0}, "safety": {"read_only_profile": True, "confirmation_calls": 0, "execution_calls": 0, "live_trading_calls": 0, "live_bot_activation_calls": 0}, "outcome": "failed", "qa_status": "NOT_STARTED", "error_category": None}
    token: Optional[str] = None
    known_cases: list[Dict[str, Any]] = []
    try:
        checkout = Path(args.checkout).resolve()
        if getattr(args, "dry_preflight", False):
            if args.manifest_id == "none":
                raise ValueError("manifest_required")
            manifest_root = Path(args.manifest_root)
            manifest = manifest_path(manifest_root=manifest_root, manifest_id=args.manifest_id)
            report["manifest_sha256"] = sha256_file(manifest)
            report["base_manifest_hash"] = report["manifest_sha256"]
            report["planned_count"] = len(manifest_cases(manifest))
            cases = list(load_manifest(
                manifest_root=manifest_root,
                manifest_id=args.manifest_id,
                fixture_namespace=fixture_namespace,
            ))
            report.update(fixture_preflight(cases, fixture_namespace=fixture_namespace))
            report["planned_count"] = len(cases)
            report["outcome"] = "passed"
            report["qa_status"] = "PRECONDITION_PASSED"
            return 0
        report["release_identity"] = release_identity(release_sha=args.release_sha, checkout=checkout, release_marker=Path(args.release_marker), base_url=args.base_url.rstrip("/"))
        if not report["release_identity"]["matches"]:
            report["error_category"] = "release_mismatch"
        elif args.profile == "manifest_key":
            crypto_script = Path(args.manifest_crypto_script or checkout / "ops" / "qa" / "finn_qa_manifest_bundle.py")
            report["manifest_public_key"] = manifest_public_key(
                crypto_script=crypto_script,
                private_key_path=Path(args.manifest_private_key_path),
            )
            report["outcome"] = "passed"
        else:
            token = issue_fixture_token(issuer=checkout / "backend" / "trading-tool-backend" / "backend" / "scripts" / "qa_issue_finn_token.py")
            report["auth_preflight"] = authenticated_preflight(base_url=args.base_url.rstrip("/"), token=token)
            if not report["auth_preflight"]["fixture_authenticated"]:
                report["error_category"] = report["auth_preflight"].get("error_category") or "auth"
            elif args.profile == "auth_preflight":
                report["outcome"] = "passed"
            else:
                if args.manifest_id == "none":
                    raise ValueError("manifest_required")
                manifest_root = Path(args.manifest_root)
                if args.manifest_bundle_path:
                    crypto_script = Path(args.manifest_crypto_script or checkout / "ops" / "qa" / "finn_qa_manifest_bundle.py")
                    stage_manifest_bundle(
                        crypto_script=crypto_script,
                        private_key_path=Path(args.manifest_private_key_path),
                        bundle_path=Path(args.manifest_bundle_path),
                        manifest_root=manifest_root,
                        manifest_id=args.manifest_id,
                    )
                manifest = manifest_path(manifest_root=manifest_root, manifest_id=args.manifest_id)
                report["manifest_sha256"] = sha256_file(manifest)
                report["base_manifest_hash"] = report["manifest_sha256"]
                report["planned_count"] = len(manifest_cases(manifest))
                cases = list(load_manifest(
                    manifest_root=manifest_root,
                    manifest_id=args.manifest_id,
                    fixture_namespace=fixture_namespace,
                ))
                known_cases = cases
                report.update(fixture_preflight(cases, fixture_namespace=fixture_namespace))
                if getattr(args, "resume", False) and report_path.exists():
                    prior = json.loads(report_path.read_text(encoding="utf-8"))
                    if (
                        prior.get("target_sha") != args.release_sha
                        or prior.get("manifest_sha256") != report["manifest_sha256"]
                        or prior.get("workflow_run_id") != args.workflow_run_id
                    ):
                        raise ValueError("checkpoint_identity_mismatch")
                    previous_rows = prior.get("cases")
                    if not isinstance(previous_rows, list):
                        raise ValueError("checkpoint_cases_invalid")
                    report["cases"] = [dict(item) for item in previous_rows]
                def checkpoint(results, *, planned_count: int) -> None:
                    # Copy snapshots: a later runner failure must not mutate a
                    # previously valid atomic checkpoint in memory.
                    report["cases"] = [dict(item) for item in results]
                    progress = case_progress(cases=report["cases"], planned_count=planned_count)
                    report.update(progress)
                    report["failure_summary"] = failure_summary(report["cases"])
                    # Checkpoints are independently publishable evidence.  A
                    # runner crash must never leave completed product calls
                    # labelled NOT_STARTED simply because final aggregation
                    # did not get CPU time.
                    report["qa_status"] = (
                        "INCOMPLETE" if report["incomplete"]
                        else "IN_PROGRESS"
                    )
                    report["outcome"] = "incomplete" if report["incomplete"] else "running"
                    write_report_atomic(report_path, report)

                report["cases"] = run_cases(base_url=args.base_url.rstrip("/"), token=token, cases=cases, matrix_deadline_seconds=getattr(args, "matrix_deadline_seconds", 2100.0), case_timeout_seconds=getattr(args, "case_timeout_seconds", 60.0), fixture_namespace=fixture_namespace, checkpoint=checkpoint, existing_results=report["cases"])
                report.update(case_progress(cases=report["cases"], planned_count=len(cases)))
                report["failure_summary"] = failure_summary(report["cases"])
                report["safety"]["read_only_profile"] = all(case.get("fixture_action", "read_only") == "read_only" for case in cases)
                report["safety"]["confirmation_calls"] = sum(1 for item in report["cases"] if item.get("fixture_action", {}).get("confirm_status") is not None)
                report["safety"]["execution_calls"] = sum(1 for item in report["cases"] if item.get("fixture_action", {}).get("execute_status") is not None)
                report["outcome"] = "passed" if not report["incomplete"] and all(item.get("create_http_status") == 200 and item.get("terminal", {}).get("status") in TERMINAL_STATUSES and item.get("polling_sse_equal") and item.get("operation_matches") and not item["fixture_action"].get("error_category") for item in report["cases"]) else "failed"
    except (RuntimeError, ValueError) as error:
        report["error_category"] = str(error)
        if report["error_category"] in {"fixture_namespace_required", "fixture_namespace_invalid"}:
            report["outcome"] = "blocked"
            report["qa_status"] = "QA BLOCKED / NOT STARTED"
    except Exception:
        report["error_category"] = "runner_internal"
    finally:
        token = None
        # A late runner error must retain the most complete checkpoint.  Keep
        # progress derived from the saved case rows rather than resetting it to
        # the initial empty report shape.
        if known_cases and not getattr(args, "dry_preflight", False):
            report["cases"] = add_missing_not_run_cases(
                results=report["cases"],
                cases=known_cases,
                error_category="runner_interrupted",
            )
        if report["planned_count"] and not getattr(args, "dry_preflight", False):
            report.update(case_progress(cases=report["cases"], planned_count=report["planned_count"]))
            report["failure_summary"] = failure_summary(report["cases"])
            if report["attempted_count"]:
                report["qa_status"] = (
                    "INCOMPLETE" if report["incomplete"]
                    else ("COMPLETED" if report["outcome"] == "passed" else "COMPLETED_WITH_FAILURES")
                )
        write_report_atomic(report_path, report)
    # Content failures are QA evidence, not a runner failure. The workflow must
    # upload the complete report instead of stopping before the matrix result.
    if report["outcome"] == "passed" or report["cases"]:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
