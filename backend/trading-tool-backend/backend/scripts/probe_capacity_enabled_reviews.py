"""Measure the enabled trade-review GET in one isolated production process.

The process has no listening socket. Its rollout override applies only to
requests sent through ASGITransport and is restored before exit. This measures
the real route, middleware, Redis limiter and PostgreSQL reads without changing
the deployed API or worker rollout. It does not measure Nginx or multiple API
processes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import random
import stat
import time
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

import httpx
from sqlalchemy import text

from backend.infrastructure.database import db_host, db_name, db_port, engine, sync_engine
from backend.scripts.provision_capacity_fixtures import CAMPAIGN_RE, REPO_ROOT, checked_rows, fixture_email


def resource_snapshot() -> dict:
    """Read cluster headroom; failure to inspect is itself a stop condition."""
    import redis
    from backend.celery_task.queue_policy import NAMED_QUEUES
    from backend.services.system_health_service import SystemHealthService

    with sync_engine.connect() as connection:
        connection.execute(text("SET LOCAL statement_timeout = '2s'"))
        row = connection.execute(text("""
            SELECT current_setting('max_connections')::int AS maximum,
                   (current_setting('superuser_reserved_connections')::int
                    + COALESCE(current_setting('reserved_connections', true), '0')::int) AS reserved,
                   (SELECT COUNT(*) FROM pg_stat_activity) AS used,
                   (SELECT COUNT(*) FROM pg_stat_activity
                    WHERE wait_event_type='Lock') AS lock_waiters,
                   (SELECT COUNT(*) FROM pg_stat_activity
                    WHERE state='idle in transaction'
                      AND xact_start < NOW() - INTERVAL '10 seconds') AS long_idle_transactions
        """)).mappings().one()
    memory_kib = None
    with open("/proc/meminfo", encoding="ascii") as info:
        for line in info:
            if line.startswith("MemAvailable:"):
                memory_kib = int(line.split()[1])
                break
    if memory_kib is None:
        raise RuntimeError("MemAvailable unavailable")
    broker_url = os.getenv("CELERY_BROKER_URL") or os.getenv("REDIS_URL")
    if not broker_url:
        raise RuntimeError("Redis broker URL unavailable")
    client = redis.from_url(broker_url, socket_connect_timeout=1, socket_timeout=1)
    try:
        if not client.ping():
            raise RuntimeError("Redis broker unavailable")
        queues = {}
        for name in NAMED_QUEUES:
            depth = int(client.llen(name))
            oldest = client.lrange(name, -1, -1) if depth else []
            age = SystemHealthService._queue_age_summary(oldest)
            queues[name] = {"depth": depth, "oldest_age_seconds": age["oldest_message_age_seconds"]}
    finally:
        client.close()
    return {
        "db_max": int(row["maximum"]), "db_used": int(row["used"]),
        "db_free": int(row["maximum"] - row["used"] - row["reserved"]),
        "lock_waiters": int(row["lock_waiters"]),
        "long_idle_transactions": int(row["long_idle_transactions"]),
        "mem_available_mib": memory_kib // 1024,
        "queues": queues,
    }


def resource_stop_reason(snapshot: dict, baseline: dict, *, minimum_db_free: int = 20) -> str | None:
    if snapshot["db_free"] < minimum_db_free:
        return "database_headroom"
    if snapshot["lock_waiters"] or snapshot["long_idle_transactions"]:
        return "database_lock_or_long_transaction"
    if snapshot["mem_available_mib"] < 1024:
        return "host_memory"
    for name, queue in snapshot["queues"].items():
        starting_depth = baseline["queues"][name]["depth"]
        if queue["depth"] and queue["oldest_age_seconds"] is None:
            return "queue_age_unavailable"
        if queue["depth"] > starting_depth + 50:
            return "queue_growth"
        if name.endswith(("execution_critical", "finn_interactive")) and queue["depth"] > 5:
            return "critical_queue_depth"
        age = queue["oldest_age_seconds"]
        baseline_age = baseline["queues"][name]["oldest_age_seconds"] or 0
        if age is not None and age > baseline_age + 30:
            return "queue_age_growth"
        if age is not None and age > (60 if name.endswith(("execution_critical", "finn_interactive")) else 300):
            return "queue_age"
    return None


def diagnostic_possible_new_connections() -> int:
    """Reserve the remaining async and sync pool slots before each stage."""
    async_open = engine.pool.checkedin() + engine.pool.checkedout()
    sync_open = sync_engine.pool.checkedin() + sync_engine.pool.checkedout()
    return max(0, 20 - async_open) + max(0, 3 - sync_open)


def private_fixtures(path: Path, campaign: str) -> list[dict]:
    resolved = path.resolve(strict=True)
    if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
        raise ValueError("Fixture token file must be outside the repository")
    if (stat.S_IMODE(resolved.stat().st_mode) & 0o077
            or stat.S_IMODE(resolved.parent.stat().st_mode) & 0o077):
        raise ValueError("Fixture token file and directory must be private")
    fixtures = json.loads(resolved.read_text())
    if not isinstance(fixtures, list) or not fixtures or len(fixtures) > 1000:
        raise ValueError("Expected 1-1000 capacity fixtures")
    for index, fixture in enumerate(fixtures, 1):
        if (not isinstance(fixture, dict)
                or fixture.get("email") != fixture_email(campaign, index)
                or type(fixture.get("user_id")) is not int
                or not isinstance(fixture.get("access_token"), str)
                or not fixture["access_token"]):
            raise ValueError("Fixture token file must contain exact ordered campaign accounts")
    if len({fixture["user_id"] for fixture in fixtures}) != len(fixtures):
        raise ValueError("Fixture account IDs must be distinct")
    with sync_engine.connect() as connection:
        rows = checked_rows(connection, campaign, len(fixtures))
        if len(rows) != len(fixtures):
            raise ValueError("All marked capacity accounts must exist")
        for fixture in fixtures:
            row = rows[fixture["email"]]
            if row["id"] != fixture["user_id"] or not row["is_active"]:
                raise ValueError("Fixture account identity or active status changed")
        review_count = connection.execute(text("""
            SELECT COUNT(*) FROM finn_trade_reviews WHERE user_id = ANY(:ids)
        """), {"ids": [fixture["user_id"] for fixture in fixtures]}).scalar_one()
        if review_count:
            raise ValueError("Capacity fixture accounts contain real review content")
    return fixtures


@contextmanager
def process_local_review_rollout():
    keys = ("FINN_TRADE_REVIEW_ROLLOUT", "FINN_TRADE_REVIEW_USER_IDS")
    previous = {key: os.environ.get(key) for key in keys}
    try:
        os.environ["FINN_TRADE_REVIEW_ROLLOUT"] = "all"
        os.environ.pop("FINN_TRADE_REVIEW_USER_IDS", None)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)], 2)


def enabled_empty_review(response: httpx.Response) -> bool:
    if response.status_code != 200:
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    return (isinstance(body, dict) and body.get("status") != "disabled"
            and body.get("items") == [] and body.get("total") == 0
            and isinstance(body.get("weekly"), dict)
            and body["weekly"].get("status") == "complete")


async def identity_preflight(client: httpx.AsyncClient, fixtures: list[dict], timeout: float) -> None:
    semaphore = asyncio.Semaphore(25)

    async def check(fixture: dict) -> bool:
        async with semaphore:
            try:
                response = await asyncio.wait_for(client.get("/api/auth/me", headers={
                    "Authorization": f"Bearer {fixture['access_token']}",
                }), timeout=timeout)
            except (asyncio.TimeoutError, httpx.HTTPError):
                return False
            if response.status_code != 200:
                return False
            try:
                body = response.json()
            except ValueError:
                return False
            return body.get("id") == fixture["user_id"] and body.get("email") == fixture["email"]

    matches = await asyncio.gather(*(check(fixture) for fixture in fixtures))
    if not all(matches):
        raise RuntimeError(f"Identity preflight failed for {len(matches) - sum(matches)} fixture accounts")


async def monitor_stage(steady_samples: list[tuple[int, float, bool]], max_p95_ms: float,
                        deadline: float, stop: asyncio.Event, latency_abort: list[str]) -> None:
    while not stop.is_set() and time.monotonic() < deadline:
        await asyncio.sleep(min(2, max(0, deadline - time.monotonic())))
        latencies = [sample[1] for sample in steady_samples]
        if len(latencies) >= 20 and percentile(latencies, 0.95) > max_p95_ms:
            latency_abort.append("interim_steady_p95_breach")
            stop.set()
            return


async def monitor_resources(baseline: dict, deadline: float, stop: asyncio.Event,
                            resource_abort: list[str]) -> None:
    while not stop.is_set() and time.monotonic() < deadline:
        await asyncio.sleep(min(2, max(0, deadline - time.monotonic())))
        try:
            snapshot = await asyncio.wait_for(asyncio.to_thread(resource_snapshot), timeout=5)
            reason = resource_stop_reason(snapshot, baseline)
        except Exception:
            reason = "resource_monitor_unavailable"
        if reason:
            resource_abort.append(reason)
            stop.set()
            return


async def stage(client: httpx.AsyncClient, fixtures: list[dict], seconds: int,
                think_seconds: float, max_p95_ms: float, timeout: float,
                baseline: dict) -> dict:
    stop = asyncio.Event()
    started = time.monotonic()
    steady_at = started + think_seconds
    deadline = steady_at + seconds
    all_samples: list[tuple[int, float, bool]] = []
    steady_samples: list[tuple[int, float, bool]] = []
    latency_abort: list[str] = []
    resource_abort: list[str] = []

    async def user(fixture: dict) -> None:
        rng = random.Random(fixture["user_id"])
        try:
            await asyncio.wait_for(stop.wait(), timeout=rng.uniform(0, think_seconds))
        except asyncio.TimeoutError:
            pass
        headers = {"Authorization": f"Bearer {fixture['access_token']}"}
        while time.monotonic() < deadline and not stop.is_set():
            request_start = time.monotonic()
            try:
                response = await asyncio.wait_for(
                    client.get("/api/bot/trade-reviews?limit=20", headers=headers), timeout=timeout,
                )
                status = response.status_code
                valid = enabled_empty_review(response)
            except (asyncio.TimeoutError, httpx.HTTPError):
                status, valid = 0, False
            sample = (status, (time.monotonic() - request_start) * 1000, valid)
            all_samples.append(sample)
            if request_start >= steady_at:
                steady_samples.append(sample)
            if not valid:
                stop.set()
                return
            try:
                await asyncio.wait_for(stop.wait(), timeout=rng.uniform(
                    think_seconds * 0.5, think_seconds * 1.5,
                ))
            except asyncio.TimeoutError:
                pass

    watcher = asyncio.create_task(monitor_stage(
        steady_samples, max_p95_ms, deadline, stop, latency_abort,
    ))
    resource_watcher = asyncio.create_task(monitor_resources(baseline, deadline, stop, resource_abort))
    try:
        await asyncio.gather(*(user(fixture) for fixture in fixtures))
    finally:
        watcher.cancel()
        resource_watcher.cancel()
        await asyncio.gather(watcher, resource_watcher, return_exceptions=True)
    summary = {
        "users": len(fixtures), "steady_seconds_observed": round(max(0, time.monotonic() - steady_at), 2),
        "all_requests": len(all_samples),
        "steady_requests": len(steady_samples),
        "statuses": dict(Counter(str(item[0]) for item in all_samples)),
        "enabled_valid_responses": sum(item[2] for item in all_samples),
        "steady_p95_ms": percentile([item[1] for item in steady_samples], 0.95),
        "steady_max_ms": round(max((item[1] for item in steady_samples), default=0), 2),
        "abort_reason": (latency_abort or resource_abort or [None])[0],
    }
    print(json.dumps({"review_stage": summary}, sort_keys=True), flush=True)
    if (latency_abort or resource_abort or len(steady_samples) < len(fixtures)
            or len(all_samples) != summary["enabled_valid_responses"]
            or summary["steady_p95_ms"] is None or summary["steady_p95_ms"] > max_p95_ms
            or time.monotonic() < deadline):
        raise RuntimeError("Enabled trade-review stage failed; refusing escalation")
    return summary


async def run(fixtures: list[dict], stages: list[tuple[int, int]], think_seconds: float,
              max_p95_ms: float, timeout: float) -> None:
    from backend.main import app

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    try:
        with process_local_review_rollout():
            async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1",
                                         timeout=timeout) as client:
                for index, (users, seconds) in enumerate(stages):
                    baseline = await asyncio.wait_for(asyncio.to_thread(resource_snapshot), timeout=5)
                    required_free = 20 + diagnostic_possible_new_connections()
                    reason = resource_stop_reason(baseline, baseline, minimum_db_free=required_free)
                    print(json.dumps({"review_resource_preflight": {
                        "users": users, "db_free": baseline["db_free"],
                        "db_free_required": required_free,
                        "mem_available_mib": baseline["mem_available_mib"],
                        "queue_depths": {name: item["depth"] for name, item in baseline["queues"].items()},
                        "stop_reason": reason,
                    }}, sort_keys=True), flush=True)
                    if reason:
                        raise RuntimeError(f"Resource preflight refused stage: {reason}")
                    await identity_preflight(client, fixtures[:users], timeout)
                    await stage(client, fixtures[:users], seconds, think_seconds, max_p95_ms, timeout, baseline)
                    if index + 1 < len(stages):
                        answer = await asyncio.to_thread(input, "Inspect host and DB; type CONTINUE: ")
                        if answer.strip() != "CONTINUE":
                            raise RuntimeError("Operator declined the next stage")
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", required=True, type=Path)
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--expected-db-host", required=True)
    parser.add_argument("--expected-db-port", required=True)
    parser.add_argument("--expected-db-name", required=True)
    parser.add_argument("--stages", default="100:60,500:60,1000:120")
    parser.add_argument("--think-seconds", type=float, default=10.0)
    parser.add_argument("--max-p95-ms", type=float, required=True)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--allow-production", action="store_true")
    parser.add_argument("--allow-process-local-rollout", action="store_true")
    args = parser.parse_args()
    if not CAMPAIGN_RE.fullmatch(args.campaign):
        parser.error("Campaign must be a 3-32 character lowercase slug")
    if (args.expected_db_host, args.expected_db_port, args.expected_db_name) != (db_host, db_port, db_name):
        parser.error("Configured database target does not match expected host, port and name")
    if not args.allow_production or not args.allow_process_local_rollout:
        parser.error("Explicit production and process-local rollout flags are required")
    if os.getenv("APP_ENV") != "production" or os.getenv("TRADAMIND_BUILD_SERVICE") != "backend":
        parser.error("Production diagnostic requires APP_ENV=production and TRADAMIND_BUILD_SERVICE=backend")
    if (not math.isfinite(args.think_seconds) or args.think_seconds < 1
            or not math.isfinite(args.max_p95_ms) or args.max_p95_ms <= 0
            or not math.isfinite(args.timeout) or args.timeout <= 0):
        parser.error("Think time, p95 limit and timeout must be finite positive values")
    try:
        stages = [tuple(map(int, part.split(":"))) for part in args.stages.split(",")]
    except ValueError:
        parser.error("Stages must use users:seconds pairs")
    if not stages or any(len(item) != 2 or item[0] < 1 or item[1] < 30 for item in stages):
        parser.error("Each stage needs users and at least 30 seconds")
    if any(stages[index][0] >= stages[index + 1][0] for index in range(len(stages) - 1)):
        parser.error("Stage user counts must strictly increase")
    if len(stages) > 1 and not os.isatty(0):
        parser.error("Multi-stage production load requires an interactive operator terminal")
    try:
        fixtures = private_fixtures(args.fixtures, args.campaign)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if stages[-1][0] > len(fixtures):
        parser.error("Provide a distinct fixture for every user in the largest stage")
    asyncio.run(run(fixtures, stages, args.think_seconds, args.max_p95_ms, args.timeout))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
