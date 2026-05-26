import collections
import time
from typing import Optional

from fastapi import HTTPException, Request


class InMemoryRateLimiter:
    def __init__(self, requests_limit: int, window_seconds: int):
        self.requests_limit = requests_limit
        self.window_seconds = window_seconds
        self.history = collections.defaultdict(list)

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


def client_ip(raw_request: Request) -> str:
    forwarded = raw_request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",", 1)[0].strip()
        if first:
            return first
    real_ip = raw_request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return raw_request.client.host if raw_request.client else "unknown"
