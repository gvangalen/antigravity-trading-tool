import asyncio
from backend.services import chart_candle_cache_service as service


class _FakeRedis:
    def __init__(self):
        self.items = {}

    async def get(self, key):
        return self.items.get(key)

    async def set(self, key, value, *, nx=False, ex=None):
        if nx and key in self.items:
            return False
        self.items[key] = value
        return True

    async def eval(self, _script, _count, key, token):
        if self.items.get(key) == token:
            del self.items[key]
            return 1
        return 0


def test_chart_candles_reuse_shared_cache_per_verified_identity(monkeypatch):
    redis = _FakeRedis()
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(service, "_redis_client", lambda: redis)
    monkeypatch.setattr(service._provider_minute, "check_rate_limit", lambda _key: None)
    monkeypatch.setattr(service._provider_day, "check_rate_limit", lambda _key: None)
    calls = []

    async def fetch():
        calls.append(1)
        return {"candles": [{"close": 101}]}

    async def check():
        first = await service.cached_chart_candles("binance:SOLEUR:D", "crypto", "binance", fetch)
        second = await service.cached_chart_candles("binance:SOLEUR:D", "crypto", "binance", fetch)
        other = await service.cached_chart_candles("binance:SOLUSDT:D", "crypto", "binance", fetch)
        assert first == second == other

    asyncio.run(check())
    assert len(calls) == 2
