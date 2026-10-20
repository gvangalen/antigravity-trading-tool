import pytest
from fastapi import HTTPException

from backend.utils.rate_limit import SharedRateLimiter


def test_shared_limiter_counts_across_instances_and_expires_keys(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr("backend.utils.rate_limit.time.time", lambda: 120.0)

    class FakeRedis:
        def __init__(self):
            self.counts = {}
            self.ttls = {}

        def eval(self, script, key_count, key, ttl):
            assert key_count == 1
            assert "EXPIRE" in script
            self.counts[key] = self.counts.get(key, 0) + 1
            self.ttls[key] = ttl
            return [self.counts[key], ttl]

    redis = FakeRedis()
    first = SharedRateLimiter(1, 60, "login")
    second = SharedRateLimiter(1, 60, "login")
    first._client = second._client = redis

    first.check_rate_limit("user@example.com")
    with pytest.raises(HTTPException) as exc:
        second.check_rate_limit("user@example.com")

    assert exc.value.status_code == 429
    assert int(exc.value.headers["Retry-After"]) > 0
    assert len(redis.counts) == 1
    assert "user@example.com" not in next(iter(redis.counts))


def test_shared_limiter_fails_closed_when_redis_is_unavailable(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    limiter = SharedRateLimiter(1, 60, "orders")

    class BrokenRedis:
        def eval(self, *_args):
            raise ConnectionError("down")

    limiter._client = BrokenRedis()
    with pytest.raises(HTTPException) as exc:
        limiter.check_rate_limit("user:1")
    assert exc.value.status_code == 503
