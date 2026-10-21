"""Authenticated mixed read load. Optional FINN chat is explicit and fixture-only.

Input JSON: [{"user_id": 1, "access_token": "..."}, ...]. Keep this file outside Git.
"""

import argparse
import asyncio
import json
import math
import os
import random
import resource
import sys
import time
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

import httpx


ROUTES = (
    ("workspace", "GET", "/api/workspace/asset?symbol=BTC&watchlist_symbols=BTC,ETH", 5),
    ("finn_conversations", "GET", "/api/assistant/v2/conversations", 2),
    ("trade_reviews", "GET", "/api/bot/trade-reviews?limit=20", 1),
)
PRODUCTION_ORIGIN = "https://tradamind.com"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def validate_base_url(raw_url, *, allow_production):
    parsed = urlparse(raw_url)
    if (not parsed.hostname or parsed.username or parsed.password or parsed.path not in {"", "/"}
            or parsed.query or parsed.fragment):
        raise ValueError("Base URL must be a bare origin without credentials, path, query or fragment")
    origin = raw_url.rstrip("/")
    if parsed.hostname in LOOPBACK_HOSTS:
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Local load test requires HTTP or HTTPS")
        return origin
    if parsed.scheme != "https":
        raise ValueError("Remote load tests require HTTPS")
    if origin != PRODUCTION_ORIGIN or not allow_production:
        raise ValueError("Production load requires the exact approved origin and --allow-production")
    return origin


def percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    return round(values[min(len(values) - 1, max(0, int(len(values) * fraction + 0.999999) - 1))], 2)


def chat_response_state(response):
    """Classify the visible FINN contract without logging its private body."""
    try:
        body = response.json()
    except ValueError:
        return "malformed", None
    if not isinstance(body, dict):
        return "malformed", None
    state = body.get("state")
    trace = body.get("response_trace")
    if not isinstance(state, dict) or not isinstance(trace, dict):
        return "malformed", None
    flow = state.get("current_flow")
    if flow in {"finn_v2_visible_failed", "finn_v2_visible_terminal_failed"} or body.get("intent") == "unavailable":
        return "unavailable", None
    run_id = state.get("run_id")
    if not isinstance(run_id, str) or not run_id or len(run_id) > 128:
        return "malformed", None
    if trace.get("run_id") != run_id:
        return "malformed", None
    if flow == "finn_v2_visible_pending" and body.get("intent") == "processing":
        return "pending", run_id
    if (flow == "finn_v2_visible" and body.get("intent") != "unavailable"
            and isinstance(body.get("response"), str) and body["response"].strip()
            and trace.get("pipeline_version") == "finn_v2"
            and trace.get("response_source") == "finn_v2_verified"
            and trace.get("verifier_status") in {"passed", "repaired", "registry_grounded"}
            and isinstance(trace.get("delivery_envelope"), dict)
            and trace["delivery_envelope"].get("status") == "completed"
            and not trace.get("error")):
        return "ok", run_id
    return "unavailable", run_id


async def chat_turn_outcome(client, response, authorization, timeout_seconds, stop_event):
    state, run_id = chat_response_state(response)
    if state != "pending":
        return state
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline and not stop_event.is_set():
        await asyncio.sleep(min(2, max(0, deadline - time.monotonic())))
        try:
            polled = await client.get(
                f"/api/assistant/v2/runs/{run_id}",
                headers={"Authorization": authorization},
            )
            if polled.status_code != 200:
                return "poll_http_error"
            body = polled.json()
        except (httpx.HTTPError, ValueError):
            return "poll_error"
        if not isinstance(body, dict) or body.get("run_id") != run_id:
            return "poll_malformed"
        status = body.get("status")
        if status == "completed":
            verified = body.get("response")
            if (isinstance(verified, dict)
                    and isinstance(verified.get("content"), str) and verified["content"].strip()
                    and verified.get("mode") != "UNAVAILABLE"
                    and verified.get("verifier_status") in {"passed", "repaired", "registry_grounded"}
                    and not body.get("error_code")):
                return "ok"
            return "terminal_invalid"
        if status in {"failed", "canceled", "blocked", "rejected", "unavailable", "downgraded", "clarification_required"}:
            return "terminal_unsuccessful"
        if status not in {"created", "queued", "collecting", "planned", "reasoning", "verifying"}:
            return "poll_malformed"
    return "interrupted" if stop_event.is_set() else "terminal_timeout"


