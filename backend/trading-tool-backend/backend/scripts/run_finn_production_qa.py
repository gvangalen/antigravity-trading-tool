#!/usr/bin/env python3
"""Run a sanitized FINN production-QA profile from the protected host.

This program is invoked by the GitHub Actions QA runner on the production host.
It never prints the fixture token and writes only a redacted report.
"""

from __future__ import annotations

import argparse
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
from typing import Any, Dict, Iterable, Optional, Tuple


ALLOWED_PROFILES = {
    "auth_preflight",
    "targeted_regression",
    "runtime_acceptance",
    "full_release_acceptance",
    "safety",
    "latency",
}
SENSITIVE_KEYS = {"access_token", "authorization", "authorization_header", "cookie", "email", "password", "private_key", "secret", "token", "user_id"}
TERMINAL_STATUSES = {"completed", "failed", "canceled", "unavailable", "downgraded", "rejected", "blocked"}


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
    headers = {"Accept": "application/json", "User-Agent": "FINN-Production-QA-Runner/1.0"}
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
    headers = {"Accept": "text/event-stream", "Authorization": f"Bearer {token}", "User-Agent": "FINN-Production-QA-Runner/1.0"}
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


def release_identity(*, release_sha: str, checkout: Path, release_marker: Path, base_url: str) -> Dict[str, Any]:
    head = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"], check=False, capture_output=True, text=True).stdout.strip() or None
    marker = _read(release_marker)
    health_status, health, health_latency, health_error = request_json(url=f"{base_url}/api/health")
    frontend_status, frontend, frontend_latency, frontend_error = request_json(url=f"{base_url}/build-info.json")
    backend_sha = health.get("commit_sha") or health.get("build_commit") or health.get("sha")
    frontend_sha = frontend.get("commit_sha") or frontend.get("build_commit") or frontend.get("sha")
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
    status, _payload, latency, error_category = request_json(url=f"{base_url}/api/auth/me", token=token)
    return {"http_status": status, "latency_ms": round(latency, 2), "error_category": error_category, "fixture_authenticated": status == 200}


def safe_projection(envelope: Dict[str, Any]) -> Dict[str, Any]:
    trace = envelope.get("runtime_trace") if isinstance(envelope.get("runtime_trace"), dict) else {}
    response = envelope.get("response") if isinstance(envelope.get("response"), dict) else {}
    allowed = {"initial_operation_id", "final_operation_id", "operation_change_reason", "canonical_target", "target_source", "conversation_reference", "dispatch_id", "attempt_count", "projection_version", "projection_hash", "terminal_response_type"}
    return {"run_id": envelope.get("run_id"), "status": envelope.get("status"), "mode": envelope.get("mode"), "response_mode": response.get("mode"), "runtime_trace": {key: trace.get(key) for key in allowed if key in trace}}


def manifest_path(*, manifest_root: Path, manifest_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,80}", manifest_id):
        raise ValueError("manifest_id_invalid")
    root = manifest_root.resolve()
    path = (root / f"{manifest_id}.json").resolve()
    if root not in path.parents or not path.is_file():
        raise ValueError("manifest_not_found")
    return path


def load_read_only_manifest(*, manifest_root: Path, manifest_id: str) -> Iterable[Dict[str, Any]]:
    payload = json.loads(manifest_path(manifest_root=manifest_root, manifest_id=manifest_id).read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ValueError("manifest_cases_invalid")
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("case_id"), str) or not isinstance(case.get("message"), str):
            raise ValueError("manifest_case_invalid")
        if case.get("allow_fixture_write") is True or case.get("confirmation") is True or case.get("execution") is True:
            raise ValueError("manifest_not_read_only")
    return cases


def run_read_only_cases(*, base_url: str, token: str, cases: Iterable[Dict[str, Any]]) -> list[Dict[str, Any]]:
    results = []
    for case in cases:
        request_payload = {"message": case["message"], "conversation_id": case.get("conversation_id"), "workspace_hints": case.get("workspace_hints") or {}, "client_context": case.get("client_context") or {}, "idempotency_key": f"qa-{uuid.uuid4().hex}", "transport": "chat"}
        status, created, latency, error_category = request_json(url=f"{base_url}/api/assistant/v2/runs", method="POST", token=token, payload=request_payload, timeout_seconds=20.0)
        run_id = created.get("run_id") if isinstance(created.get("run_id"), str) else None
        result: Dict[str, Any] = {"case_id": case["case_id"], "create_http_status": status, "run_id": run_id, "create_latency_ms": round(latency, 2), "error_category": error_category}
        if status != 200 or not run_id:
            results.append(result)
            continue
        terminal = created
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            time.sleep(0.25)
            _, terminal, _, poll_error = request_json(url=f"{base_url}/api/assistant/v2/runs/{run_id}", token=token)
            if poll_error:
                result["error_category"] = poll_error
                break
            if terminal.get("status") in TERMINAL_STATUSES:
                break
        projection = safe_projection(terminal)
        sse_envelope, sse_error = request_sse_terminal(
            url=f"{base_url}/api/assistant/v2/runs/{run_id}/stream", token=token
        )
        sse_projection = safe_projection(sse_envelope) if sse_envelope else {}
        actual = projection["runtime_trace"].get("final_operation_id") or projection["runtime_trace"].get("initial_operation_id")
        result["terminal"] = projection
        result["sse_terminal"] = sse_projection
        result["polling_sse_equal"] = bool(sse_projection) and projection == sse_projection
        if sse_error:
            result["error_category"] = sse_error
        result["operation_matches"] = case.get("expected_operation_id") is None or actual == case["expected_operation_id"]
        results.append(result)
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
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--workflow-run-id", default="local")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.release_sha):
        raise SystemExit("release_sha must be a full lowercase SHA")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}", args.run_label):
        raise SystemExit("run_label is invalid")
    report_path = Path(args.report_path)
    report: Dict[str, Any] = {"schema_version": 1, "workflow": "finn-production-qa", "workflow_run_id": args.workflow_run_id, "profile": args.profile, "run_label": args.run_label, "manifest_id": args.manifest_id, "manifest_sha256": None, "release_identity": {}, "auth_preflight": {}, "cases": [], "safety": {"read_only_profile": True, "confirmation_calls": 0, "execution_calls": 0, "live_trading_calls": 0}, "outcome": "failed", "error_category": None}
    token: Optional[str] = None
    try:
        checkout = Path(args.checkout).resolve()
        report["release_identity"] = release_identity(release_sha=args.release_sha, checkout=checkout, release_marker=Path(args.release_marker), base_url=args.base_url.rstrip("/"))
        if not report["release_identity"]["matches"]:
            report["error_category"] = "release_mismatch"
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
                report["manifest_sha256"] = sha256_file(manifest_path(manifest_root=manifest_root, manifest_id=args.manifest_id))
                report["cases"] = run_read_only_cases(base_url=args.base_url.rstrip("/"), token=token, cases=load_read_only_manifest(manifest_root=manifest_root, manifest_id=args.manifest_id))
                report["outcome"] = "passed" if all(item.get("create_http_status") == 200 and item.get("terminal", {}).get("status") in TERMINAL_STATUSES and item.get("polling_sse_equal") and item.get("operation_matches") for item in report["cases"]) else "failed"
    except (RuntimeError, ValueError) as error:
        report["error_category"] = str(error)
    except Exception:
        report["error_category"] = "runner_internal"
    finally:
        token = None
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(redact(report), sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return 0 if report["outcome"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
