#!/usr/bin/env python3
"""Run a QA-style FINN replay against a target environment.

The goal of this script is to make the FINN 2.0 release gate reproducible.
It replays a saved promptset against `/api/assistant/chat`, records latency and
behavioral invariants, and emits JSON/Markdown summaries that can be attached
to QA runs.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import math
import os
import socket
import ssl
import statistics
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


GENERIC_FAILURE_SNIPPETS = (
    "kon geen analyse ophalen",
    "probeer opnieuw",
    "interne authenticatiefout",
    "insufficient_quota",
)

DEFAULT_CHAT_LATENCY_BUDGET_MS = 8000.0
DEFAULT_MISSION_CONTROL_LATENCY_BUDGET_MS = 20000.0


def load_promptset(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Promptset root must be an object.")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Promptset must contain a non-empty 'cases' list.")

    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"Case #{index} must be an object.")
        if not case.get("id") or not case.get("query"):
            raise ValueError(f"Case #{index} requires 'id' and 'query'.")
    return payload


def _is_generic_failure(response_text: Optional[str]) -> bool:
    text = str(response_text or "").strip().lower()
    if not text:
        return True
    return any(snippet in text for snippet in GENERIC_FAILURE_SNIPPETS)


def _percentile(values: List[float], percentile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return round(values[0], 2)
    values = sorted(values)
    rank = (len(values) - 1) * percentile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return round(values[lower], 2)
    fraction = rank - lower
    return round(values[lower] + (values[upper] - values[lower]) * fraction, 2)


def _safe_json(response: bytes) -> Dict[str, Any]:
    try:
        return json.loads(response.decode("utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError(f"Invalid JSON response: {exc}") from exc


def build_http_client(
    *,
    base_url: str,
    bearer_token: Optional[str],
    login_email: Optional[str],
    login_password: Optional[str],
    timeout_seconds: float,
    insecure_ssl: bool = False,
) -> Tuple[urllib.request.OpenerDirector, Dict[str, str]]:
    cookie_jar = http.cookiejar.CookieJar()
    if insecure_ssl:
        ssl_context = ssl._create_unverified_context()
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cookie_jar),
            urllib.request.HTTPSHandler(context=ssl_context),
        )
    else:
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    headers: Dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
        return opener, headers

    if login_email and login_password:
        login_body = json.dumps({"email": login_email, "password": login_password}).encode("utf-8")
        login_request = urllib.request.Request(
            f"{base_url.rstrip('/')}/api/auth/login",
            data=login_body,
            method="POST",
            headers=headers,
        )
        with opener.open(login_request, timeout=timeout_seconds) as response:
            if int(response.status) != 200:  # pragma: no cover - defensive
                raise RuntimeError(f"Login failed with status {response.status}")
        return opener, headers

    raise ValueError("Provide either a bearer token or login email/password.")


def perform_chat_request(
    *,
    opener: urllib.request.OpenerDirector,
    default_headers: Dict[str, str],
    base_url: str,
    query: str,
    context: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    timeout_seconds: float = 45.0,
) -> Tuple[Dict[str, Any], float, int]:
    payload: Dict[str, Any] = {"query": query}
    if context:
        payload["context"] = context
    if session_id:
        payload["session_id"] = session_id

    body = json.dumps(payload).encode("utf-8")
    headers = {
        **default_headers,
        "X-Trace-Id": f"finn-qa-{uuid.uuid4()}",
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/assistant/chat",
        data=body,
        method="POST",
        headers=headers,
    )

    started = time.perf_counter()
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            raw = response.read()
            latency_ms = (time.perf_counter() - started) * 1000
            return _safe_json(raw), latency_ms, int(response.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        latency_ms = (time.perf_counter() - started) * 1000
        payload = _safe_json(raw) if raw else {"detail": str(exc)}
        return payload, latency_ms, int(exc.code)
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        latency_ms = (time.perf_counter() - started) * 1000
        detail = getattr(exc, "reason", None) or str(exc)
        return {"detail": str(detail), "error": "operational_qa_path"}, latency_ms, 599


def evaluate_case(case: Dict[str, Any], response: Dict[str, Any], latency_ms: float, http_status: int) -> Dict[str, Any]:
    state = response.get("state") if isinstance(response.get("state"), dict) else {}
    analysis = response.get("analysis") if isinstance(response.get("analysis"), dict) else {}
    if not analysis and isinstance(state.get("analysis"), dict):
        analysis = state.get("analysis") or {}
    flow = response.get("flow")
    intent = response.get("intent")
    mode = analysis.get("mode")
    context_confidence = analysis.get("context_confidence") if isinstance(analysis.get("context_confidence"), dict) else None
    context_explain = analysis.get("context_explain") if isinstance(analysis.get("context_explain"), dict) else None
    context_entity_resolution = analysis.get("context_entity_resolution") if isinstance(analysis.get("context_entity_resolution"), dict) else None
    behavioral = analysis.get("behavioral_intelligence") if isinstance(analysis.get("behavioral_intelligence"), dict) else None
    behavioral_variant = (
        behavioral.get("variant")
        or analysis.get("variant")
    ) if (behavioral or analysis.get("variant")) else None
    route_source = analysis.get("route_source")
    route_family = analysis.get("route_family")
    response_text = response.get("response")
    expected_intents = set(case.get("expected_intents") or [])
    forbidden_flows = set(case.get("forbidden_flows") or [])
    expected_mode = case.get("expected_mode")
    require_context_confidence = bool(case.get("require_context_confidence"))
    require_analysis_variant = case.get("require_analysis_variant")
    require_context_entity_type = case.get("require_context_entity_type")
    require_context_resolution_target = case.get("require_context_resolution_target")
    response_must_not_contain = [str(item).lower() for item in (case.get("response_must_not_contain") or [])]
    forbid_duplicate_bullets = bool(case.get("forbid_duplicate_bullets"))

    failures: List[str] = []

    if http_status != 200:
        failures.append(f"http_status:{http_status}")
    if _is_generic_failure(response_text):
        failures.append("generic_failure")
    if expected_intents and intent not in expected_intents:
        failures.append(f"unexpected_intent:{intent}")
    if flow in forbidden_flows:
        failures.append(f"forbidden_flow:{flow}")
    if expected_mode and mode != expected_mode:
        failures.append(f"unexpected_mode:{mode}")
    if require_context_confidence and not context_confidence:
        failures.append("missing_context_confidence")
    if require_analysis_variant and behavioral_variant != require_analysis_variant:
        failures.append(f"unexpected_variant:{behavioral_variant}")
    if require_context_entity_type and (context_explain or {}).get("entity_type") != require_context_entity_type:
        failures.append(f"unexpected_context_entity_type:{(context_explain or {}).get('entity_type')}")
    if require_context_resolution_target and (context_entity_resolution or {}).get("target") != require_context_resolution_target:
        failures.append(f"unexpected_context_resolution_target:{(context_entity_resolution or {}).get('target')}")
    response_text_normalized = str(response_text or "").lower()
    for snippet in response_must_not_contain:
        if snippet and snippet in response_text_normalized:
            failures.append(f"forbidden_response_snippet:{snippet}")
    if forbid_duplicate_bullets:
        bullets = [
            line.strip()[2:].strip().lower()
            for line in str(response_text or "").splitlines()
            if line.strip().startswith("- ")
        ]
        bullets = [bullet for bullet in bullets if bullet]
        if len(set(bullets)) != len(bullets):
            failures.append("duplicate_bullets")

    return {
        "id": case["id"],
        "query": case["query"],
        "conversation": case.get("conversation"),
        "http_status": http_status,
        "intent": intent,
        "flow": flow,
        "mode": mode,
        "route_source": route_source,
        "route_family": route_family,
        "analysis_variant": behavioral_variant,
        "latency_ms": round(latency_ms, 2),
        "context_confidence": context_confidence,
        "context_entity_type": (context_explain or {}).get("entity_type"),
        "context_entity_resolution": context_entity_resolution,
        "response_preview": str(response_text or "")[:220],
        "passed": not failures,
        "failures": failures,
        "expected_intents": list(expected_intents),
        "forbidden_flows": list(forbidden_flows),
        "response": response,
    }


def _latency_bucket(latency_ms: float) -> str:
    if latency_ms <= 1000:
        return "le_1s"
    if latency_ms <= 3000:
        return "le_3s"
    if latency_ms <= 8000:
        return "le_8s"
    return "gt_8s"


def _failure_bucket(result: Dict[str, Any]) -> Optional[str]:
    if result.get("passed"):
        return None
    http_status = int(result.get("http_status") or 0)
    failures = result.get("failures") or []
    if http_status in {401, 408, 409, 429} or http_status >= 500:
        return "operational_qa_path"
    if any(flag.startswith("http_status:") for flag in failures):
        return "operational_qa_path"
    return "product_quality"


def summarize_results(
    *,
    suite_name: str,
    results: List[Dict[str, Any]],
    chat_latency_budget_ms: float = DEFAULT_CHAT_LATENCY_BUDGET_MS,
    mission_control_latency_budget_ms: float = DEFAULT_MISSION_CONTROL_LATENCY_BUDGET_MS,
) -> Dict[str, Any]:
    latencies = [float(result.get("latency_ms") or 0.0) for result in results]
    mission_results = [result for result in results if result.get("intent") == "mission_control_explain"]
    mission_latencies = [float(result.get("latency_ms") or 0.0) for result in mission_results]
    slowest_result = max(results, key=lambda result: float(result.get("latency_ms") or 0.0)) if results else None
    failures = [result for result in results if not result.get("passed")]
    failure_buckets = {"product_quality": 0, "operational_qa_path": 0}
    latency_buckets = {"le_1s": 0, "le_3s": 0, "le_8s": 0, "gt_8s": 0}
    for result in results:
        latency_buckets[_latency_bucket(float(result.get("latency_ms") or 0.0))] += 1
    for result in failures:
        bucket = _failure_bucket(result)
        if bucket:
            failure_buckets[bucket] += 1
    generic_failures = [result for result in results if "generic_failure" in (result.get("failures") or [])]
    transactional_misroutes = [
        result
        for result in results
        if any(failure.startswith("forbidden_flow:") for failure in (result.get("failures") or []))
    ]
    mixed_conversation_failures = [
        result for result in results if result.get("conversation") == "mixed-20-turn" and not result.get("passed")
    ]

    release_gate = {
        "no_generic_failures": not generic_failures,
        "no_transactional_misroutes": not transactional_misroutes,
        "stable_mixed_session": not mixed_conversation_failures,
        "chat_latency_budget_ok": _percentile(latencies, 0.95) <= chat_latency_budget_ms if latencies else True,
        "mission_control_latency_budget_ok": (
            max(mission_latencies) <= mission_control_latency_budget_ms if mission_latencies else True
        ),
    }
    release_gate["overall_pass"] = all(release_gate.values()) and not failures

    return {
        "suite_name": suite_name,
        "total_cases": len(results),
        "passed_cases": sum(1 for result in results if result.get("passed")),
        "failed_cases": len(failures),
        "generic_failures": len(generic_failures),
        "transactional_misroutes": len(transactional_misroutes),
        "avg_latency_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
        "p95_latency_ms": _percentile(latencies, 0.95),
        "max_latency_ms": round(max(latencies), 2) if latencies else 0.0,
        "slowest_prompt_id": slowest_result.get("id") if slowest_result else None,
        "mission_control_max_latency_ms": round(max(mission_latencies), 2) if mission_latencies else 0.0,
        "latency_buckets": latency_buckets,
        "failure_buckets": failure_buckets,
        "release_gate": release_gate,
        "failures": failures,
    }


def render_markdown_report(summary: Dict[str, Any], results: List[Dict[str, Any]]) -> str:
    lines = [
        f"# FINN QA Replay Report — {summary['suite_name']}",
        "",
        f"- Total cases: **{summary['total_cases']}**",
        f"- Passed: **{summary['passed_cases']}**",
        f"- Failed: **{summary['failed_cases']}**",
        f"- Generic failures: **{summary['generic_failures']}**",
        f"- Transactional misroutes: **{summary['transactional_misroutes']}**",
        f"- Avg latency: **{summary['avg_latency_ms']} ms**",
        f"- P95 latency: **{summary['p95_latency_ms']} ms**",
        f"- Max latency: **{summary['max_latency_ms']} ms**",
        f"- Slowest prompt: **{summary.get('slowest_prompt_id') or 'n/a'}**",
        "",
        "## Failure Buckets",
        "",
        f"- `product_quality`: **{summary.get('failure_buckets', {}).get('product_quality', 0)}**",
        f"- `operational_qa_path`: **{summary.get('failure_buckets', {}).get('operational_qa_path', 0)}**",
        "",
        "## Release Gate",
        "",
    ]
    for key, value in summary["release_gate"].items():
        lines.append(f"- `{key}`: **{value}**")

    lines.extend(["", "## Case Results", ""])
    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        lines.append(
            f"- `{result['id']}` [{status}] intent=`{result.get('intent')}` flow=`{result.get('flow')}` "
            f"mode=`{result.get('mode')}` variant=`{result.get('analysis_variant')}` "
            f"entity=`{result.get('context_entity_type')}` latency=`{result.get('latency_ms')}ms` "
            f"failures=`{', '.join(result.get('failures') or []) or 'none'}`"
        )
    return "\n".join(lines) + "\n"


def run_suite(
    *,
    opener: urllib.request.OpenerDirector,
    default_headers: Dict[str, str],
    base_url: str,
    promptset: Dict[str, Any],
    timeout_seconds: float,
    delay_seconds: float,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    session_map: Dict[str, str] = {}
    results: List[Dict[str, Any]] = []

    for case in promptset["cases"]:
        conversation = case.get("conversation")
        session_id = session_map.get(conversation) if conversation else None
        response, latency_ms, http_status = perform_chat_request(
            opener=opener,
            default_headers=default_headers,
            base_url=base_url,
            query=case["query"],
            context=case.get("context"),
            session_id=session_id,
            timeout_seconds=timeout_seconds,
        )
        if conversation and response.get("session_id"):
            session_map[conversation] = response["session_id"]
        results.append(evaluate_case(case, response, latency_ms, http_status))
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    summary = summarize_results(
        suite_name=promptset.get("name") or "finn-qa-suite",
        results=results,
        chat_latency_budget_ms=float(promptset.get("chat_latency_budget_ms") or DEFAULT_CHAT_LATENCY_BUDGET_MS),
        mission_control_latency_budget_ms=float(
            promptset.get("mission_control_latency_budget_ms") or DEFAULT_MISSION_CONTROL_LATENCY_BUDGET_MS
        ),
    )
    return results, summary


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay a FINN QA promptset against /api/assistant/chat.")
    parser.add_argument("--base-url", required=True, help="Base URL, e.g. https://tradamind.com")
    parser.add_argument("--promptset", required=True, help="Path to a JSON promptset file")
    parser.add_argument("--output-json", help="Optional path for a JSON report")
    parser.add_argument("--output-md", help="Optional path for a Markdown report")
    parser.add_argument("--token-env", default="FINN_QA_BEARER_TOKEN", help="Env var containing the bearer token")
    parser.add_argument("--login-email", help="Optional web login email for cookie-based replay")
    parser.add_argument("--password-env", default="FINN_QA_PASSWORD", help="Env var containing the login password")
    parser.add_argument("--timeout-seconds", type=float, default=45.0, help="Per-request timeout")
    parser.add_argument("--delay-seconds", type=float, default=0.0, help="Sleep between prompts to avoid noisy rate-limit false negatives")
    parser.add_argument("--no-delay", action="store_true", help="Override any configured pacing and run without delay between prompts")
    parser.add_argument("--insecure", action="store_true", help="Disable TLS certificate verification for environments with broken local CA trust")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when the release gate fails")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    token = os.getenv(args.token_env)
    login_password = os.getenv(args.password_env) if args.login_email else None
    try:
        opener, default_headers = build_http_client(
            base_url=args.base_url,
            bearer_token=token,
            login_email=args.login_email,
            login_password=login_password,
            timeout_seconds=args.timeout_seconds,
            insecure_ssl=args.insecure,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    promptset = load_promptset(Path(args.promptset))
    results, summary = run_suite(
        opener=opener,
        default_headers=default_headers,
        base_url=args.base_url,
        promptset=promptset,
        timeout_seconds=args.timeout_seconds,
        delay_seconds=0.0 if args.no_delay else args.delay_seconds,
    )

    report_payload = {
        "promptset": promptset.get("name"),
        "summary": summary,
        "results": results,
        "certification": {
            "pass_decision": bool(summary["release_gate"]["overall_pass"]),
            "failure_buckets": summary.get("failure_buckets") or {},
            "slowest_prompt_id": summary.get("slowest_prompt_id"),
            "latency_buckets": summary.get("latency_buckets") or {},
        },
    }

    if args.output_json:
        Path(args.output_json).write_text(json.dumps(report_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.output_md:
        Path(args.output_md).write_text(render_markdown_report(summary, results), encoding="utf-8")

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if args.strict and not summary["release_gate"]["overall_pass"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