async def virtual_user(client, fixture, deadline, think_seconds, chat_budget, results, stop_event,
                       initial_spread_seconds=0, steady_results=None, steady_started=None,
                       chat_terminal_timeout_seconds=60):
    rng = random.Random(fixture["user_id"])
    authorization = f"Bearer {fixture['access_token']}"
    choices = list(ROUTES)
    if chat_budget is not None:
        choices.append(("finn_chat", "POST", "/api/assistant/chat", 1))
    if initial_spread_seconds:
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=rng.uniform(0, initial_spread_seconds))
        except asyncio.TimeoutError:
            pass
    while time.monotonic() < deadline and not stop_event.is_set():
        name, method, path, _ = rng.choices(choices, weights=[item[3] for item in choices])[0]
        if name == "finn_chat":
            # Keep the paid per-stage quota for the measured steady interval.
            if ((steady_started is not None and time.monotonic() < steady_started)
                    or chat_budget["remaining"] <= 0):
                name, method, path, _ = ROUTES[0]
            else:
                chat_budget["remaining"] -= 1
        started_at = time.monotonic()
        started = time.perf_counter()
        request_started_utc = time.time()
        sent_trace_id = f"cap-{uuid.uuid4().hex[:16]}"
        response = None
        outcome = "ok"
        try:
            response = await client.request(
                method, path, headers={"Authorization": authorization, "X-Trace-Id": sent_trace_id},
                json={"query": "Explain the current BTC market context in general terms.",
                      "context": {"page": "load_fixture", "symbol": "BTC"}} if name == "finn_chat" else None,
            )
            status = response.status_code
        except httpx.HTTPError:
            status = 0
        if name == "finn_chat" and response is not None and status == 200:
            outcome = await chat_turn_outcome(
                client, response, authorization, chat_terminal_timeout_seconds, stop_event,
            )
        backend_ms = None
        trace_id = sent_trace_id
        if response is not None:
            response_headers = getattr(response, "headers", {})
            trace_id = response_headers.get("x-trace-id") or sent_trace_id
            timing = response_headers.get("server-timing", "")
            if timing.startswith("app;dur="):
                try:
                    backend_ms = max(0.0, float(timing.removeprefix("app;dur=")))
                except ValueError:
                    pass
        sample = (status, (time.perf_counter() - started) * 1000, backend_ms, trace_id,
                  round(request_started_utc, 6), round(time.time(), 6), outcome)
        results[name].append(sample)
        if steady_results is not None and steady_started is not None and started_at >= steady_started:
            steady_results[name].append(sample)
        if not 200 <= status < 300 or outcome != "ok":
            stop_event.set()
            break
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=rng.uniform(
                think_seconds * 0.5, think_seconds * 1.5,
            ))
        except asyncio.TimeoutError:
            pass


def identity_matches(response, fixture):
    if response.status_code != 200:
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    if not isinstance(body, dict):
        return False
    if body.get("id") != fixture["user_id"]:
        return False
    return not fixture.get("email") or body.get("email") == fixture["email"]


async def verify_identity(client, fixtures):
    semaphore = asyncio.Semaphore(25)

    async def check(fixture):
        async with semaphore:
            try:
                response = await client.get("/api/auth/me", headers={
                    "Authorization": f"Bearer {fixture['access_token']}",
                })
            except httpx.HTTPError:
                return False
            return identity_matches(response, fixture)

    checks = await asyncio.gather(*(check(fixture) for fixture in fixtures))
    if not all(checks):
        raise RuntimeError(f"Identity preflight failed for {len(checks) - sum(checks)} fixture account(s)")
    print(json.dumps({"identity_preflight": {"accounts": len(checks), "matched": len(checks)}}), flush=True)


