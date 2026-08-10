import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services.market_data_service import MarketDataService


def test_ensure_forward_returns_ready_deduplicates_concurrent_refreshes():
    service = MarketDataService(AsyncMock())
    service.get_forward_return_support = AsyncMock(
        return_value={"supported": True, "minimum_history_years": 5, "source": "twelve_data"}
    )
    service._forward_returns_need_refresh = AsyncMock(return_value=True)

    sync_calls = 0

    async def fake_sync(symbol):
        nonlocal sync_calls
        sync_calls += 1
        await asyncio.sleep(0.01)
        return {"status": "ok", "symbol": symbol}

    service.sync_symbol_forward_returns = fake_sync

    async def run():
        await asyncio.gather(
            service.ensure_forward_returns_ready("SPY"),
            service.ensure_forward_returns_ready("SPY"),
            service.ensure_forward_returns_ready("SPY"),
        )

    asyncio.run(run())

    assert sync_calls == 1


def test_ensure_forward_returns_ready_skips_sync_when_history_is_fresh():
    service = MarketDataService(AsyncMock())
    service.get_forward_return_support = AsyncMock(
        return_value={"supported": True, "minimum_history_years": 5, "source": "twelve_data"}
    )
    service._forward_returns_need_refresh = AsyncMock(return_value=False)
    service.sync_symbol_forward_returns = AsyncMock()

    result = asyncio.run(service.ensure_forward_returns_ready("AAPL"))

    assert result["supported"] is True
    service.sync_symbol_forward_returns.assert_not_called()
