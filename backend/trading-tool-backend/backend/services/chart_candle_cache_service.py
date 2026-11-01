"""Shared, bounded provider access for the read-only chart fallback."""

import asyncio
import hashlib
import json
import os
import secrets
from functools import lru_cache

from fastapi import HTTPException

from backend.utils.rate_limit import SharedRateLimiter


_requests = SharedRateLimiter(30, 60, "chart-candles-user")
_provider_minute = SharedRateLimiter(20, 60, "chart-candles-provider-minute")
_provider_day = SharedRateLimiter(300, 86400, "chart-candles-provider-day")


@lru_cache(maxsize=1)
def _redis_client():
    import redis.asyncio as redis

    url = os.getenv("REDIS_URL") or os.getenv("CELERY_BROKER_URL")
    if not url:
        raise RuntimeError("Chart cache requires Redis in production")
    return redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)


def check_chart_request(user_id: int) -> None:
    _requests.check_rate_limit(str(user_id))


async def cached_chart_candles(identity: str, asset_class: str, provider_name: str, fetch):
    """Cache public candles by verified market identity; coalesce concurrent misses."""
    if os.getenv("APP_ENV", "development").lower() not in {"production", "staging"}:
        return await fetch()

    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    environment = os.getenv("APP_ENV", "production").lower()
    key = f"chart-candles:{environment}:v1:{digest}"
    lock_key = f"{key}:lock"
    try:
        client = _redis_client()
        cached = await client.get(key)
        if cached is not None:
            return json.loads(cached)

        # Only the lock holder may contact the provider. A concurrent request
        # waits for the shared result instead of creating a quota burst.
        lock_token = secrets.token_hex(16)
        acquired = await client.set(lock_key, lock_token, nx=True, ex=30)
        if not acquired:
            for _ in range(50):
                await asyncio.sleep(0.2)
                cached = await client.get(key)
                if cached is not None:
                    return json.loads(cached)
            raise HTTPException(503, "Grafiekgegevens worden opgehaald; probeer opnieuw.")

        try:
            _provider_minute.check_rate_limit(provider_name)
            _provider_day.check_rate_limit(provider_name)
            result = await fetch()
            ttl = 60 if asset_class == "crypto" else 300
            await client.set(key, json.dumps(result), ex=ttl)
            return result
        finally:
            await client.eval(
                "if redis.call('GET', KEYS[1]) == ARGV[1] then "
                "return redis.call('DEL', KEYS[1]) else return 0 end",
                1, lock_key, lock_token,
            )
    except HTTPException:
        raise
    except Exception as exc:
        # An unavailable shared cache must not turn into unlimited provider calls.
        raise HTTPException(503, "Grafiekgegevens tijdelijk niet beschikbaar.") from exc