def report(label, results):
    summary = {}
    for name, samples in results.items():
        latencies = [sample[1] for sample in samples if 200 <= sample[0] < 300]
        statuses = Counter(str(sample[0]) for sample in samples)
        backend_latencies = [sample[2] for sample in samples if len(sample) > 2 and sample[2] is not None]
        slow_traces = [
            {"trace_id": sample[3], "client_ms": round(sample[1], 2), "backend_ms": sample[2],
             "start_utc_epoch": sample[4] if len(sample) > 4 else None,
             "end_utc_epoch": sample[5] if len(sample) > 5 else None}
            for sample in sorted(samples, key=lambda item: item[1], reverse=True)
            if len(sample) > 3 and sample[3]
        ][:5]
        summary[name] = {
            "requests": len(samples),
            "statuses": dict(statuses),
            "outcomes": dict(Counter(sample[6] if len(sample) > 6 else "ok" for sample in samples)),
            "p50_ms": percentile(latencies, 0.50),
            "p95_ms": percentile(latencies, 0.95),
            "p95_all_ms": percentile([sample[1] for sample in samples], 0.95),
            "backend_p95_ms": percentile(backend_latencies, 0.95),
            "backend_timing_samples": len(backend_latencies),
            "slow_traces": slow_traces,
            "max_ms": round(max(latencies), 2) if latencies else None,
        }
    print(json.dumps({"stage": label, "routes": summary}, sort_keys=True), flush=True)
    return summary


def stage_has_blocking_errors(summary):
    return any(
        any(not 200 <= int(code) < 300 for code in route["statuses"])
        or any(outcome != "ok" for outcome in route.get("outcomes", {}))
        for route in summary.values()
    )


def stage_exceeds_latency_limit(summary, limits):
    exceeded = sorted(set(limits) - set(summary))
    exceeded.extend(
        name for name, route in summary.items()
        if name in limits and (
            route["p95_all_ms"] is None or route["p95_all_ms"] > limits[name]
        )
    )
    return exceeded


async def monitor_stage(results, limits, deadline, stop_event, latency_abort_routes):
    """Stop an active stage once a measured route has a stable p95 breach."""
    while not stop_event.is_set() and time.monotonic() < deadline:
        await asyncio.sleep(min(2, max(0, deadline - time.monotonic())))
        for name, limit in limits.items():
            samples = results.get(name, ())
            if len(samples) >= 20 and percentile([sample[1] for sample in samples], 0.95) > limit:
                latency_abort_routes.append(name)
                stop_event.set()
                return


async def monitor_generator(samples, interval=0.5):
    """Sample load-process scheduling and file descriptors without request data."""
    loop = asyncio.get_running_loop()
    previous_wall = loop.time()
    previous_cpu = time.process_time()
    while True:
        expected = loop.time() + interval
        await asyncio.sleep(interval)
        now = loop.time()
        cpu = time.process_time()
        open_fds = None
        for fd_directory in ("/proc/self/fd", "/dev/fd"):
            try:
                open_fds = len(os.listdir(fd_directory))
                break
            except OSError:
                continue
        samples.append({
            "event_loop_lag_ms": round(max(0, now - expected) * 1000, 2),
            "process_cpu_pct": round(max(0, cpu - previous_cpu) / max(now - previous_wall, 0.001) * 100, 2),
            "open_fds": open_fds,
        })
        previous_wall, previous_cpu = now, cpu


def generator_report(samples):
    fd_samples = [sample["open_fds"] for sample in samples if sample["open_fds"] is not None]
    return {
        "samples": len(samples),
        "event_loop_lag_p95_ms": percentile([sample["event_loop_lag_ms"] for sample in samples], 0.95),
        "event_loop_lag_max_ms": max((sample["event_loop_lag_ms"] for sample in samples), default=None),
        "process_cpu_p95_pct": percentile([sample["process_cpu_pct"] for sample in samples], 0.95),
        "open_fds_max": max(fd_samples, default=None),
    }


def reject_aborted_stage(latency_abort_routes):
    if latency_abort_routes:
        raise RuntimeError(
            f"Load stage was stopped for interim p95 breach on {', '.join(latency_abort_routes)}"
        )


def require_operator_continue(next_stage):
    answer = input(f"Inspect host, DB and queue metrics. Type CONTINUE for {next_stage}: ")
    if answer.strip() != "CONTINUE":
        raise RuntimeError("Operator declined the next load stage")


def generator_fd_limits(max_users, *, production):
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if production and soft < max_users + 128:
        raise ValueError(
            f"Load generator needs at least {max_users + 128} open file descriptors "
            f"(soft={soft}, hard={hard}); raise the shell's ulimit -n before running"
        )
    return {"soft": soft, "hard": hard}


