#!/usr/bin/env python3
"""Run safe Platform Phase 2.1 capacity profiles against a target environment.

This harness is intentionally conservative:
- no execute endpoints
- no report generation endpoints
- no live/manual order placement
- optional manual-order preview only when an explicit fixture is supplied

It is meant to validate queue/latency behavior under controlled read-heavy,
AI-heavy, and governance-preview-heavy traffic.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import ssl
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import httpx


SAFE_AI_QUERIES = [
    "Vat Mission Control samen in drie bullets.",
    "Wat moet ik vandaag vooral niet doen als trader?",
    "Leg mijn huidige dashboardcontext kort uit.",
]

SAFE_GOVERNANCE_QUERIES = [
    "Plaats nu direct een live BTC order.",
    "Mag ik extra BTC risico toevoegen?",
    "Welke confirmation is nodig voordat ik dit uitvoer?",
]

PROFILE_CHOICES = ["read-heavy", "ai-heavy", "bot-execution-heavy", "mixed-load"]
DEFAULT_MIXED_READ_THINK_TIME_SECONDS = 0.15
DEFAULT_MIXED_AI_THINK_TIME_SECONDS = 2.5
DEFAULT_MIXED_BOT_THINK_TIME_SECONDS = 3.0
DEFAULT_MIXED_USER_START_STAGGER_SECONDS = 0.35
DEFAULT_MIXED_WAVE_WIDTH = 20


def _percentile(values: List[float], percentile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return round(values[0], 2)
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile
    lower = int(rank)
    upper = min(len(ordered) - 1, lower + 1)
    if lower == upper:
        return round(ordered[lower], 2)
    fraction = rank - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction, 2)


def _safe_json(response_text: str) -> Optional[Dict[str, Any]]:
    try:
        payload = json.loads(response_text)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def load_manual_order_preview_fixture(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Manual order preview fixture must be a JSON object.")
    required = {"bot_id", "symbol", "side", "quantity", "price"}
    missing = sorted(field for field in required if field not in payload)
    if missing:
        raise ValueError(f"Manual order preview fixture missing fields: {', '.join(missing)}")
    return payload


def build_profile_requests(
    profile: str,
    *,
    iterations: int,
    manual_order_preview_fixture: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    requests: List[Dict[str, Any]] = []

    if profile == "read-heavy":
        template = [
            {"name": "mission-control", "method": "GET", "path": "/api/assistant/mission-control", "cache_bust": True},
            {"name": "daily-report-latest", "method": "GET", "path": "/api/report/daily/latest?symbol=BTC"},
            {"name": "daily-report-history", "method": "GET", "path": "/api/report/daily/history"},
            {"name": "top-setups", "method": "GET", "path": "/api/setups/top?limit=3"},
            {"name": "latest-price", "method": "GET", "path": "/api/market_data/BTC/latest"},
        ]
        for iteration in range(iterations):
            for item in template:
                requests.append({**item, "profile": profile, "iteration": iteration + 1})
        return requests

    if profile == "ai-heavy":
        for iteration in range(iterations):
            for index, query in enumerate(SAFE_AI_QUERIES, start=1):
                requests.append(
                    {
                        "name": f"assistant-chat-{index}",
                        "method": "POST",
                        "path": "/api/assistant/chat",
                        "json": {"query": query, "context": {}, "history": []},
                        "profile": profile,
                        "iteration": iteration + 1,
                    }
                )
            requests.append(
                {
                    "name": "daily-report-preview",
                    "method": "POST",
                    "path": "/api/report/daily/preview",
                    "json": {},
                    "profile": profile,
                    "iteration": iteration + 1,
                }
            )
        return requests

    if profile == "bot-execution-heavy":
        for iteration in range(iterations):
            requests.append(
                {
                    "name": "bot-portfolios",
                    "method": "GET",
                    "path": "/api/bot/portfolios",
                    "profile": profile,
                    "iteration": iteration + 1,
                }
            )
            for index, query in enumerate(SAFE_GOVERNANCE_QUERIES, start=1):
                requests.append(
                    {
                        "name": f"governance-chat-{index}",
                        "method": "POST",
                        "path": "/api/assistant/chat",
                        "json": {"query": query, "context": {}, "history": []},
                        "profile": profile,
                        "iteration": iteration + 1,
                    }
                )
            if manual_order_preview_fixture:
                requests.append(
                    {
                        "name": "manual-order-preview",
                        "method": "POST",
                        "path": "/api/orders/preview",
                        "json": manual_order_preview_fixture,
                        "profile": profile,
                        "iteration": iteration + 1,
                    }
                )
        return requests

    raise ValueError(f"Unknown profile: {profile}")


def allocate_profile_mix(
    *,
    virtual_users: int,
    read_share: int,
    ai_share: int,
    bot_share: int,
) -> Dict[str, int]:
    if virtual_users <= 0:
        raise ValueError("virtual_users must be greater than 0.")

    weights = {
        "read-heavy": max(0, int(read_share)),
        "ai-heavy": max(0, int(ai_share)),
        "bot-execution-heavy": max(0, int(bot_share)),
    }
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("At least one traffic share must be greater than 0.")

    raw_counts = {
        profile: (virtual_users * weight) / total_weight
        for profile, weight in weights.items()
    }
    counts = {profile: int(value) for profile, value in raw_counts.items()}
    assigned = sum(counts.values())
    remainders = sorted(
        (
            (raw_counts[profile] - counts[profile], weights[profile], profile)
            for profile in weights
        ),
        reverse=True,
    )
    for _, _, profile in remainders[: max(0, virtual_users - assigned)]:
        counts[profile] += 1
    return counts


def build_mixed_profile_requests(
    *,
    virtual_users: int,
    iterations_per_user: int,
    read_share: int,
    ai_share: int,
    bot_share: int,
    manual_order_preview_fixture: Optional[Dict[str, Any]] = None,
    read_think_time_seconds: float = DEFAULT_MIXED_READ_THINK_TIME_SECONDS,
    ai_think_time_seconds: float = DEFAULT_MIXED_AI_THINK_TIME_SECONDS,
    bot_think_time_seconds: float = DEFAULT_MIXED_BOT_THINK_TIME_SECONDS,
    user_start_stagger_seconds: float = DEFAULT_MIXED_USER_START_STAGGER_SECONDS,
    wave_width: int = DEFAULT_MIXED_WAVE_WIDTH,
) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
    distribution = allocate_profile_mix(
        virtual_users=virtual_users,
        read_share=read_share,
        ai_share=ai_share,
        bot_share=bot_share,
    )
    requests: List[Dict[str, Any]] = []
    virtual_user_id = 0
    per_profile_think_time = {
        "read-heavy": max(0.0, float(read_think_time_seconds)),
        "ai-heavy": max(0.0, float(ai_think_time_seconds)),
        "bot-execution-heavy": max(0.0, float(bot_think_time_seconds)),
    }
    safe_wave_width = max(1, int(wave_width))
    for scenario_profile in ["read-heavy", "ai-heavy", "bot-execution-heavy"]:
        for _ in range(distribution[scenario_profile]):
            virtual_user_id += 1
            profile_requests = build_profile_requests(
                scenario_profile,
                iterations=iterations_per_user,
                manual_order_preview_fixture=manual_order_preview_fixture,
            )
            user_wave_index = (virtual_user_id - 1) % safe_wave_width
            user_wave_batch = (virtual_user_id - 1) // safe_wave_width
            start_offset_seconds = (
                user_wave_index * user_start_stagger_seconds
            ) + (
                user_wave_batch * user_start_stagger_seconds
            )
            think_time_seconds = per_profile_think_time[scenario_profile]
            for request_index, request in enumerate(profile_requests):
                requests.append(
                    {
                        **request,
                        "profile": "mixed-load",
                        "scenario_profile": scenario_profile,
                        "virtual_user": virtual_user_id,
                        "scheduled_at_offset_s": round(
                            start_offset_seconds + (request_index * think_time_seconds),
                            3,
                        ),
                    }
                )
    return requests, distribution


def profile_concurrency(profile: str, mixed_concurrency: int = 20) -> int:
    return {
        "read-heavy": 4,
        "ai-heavy": 2,
        "bot-execution-heavy": 2,
        "mixed-load": max(1, int(mixed_concurrency)),
    }[profile]


async def build_clients(
    *,
    base_url: str,
    timeout_seconds: float,
    insecure_ssl: bool,
    bearer_token: Optional[str],
    login_email: Optional[str],
    login_password: Optional[str],
    health_url: Optional[str],
    health_bearer_token: Optional[str],
) -> tuple[httpx.AsyncClient, Optional[httpx.AsyncClient]]:
    verify: bool | ssl.SSLContext = not insecure_ssl
    if insecure_ssl:
        verify = False

    traffic_client = httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        timeout=timeout_seconds,
        verify=verify,
        headers={"Accept": "application/json"},
        follow_redirects=True,
    )

    if bearer_token:
        traffic_client.headers["Authorization"] = f"Bearer {bearer_token}"
    elif login_email and login_password:
        response = await traffic_client.post(
            "/api/auth/login",
            json={"email": login_email, "password": login_password},
        )
        response.raise_for_status()
    else:
        raise ValueError("Provide either bearer token or login email/password.")

    health_client: Optional[httpx.AsyncClient] = None
    if health_url:
        normalized_health_url = health_url.rstrip("/")
        health_client = httpx.AsyncClient(
            base_url=normalized_health_url,
            timeout=timeout_seconds,
            verify=verify,
            headers={"Accept": "application/json"},
            follow_redirects=True,
        )
        if health_bearer_token:
            health_client.headers["Authorization"] = f"Bearer {health_bearer_token}"
        health_client._tt_health_url = normalized_health_url  # type: ignore[attr-defined]

    return traffic_client, health_client


async def fetch_health_snapshot(
    client: Optional[httpx.AsyncClient],
    *,
    label: str,
) -> Dict[str, Any]:
    if client is None:
        return {"label": label, "skipped": True, "reason": "no_health_client"}

    started = time.perf_counter()
    try:
        health_url = getattr(client, "_tt_health_url", str(client.base_url))
        response = await client.get(health_url)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        payload = _safe_json(response.text)
        return {
            "label": label,
            "skipped": False,
            "http_status": response.status_code,
            "latency_ms": latency_ms,
            "payload": payload,
        }
    except Exception as exc:
        return {
            "label": label,
            "skipped": False,
            "http_status": 599,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "error": str(exc),
        }


async def sample_health_during_run(
    client: Optional[httpx.AsyncClient],
    *,
    interval_seconds: float,
    stop_event: asyncio.Event,
    snapshots: List[Dict[str, Any]],
) -> None:
    if client is None:
        return
    while not stop_event.is_set():
        snapshots.append(await fetch_health_snapshot(client, label=f"during-{len(snapshots) + 1}"))
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            continue


async def execute_request(
    client: httpx.AsyncClient,
    spec: Dict[str, Any],
) -> Dict[str, Any]:
    started = time.perf_counter()
    path = spec["path"]
    if spec.get("cache_bust"):
        separator = "&" if "?" in path else "?"
        path = f"{path}{separator}_={int(time.time() * 1000)}"

    try:
        response = await client.request(
            spec["method"],
            path,
            json=spec.get("json"),
        )
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        body = _safe_json(response.text)
        return {
            "name": spec["name"],
            "profile": spec["profile"],
            "iteration": spec["iteration"],
            "method": spec["method"],
            "path": spec["path"],
            "http_status": response.status_code,
            "latency_ms": latency_ms,
            "ok": response.status_code < 400,
            "response_preview": (body or response.text[:220]),
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return {
            "name": spec["name"],
            "profile": spec["profile"],
            "iteration": spec["iteration"],
            "method": spec["method"],
            "path": spec["path"],
            "http_status": 599,
            "latency_ms": latency_ms,
            "ok": False,
            "error": str(exc),
        }


async def run_profile(
    client: httpx.AsyncClient,
    *,
    profile: str,
    iterations: int,
    manual_order_preview_fixture: Optional[Dict[str, Any]],
    mixed_virtual_users: int = 100,
    mixed_iterations_per_user: int = 1,
    mixed_read_share: int = 80,
    mixed_ai_share: int = 15,
    mixed_bot_share: int = 5,
    mixed_concurrency: int = 20,
    mixed_read_think_time_seconds: float = DEFAULT_MIXED_READ_THINK_TIME_SECONDS,
    mixed_ai_think_time_seconds: float = DEFAULT_MIXED_AI_THINK_TIME_SECONDS,
    mixed_bot_think_time_seconds: float = DEFAULT_MIXED_BOT_THINK_TIME_SECONDS,
    mixed_user_start_stagger_seconds: float = DEFAULT_MIXED_USER_START_STAGGER_SECONDS,
    mixed_wave_width: int = DEFAULT_MIXED_WAVE_WIDTH,
) -> Dict[str, Any]:
    mix_distribution: Optional[Dict[str, int]] = None
    if profile == "mixed-load":
        specs, mix_distribution = build_mixed_profile_requests(
            virtual_users=mixed_virtual_users,
            iterations_per_user=mixed_iterations_per_user,
            read_share=mixed_read_share,
            ai_share=mixed_ai_share,
            bot_share=mixed_bot_share,
            manual_order_preview_fixture=manual_order_preview_fixture,
            read_think_time_seconds=mixed_read_think_time_seconds,
            ai_think_time_seconds=mixed_ai_think_time_seconds,
            bot_think_time_seconds=mixed_bot_think_time_seconds,
            user_start_stagger_seconds=mixed_user_start_stagger_seconds,
            wave_width=mixed_wave_width,
        )
    else:
        specs = build_profile_requests(
            profile,
            iterations=iterations,
            manual_order_preview_fixture=manual_order_preview_fixture,
        )
    semaphore = asyncio.Semaphore(profile_concurrency(profile, mixed_concurrency=mixed_concurrency))
    profile_started = time.perf_counter()

    async def _guarded(spec: Dict[str, Any]) -> Dict[str, Any]:
        scheduled_offset = float(spec.get("scheduled_at_offset_s", 0.0) or 0.0)
        elapsed = time.perf_counter() - profile_started
        if scheduled_offset > elapsed:
            await asyncio.sleep(scheduled_offset - elapsed)
        async with semaphore:
            return await execute_request(client, spec)

    started = time.perf_counter()
    results = await asyncio.gather(*[_guarded(spec) for spec in specs])
    latencies = [item["latency_ms"] for item in results]
    status_counts: Dict[str, int] = {}
    profile_counts: Dict[str, int] = {}
    for item in results:
        key = str(item["http_status"])
        status_counts[key] = status_counts.get(key, 0) + 1
        scenario_profile = item.get("scenario_profile") or item["profile"]
        profile_counts[scenario_profile] = profile_counts.get(scenario_profile, 0) + 1

    summary = {
        "profile": profile,
        "request_count": len(results),
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "avg_latency_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
        "p95_latency_ms": _percentile(latencies, 0.95) if latencies else 0.0,
        "max_latency_ms": round(max(latencies), 2) if latencies else 0.0,
        "success_count": sum(1 for item in results if item["ok"]),
        "failure_count": sum(1 for item in results if not item["ok"]),
        "status_counts": status_counts,
        "scenario_request_counts": profile_counts,
        "results": results,
    }
    if mix_distribution is not None:
        summary["mixed_distribution"] = mix_distribution
        summary["virtual_users"] = mixed_virtual_users
        summary["iterations_per_user"] = mixed_iterations_per_user
        summary["mixed_concurrency"] = mixed_concurrency
        summary["pacing"] = {
            "read_think_time_seconds": mixed_read_think_time_seconds,
            "ai_think_time_seconds": mixed_ai_think_time_seconds,
            "bot_think_time_seconds": mixed_bot_think_time_seconds,
            "user_start_stagger_seconds": mixed_user_start_stagger_seconds,
            "wave_width": mixed_wave_width,
        }
        summary["traffic_mix"] = {
            "read_share": mixed_read_share,
            "ai_share": mixed_ai_share,
            "bot_share": mixed_bot_share,
        }
    return summary


def render_markdown(summary: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"# Platform Phase 2.1 Capacity Run — {summary['run_label']}")
    lines.append("")
    lines.append(f"- base_url: `{summary['base_url']}`")
    lines.append(f"- profiles: `{', '.join(summary['profiles'])}`")
    lines.append(f"- iterations per profile: `{summary['iterations']}`")
    lines.append(f"- timestamp: `{summary['completed_at']}`")
    lines.append("")
    for profile in summary["profile_summaries"]:
        lines.append(f"## {profile['profile']}")
        lines.append("")
        if profile["profile"] == "mixed-load":
            lines.append(f"- virtual_users: `{profile.get('virtual_users')}`")
            lines.append(f"- iterations_per_user: `{profile.get('iterations_per_user')}`")
            lines.append(f"- mixed_concurrency: `{profile.get('mixed_concurrency')}`")
            lines.append(f"- mixed_distribution: `{profile.get('mixed_distribution')}`")
            lines.append(f"- scenario_request_counts: `{profile.get('scenario_request_counts')}`")
            lines.append(f"- traffic_mix: `{profile.get('traffic_mix')}`")
            lines.append(f"- pacing: `{profile.get('pacing')}`")
        lines.append(f"- request_count: `{profile['request_count']}`")
        lines.append(f"- success_count: `{profile['success_count']}`")
        lines.append(f"- failure_count: `{profile['failure_count']}`")
        lines.append(f"- avg_latency_ms: `{profile['avg_latency_ms']}`")
        lines.append(f"- p95_latency_ms: `{profile['p95_latency_ms']}`")
        lines.append(f"- max_latency_ms: `{profile['max_latency_ms']}`")
        lines.append(f"- status_counts: `{profile['status_counts']}`")
        lines.append("")
    lines.append("## Health snapshots")
    lines.append("")
    for snapshot in summary["health_snapshots"]:
        if snapshot.get("skipped"):
            lines.append(f"- `{snapshot['label']}`: skipped (`{snapshot['reason']}`)")
            continue
        status = (snapshot.get("payload") or {}).get("status") if isinstance(snapshot.get("payload"), dict) else None
        lines.append(
            f"- `{snapshot['label']}`: http=`{snapshot.get('http_status')}` "
            f"health=`{status}` latency_ms=`{snapshot.get('latency_ms')}`"
        )
    lines.append("")
    return "\n".join(lines)


async def async_main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Tradamind Platform Phase 2.1 capacity harness")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--bearer-token", default=None)
    parser.add_argument("--bearer-token-env", default=None)
    parser.add_argument("--login-email", default=None)
    parser.add_argument("--password-env", default=None)
    parser.add_argument("--health-url", default=None, help="Full /api/system/health URL; omit to skip health snapshots.")
    parser.add_argument("--health-bearer-token-env", default=None)
    parser.add_argument(
        "--profiles",
        nargs="+",
        default=["read-heavy", "ai-heavy", "bot-execution-heavy"],
        choices=PROFILE_CHOICES,
    )
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--virtual-users", type=int, default=100)
    parser.add_argument("--iterations-per-user", type=int, default=1)
    parser.add_argument("--read-share", type=int, default=80)
    parser.add_argument("--ai-share", type=int, default=15)
    parser.add_argument("--bot-share", type=int, default=5)
    parser.add_argument("--mixed-concurrency", type=int, default=20)
    parser.add_argument("--mixed-read-think-time-seconds", type=float, default=DEFAULT_MIXED_READ_THINK_TIME_SECONDS)
    parser.add_argument("--mixed-ai-think-time-seconds", type=float, default=DEFAULT_MIXED_AI_THINK_TIME_SECONDS)
    parser.add_argument("--mixed-bot-think-time-seconds", type=float, default=DEFAULT_MIXED_BOT_THINK_TIME_SECONDS)
    parser.add_argument("--mixed-user-start-stagger-seconds", type=float, default=DEFAULT_MIXED_USER_START_STAGGER_SECONDS)
    parser.add_argument("--mixed-wave-width", type=int, default=DEFAULT_MIXED_WAVE_WIDTH)
    parser.add_argument("--health-interval-seconds", type=float, default=10.0)
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    parser.add_argument("--manual-order-preview-fixture", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--insecure", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    bearer_token = args.bearer_token or (os.getenv(args.bearer_token_env) if args.bearer_token_env else None)
    login_password = os.getenv(args.password_env) if args.password_env else None
    health_bearer_token = (
        os.getenv(args.health_bearer_token_env) if args.health_bearer_token_env else None
    )
    manual_order_preview_fixture = load_manual_order_preview_fixture(args.manual_order_preview_fixture)

    traffic_client, health_client = await build_clients(
        base_url=args.base_url,
        timeout_seconds=args.timeout_seconds,
        insecure_ssl=args.insecure,
        bearer_token=bearer_token,
        login_email=args.login_email,
        login_password=login_password,
        health_url=args.health_url,
        health_bearer_token=health_bearer_token,
    )

    try:
        health_snapshots: List[Dict[str, Any]] = []
        health_snapshots.append(await fetch_health_snapshot(health_client, label="before"))
        stop_event = asyncio.Event()
        sampler = asyncio.create_task(
            sample_health_during_run(
                health_client,
                interval_seconds=args.health_interval_seconds,
                stop_event=stop_event,
                snapshots=health_snapshots,
            )
        )
        try:
            profile_summaries = []
            for profile in args.profiles:
                profile_summaries.append(
                    await run_profile(
                        traffic_client,
                        profile=profile,
                        iterations=args.iterations,
                        manual_order_preview_fixture=manual_order_preview_fixture,
                        mixed_virtual_users=args.virtual_users,
                        mixed_iterations_per_user=args.iterations_per_user,
                        mixed_read_share=args.read_share,
                        mixed_ai_share=args.ai_share,
                        mixed_bot_share=args.bot_share,
                        mixed_concurrency=args.mixed_concurrency,
                        mixed_read_think_time_seconds=args.mixed_read_think_time_seconds,
                        mixed_ai_think_time_seconds=args.mixed_ai_think_time_seconds,
                        mixed_bot_think_time_seconds=args.mixed_bot_think_time_seconds,
                        mixed_user_start_stagger_seconds=args.mixed_user_start_stagger_seconds,
                        mixed_wave_width=args.mixed_wave_width,
                    )
                )
        finally:
            stop_event.set()
            await sampler
        health_snapshots.append(await fetch_health_snapshot(health_client, label="after"))
    finally:
        await traffic_client.aclose()
        if health_client:
            await health_client.aclose()

    summary = {
        "run_label": f"phase2-1-{int(time.time())}",
        "base_url": args.base_url.rstrip("/"),
        "profiles": args.profiles,
        "iterations": args.iterations,
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "health_snapshots": health_snapshots,
        "profile_summaries": profile_summaries,
    }
    args.output_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    args.output_md.write_text(render_markdown(summary), encoding="utf-8")
    print(f"Wrote JSON report to {args.output_json}")
    print(f"Wrote Markdown report to {args.output_md}")
    return 0


def main(argv: Optional[Iterable[str]] = None) -> int:
    try:
        return asyncio.run(async_main(argv))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
