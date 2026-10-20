"""Authenticated mixed read load. Optional FINN chat is explicit and fixture-only.

Input JSON: [{"user_id": 1, "access_token": "..."}, ...]. Keep this file outside Git.
"""

import argparse
import asyncio
import json
import random
import time
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

import httpx


ROUTES = (
    ("workspace", "GET", "/api/workspace/asset?symbol=BTC&watchlist_symbols=BTC,ETH", 5),
    ("finn_conversations", "GET", "/api/assistant/v2/conversations", 2),
    ("trade_reviews", "GET", "/api/bot/trade-reviews?limit=20", 1),
)


def percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    return round(values[min(len(values) - 1, max(0, int(len(values) * fraction + 0.999999) - 1))], 2)


async def virtual_user(client, fixture, deadline, think_seconds, chat_budget, results):
    rng = random.Random(fixture["user_id"])
    headers = {"Authorization": f"Bearer {fixture['access_token']}"}
    choices = list(ROUTES)
    if chat_budget is not None:
        choices.append(("finn_chat", "POST", "/api/assistant/chat", 1))
    while time.monotonic() < deadline:
        name, method, path, _ = rng.choices(choices, weights=[item[3] for item in choices])[0]
        if name == "finn_chat":
            if chat_budget["remaining"] <= 0:
                name, method, path, _ = ROUTES[0]
            else:
                chat_budget["remaining"] -= 1
        started = time.perf_counter()
        try:
            response = await client.request(
                method, path, headers=headers,
                json={"query": "Explain the current BTC market context in general terms.",
                      "context": {"page": "load_fixture", "symbol": "BTC"}} if name == "finn_chat" else None,
            )
            status = response.status_code
        except httpx.HTTPError:
            status = 0
        results[name].append((status, (time.perf_counter() - started) * 1000))
        await asyncio.sleep(rng.uniform(think_seconds * 0.5, think_seconds * 1.5))


def report(label, results):
    summary = {}
    for name, samples in results.items():
        latencies = [duration for status, duration in samples if 200 <= status < 300]
        statuses = Counter(str(status) for status, _ in samples)
        summary[name] = {
            "requests": len(samples),
            "statuses": dict(statuses),
            "p50_ms": percentile(latencies, 0.50),
            "p95_ms": percentile(latencies, 0.95),
            "max_ms": round(max(latencies), 2) if latencies else None,
        }
    print(json.dumps({"stage": label, "routes": summary}, sort_keys=True), flush=True)


async def run(args, fixtures):
    limits = httpx.Limits(max_connections=max(100, args.max_users + 50), max_keepalive_connections=args.max_users)
    async with httpx.AsyncClient(base_url=args.base_url, timeout=args.timeout, limits=limits) as client:
        chat_budget = {"remaining": args.max_chat_requests} if args.include_chat else None
        for stage in args.stages.split(","):
            users_raw, seconds_raw = stage.split(":", 1)
            users, seconds = int(users_raw), int(seconds_raw)
            if users < 1 or users > len(fixtures) or seconds < 1:
                raise ValueError("Each stage needs positive duration and one distinct fixture per active user")
            results = defaultdict(list)
            deadline = time.monotonic() + seconds
            await asyncio.gather(*(
                virtual_user(client, fixture, deadline, args.think_seconds, chat_budget, results)
                for fixture in fixtures[:users]
            ))
            report(f"{users} users / {seconds}s", results)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--fixtures", required=True, type=Path)
    parser.add_argument("--stages", default="100:120,500:120,1000:300")
    parser.add_argument("--think-seconds", type=float, default=10.0)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--include-chat", action="store_true")
    parser.add_argument("--max-chat-requests", type=int, default=0)
    parser.add_argument("--allow-production", action="store_true")
    args = parser.parse_args()
    host = urlparse(args.base_url).hostname or ""
    if host in {"tradamind.com", "www.tradamind.com"} and not args.allow_production:
        parser.error("Production load requires --allow-production")
    if args.include_chat and args.max_chat_requests < 1:
        parser.error("FINN chat load requires --max-chat-requests with an explicit positive budget")
    fixtures = json.loads(args.fixtures.read_text())
    if not isinstance(fixtures, list) or not fixtures or any(
        not isinstance(item, dict) or not item.get("user_id") or not item.get("access_token")
        for item in fixtures
    ):
        parser.error("Fixture file must contain distinct user_id and access_token objects")
    if len({item["user_id"] for item in fixtures}) != len(fixtures):
        parser.error("Fixture user IDs must be unique")
    args.max_users = max(int(item.split(":", 1)[0]) for item in args.stages.split(","))
    if len(fixtures) < args.max_users:
        parser.error("Provide a distinct fixture for every user in the largest stage")
    asyncio.run(run(args, fixtures))


if __name__ == "__main__":
    main()