def chat_stage_quotas(max_requests, stage_count, *, production):
    minimum = 20 if production else 1
    if max_requests < minimum * stage_count:
        raise ValueError(
            f"FINN chat needs at least {minimum} requests per stage "
            f"({minimum * stage_count} total)"
        )
    return [minimum] * (stage_count - 1) + [max_requests - minimum * (stage_count - 1)]


async def run(args, fixtures):
    limits = httpx.Limits(max_connections=max(100, args.max_users + 50), max_keepalive_connections=args.max_users)
    async with httpx.AsyncClient(base_url=args.base_url, timeout=args.timeout, limits=limits) as client:
        stages = args.stages.split(",")
        chat_quotas = (chat_stage_quotas(args.max_chat_requests, len(stages), production=args.allow_production)
                       if args.include_chat else None)
        for stage_index, stage in enumerate(stages):
            chat_budget = {"remaining": chat_quotas[stage_index]} if chat_quotas is not None else None
            users_raw, seconds_raw = stage.split(":", 1)
            users, seconds = int(users_raw), int(seconds_raw)
            if users < 1 or users > len(fixtures) or seconds < 1:
                raise ValueError("Each stage needs positive duration and one distinct fixture per active user")
            await verify_identity(client, fixtures[:users])
            results = defaultdict(list)
            steady_results = defaultdict(list)
            stop_event = asyncio.Event()
            latency_abort_routes = []
            generator_samples = []
            # Keep the requested duration after the final fixture has joined;
            # the deterministic first-request spread is a separate ramp.
            steady_started = time.monotonic() + args.think_seconds
            deadline = steady_started + seconds
            monitor = asyncio.create_task(monitor_stage(
                steady_results, args.p95_limits, deadline, stop_event, latency_abort_routes,
            ))
            generator_monitor = asyncio.create_task(monitor_generator(generator_samples))
            chat_options = ({"chat_terminal_timeout_seconds": args.chat_terminal_timeout_seconds}
                            if args.include_chat else {})
            try:
                await asyncio.gather(*(
                    virtual_user(client, fixture, deadline, args.think_seconds, chat_budget, results,
                                 stop_event, initial_spread_seconds=args.think_seconds,
                                 steady_results=steady_results, steady_started=steady_started,
                                 **chat_options)
                    for fixture in fixtures[:users]
                ))
            except asyncio.CancelledError:
                # asyncio.run translates the operator's first Ctrl-C into
                # cancellation. Keep the partial route evidence even when a
                # database or host stop gate interrupts the stage.
                stop_event.set()
                report(f"{users} users / interrupted ramp + steady", results)
                report(f"{users} users / interrupted steady interval", steady_results)
                print(json.dumps({
                    "stage_aborted": {
                        "users": users,
                        "reason": "operator_interrupt",
                        "steady_seconds_observed": round(max(0, time.monotonic() - steady_started), 2),
                    }
                }), flush=True)
                raise
            finally:
                monitor.cancel()
                generator_monitor.cancel()
                await asyncio.gather(monitor, generator_monitor, return_exceptions=True)
                print(json.dumps({"stage": f"{users} users", "generator": generator_report(generator_samples)}),
                      flush=True)
            all_summary = report(f"{users} users / ramp + {seconds}s steady", results)
            summary = report(f"{users} users / observed steady interval", steady_results)
            reject_aborted_stage(latency_abort_routes)
            if stage_has_blocking_errors(all_summary):
                raise RuntimeError("Load stage had non-2xx or timeout responses; refusing a higher stage")
            exceeded = stage_exceeds_latency_limit(summary, args.p95_limits)
            if exceeded:
                raise RuntimeError(f"Load stage exceeded p95 limits for {', '.join(exceeded)}; refusing a higher stage")
            if stage_index < len(stages) - 1 and args.between_stage_pause_seconds:
                print(json.dumps({"operator_pause_seconds": args.between_stage_pause_seconds,
                                  "next_stage": stages[stage_index + 1]}), flush=True)
                await asyncio.sleep(args.between_stage_pause_seconds)
            if stage_index < len(stages) - 1 and args.allow_production:
                await asyncio.to_thread(require_operator_continue, stages[stage_index + 1])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--fixtures", required=True, type=Path)
    parser.add_argument("--stages", default="100:120,500:120,1000:300")
    parser.add_argument("--think-seconds", type=float, default=10.0)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--include-chat", action="store_true")
    parser.add_argument("--max-chat-requests", type=int, default=0)
    parser.add_argument("--max-chat-p95-ms", type=float)
    parser.add_argument("--chat-terminal-timeout-seconds", type=float, default=60)
    parser.add_argument("--provider-hard-cap-usd", type=float)
    parser.add_argument("--confirm-provider-hard-cap", action="store_true")
    parser.add_argument("--allow-production", action="store_true")
    parser.add_argument("--max-workspace-p95-ms", type=float)
    parser.add_argument("--max-finn-p95-ms", type=float)
    parser.add_argument("--max-reviews-p95-ms", type=float)
    parser.add_argument("--between-stage-pause-seconds", type=int, default=60)
    args = parser.parse_args()
    try:
        args.base_url = validate_base_url(args.base_url, allow_production=args.allow_production)
    except ValueError as exc:
        parser.error(str(exc))
    if args.include_chat and args.max_chat_requests < 1:
        parser.error("FINN chat load requires --max-chat-requests with an explicit positive budget")
    if args.include_chat and args.allow_production and args.max_chat_p95_ms is None:
        parser.error("Production FINN chat load requires --max-chat-p95-ms")
    if args.include_chat and args.allow_production and (
        args.provider_hard_cap_usd is None
        or not math.isfinite(args.provider_hard_cap_usd)
        or args.provider_hard_cap_usd <= 0
        or not args.confirm_provider_hard_cap
        or not sys.stdin.isatty()
    ):
        parser.error("Production FINN chat requires a provider-side hard USD cap, its value, confirmation and an interactive terminal")
    if (not math.isfinite(args.chat_terminal_timeout_seconds)
            or args.chat_terminal_timeout_seconds < 1):
        parser.error("Chat terminal timeout must be finite and at least 1 second")
    if not math.isfinite(args.think_seconds) or args.think_seconds < (1 if args.allow_production else 0.01):
        parser.error("Think time must be finite and at least 1 second in production")
    thresholds = (args.max_workspace_p95_ms, args.max_finn_p95_ms, args.max_reviews_p95_ms)
    if args.allow_production and any(value is None for value in thresholds):
        parser.error("Production load requires explicit p95 limits for workspace, FINN and reviews")
    if any(value is not None and (not math.isfinite(value) or value <= 0)
           for value in (*thresholds, args.max_chat_p95_ms)):
        parser.error("p95 limits must be finite positive numbers")
    if args.between_stage_pause_seconds < 0 or (args.allow_production and args.between_stage_pause_seconds < 30):
        parser.error("Production load requires at least 30 seconds between stages")
    if args.allow_production and "," in args.stages and not sys.stdin.isatty():
        parser.error("Multi-stage production load requires an interactive operator terminal")
    args.p95_limits = {name: value for name, value in {
        "workspace": args.max_workspace_p95_ms,
        "finn_conversations": args.max_finn_p95_ms,
        "trade_reviews": args.max_reviews_p95_ms,
        "finn_chat": args.max_chat_p95_ms if args.include_chat else None,
    }.items() if value is not None}
    fixtures = json.loads(args.fixtures.read_text())
    if not isinstance(fixtures, list) or not fixtures or any(
        not isinstance(item, dict) or not item.get("user_id") or not item.get("access_token")
        for item in fixtures
    ):
        parser.error("Fixture file must contain distinct user_id and access_token objects")
    if len({item["user_id"] for item in fixtures}) != len(fixtures):
        parser.error("Fixture user IDs must be unique")
    args.max_users = max(int(item.split(":", 1)[0]) for item in args.stages.split(","))
    if args.include_chat:
        try:
            chat_stage_quotas(args.max_chat_requests, len(args.stages.split(",")), production=args.allow_production)
        except ValueError as exc:
            parser.error(str(exc))
    if len(fixtures) < args.max_users:
        parser.error("Provide a distinct fixture for every user in the largest stage")
    try:
        limits = generator_fd_limits(args.max_users, production=args.allow_production)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps({"generator_fd_limit": limits}), flush=True)
    if args.include_chat and args.allow_production:
        expected = f"CAP {args.provider_hard_cap_usd:g}"
        if input(f"Confirm the provider project's enforced USD spending cap by typing {expected}: ").strip() != expected:
            parser.error("Provider hard-cap confirmation declined")
    asyncio.run(run(args, fixtures))


if __name__ == "__main__":
    main()
