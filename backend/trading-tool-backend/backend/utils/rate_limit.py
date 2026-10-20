import collections
import hashlib
import ipaddress
import os
import time
from typing import Optional

from fastapi import HTTPException, Request


class InMemoryRateLimiter:
    def __init__(self, requests_limit: int, window_seconds: int):
        self.requests_limit = requests_limit
        self.window_seconds = window_seconds
        self.history = collections.defaultdict(list)
        self._checks = 0
        self._retention_seconds = window_seconds

    def check_rate_limit(
        self,
        identifier: str,
        *,
        limit: Optional[int] = None,
        window_seconds: Optional[int] = None,
        detail: str = "Te veel verzoeken. Wacht kort en probeer opnieuw.",
    ) -> None:
        now = time.time()
        active_limit = limit or self.requests_limit
        active_window = window_seconds or self.window_seconds
        self._retention_seconds = max(self._retention_seconds, active_window)
        self._checks += 1
        if self._checks % 256 == 0:
            self.history = collections.defaultdict(
                list,
                {key: timestamps for key, timestamps in self.history.items()
                 if timestamps and now - timestamps[-1] < self._retention_seconds},
            )
        self.history[identifier] = [t for t in self.history[identifier] if now - t < active_window]
        if len(self.history[identifier]) >= active_limit:
            retry_after = (
                max(1, int(active_window - (now - self.history[identifier][0])))
                if self.history[identifier]
                else active_window
            )
            raise HTTPException(
                status_code=429,
                detail=detail,
                headers={"Retry-After": str(retry_after)},
            )
        self.history[identifier].append(now)


class SharedRateLimiter:
    """Atomic, expiring rate buckets shared by all API processes."""

    _INCREMENT_SCRIPT = """
    local count = redis.call('INCR', KEYS[1])
    if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
    return {count, redis.call('TTL', KEYS[1])}
    """

    def __init__(self, requests_limit: int, window_seconds: int, namespace: str):
        self.requests_limit = requests_limit
        self.window_seconds = window_seconds
        self.namespace = namespace
        self._client = None
        self._local = InMemoryRateLimiter(requests_limit, window_seconds)

    def _redis(self):
        if self._client is None:
            import redis

            url = os.getenv("REDIS_URL") or os.getenv("CELERY_BROKER_URL")
            if not url:
                raise RuntimeError("Shared rate limiting requires REDIS_URL or CELERY_BROKER_URL")
            self._client = redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
        return self._client

    def check_rate_limit(
        self,
        identifier: str,
        *,
        limit: Optional[int] = None,
        window_seconds: Optional[int] = None,
        detail: str = "Te veel verzoeken. Wacht kort en probeer opnieuw.",
    ) -> None:
        active_limit = self.requests_limit if limit is None else max(1, int(limit))
        active_window = self.window_seconds if window_seconds is None else max(1, int(window_seconds))
        if os.getenv("APP_ENV", "development").lower() not in {"production", "staging"}:
            self._local.check_rate_limit(identifier, limit=active_limit, window_seconds=active_window, detail=detail)
            return
        digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
        bucket = int(time.time()) // active_window
        environment = os.getenv("APP_ENV", "development").lower()
        key = f"rate-limit:{environment}:{self.namespace}:{digest}:{active_window}:{bucket}"
        try:
            count, ttl = self._redis().eval(self._INCREMENT_SCRIPT, 1, key, active_window + 1)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Verzoek tijdelijk niet beschikbaar; probeer opnieuw.") from exc
        if int(count) > active_limit:
            raise HTTPException(
                status_code=429,
                detail=detail,
                headers={"Retry-After": str(max(1, int(ttl)))},
            )


def client_ip(raw_request: Request) -> str:
    peer = raw_request.client.host if raw_request.client else "unknown"
    trusted_raw = os.getenv("TRUSTED_PROXY_CIDRS", "127.0.0.1/32,::1/128")
    try:
        trusted = [ipaddress.ip_network(item.strip(), strict=False) for item in trusted_raw.split(",") if item.strip()]
        if not any(ipaddress.ip_address(peer) in network for network in trusted):
            return peer
    except ValueError:
        return peer
    forwarded = raw_request.headers.get("x-forwarded-for")
    if forwarded:
        # nginx appends its direct peer; client-supplied entries to the left are untrusted.
        for candidate in reversed([item.strip() for item in forwarded.split(",")]):
            try:
                address = ipaddress.ip_address(candidate)
            except ValueError:
                continue
            if not any(address in network for network in trusted):
                return candidate
    return peer
