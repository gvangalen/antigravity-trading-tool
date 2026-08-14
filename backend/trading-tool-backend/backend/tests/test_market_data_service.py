import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException

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


def test_get_latest_market_snapshot_falls_back_to_live_provider_when_db_snapshot_is_missing(monkeypatch):
    service = MarketDataService(AsyncMock())
    service.repository.get_latest_snapshot = AsyncMock(return_value=None)

    asset_meta = {
        "symbol": "AAPL",
        "display_name": "Apple Inc.",
        "asset_class": "stock",
        "provider": "twelve_data",
        "primary_provider": "twelve_data",
        "provider_symbol": "AAPL",
        "exchange": "NASDAQ",
        "market_region": "us",
        "timezone": "America/New_York",
        "base_currency": None,
        "quote_currency": "USD",
        "entitlement_tier": "internal",
        "is_delayed": False,
        "refresh_policy": "securities_live_5m",
        "metadata": {},
    }

    class _AssetCatalogStub:
        def __init__(self, _session):
            self._session = _session

        async def get_asset(self, symbol):
            assert symbol == "AAPL"
            return asset_meta

    live_snapshot = SimpleNamespace(
        price=313.30,
        open=311.45,
        high=314.81,
        low=310.74,
        change_percent=-0.11,
        volume=34_430_000,
        observed_at=None,
    )
    provider = AsyncMock()
    provider.fetch_latest_snapshot = AsyncMock(return_value=live_snapshot)
    service.provider_registry.resolve_for_asset = lambda _asset: provider

    monkeypatch.setattr("backend.services.market_data_service.AssetCatalogService", _AssetCatalogStub)

    result = asyncio.run(service.get_latest_market_snapshot("AAPL"))

    assert result.symbol == "AAPL"
    assert result.id == 0
    assert result.price == 313.30
    assert result.change_24h == -0.11
    assert result.volume == 34_430_000


def test_get_latest_market_snapshot_raises_404_when_provider_fallback_fails(monkeypatch):
    service = MarketDataService(AsyncMock())
    service.repository.get_latest_snapshot = AsyncMock(return_value=None)

    asset_meta = {
        "symbol": "SPY",
        "display_name": "SPDR S&P 500 ETF Trust",
        "asset_class": "etf",
        "provider": "twelve_data",
        "primary_provider": "twelve_data",
        "provider_symbol": "SPY",
        "exchange": "AMEX",
        "market_region": "us",
        "timezone": "America/New_York",
        "base_currency": None,
        "quote_currency": "USD",
        "entitlement_tier": "internal",
        "is_delayed": False,
        "refresh_policy": "securities_live_5m",
        "metadata": {},
    }

    class _AssetCatalogStub:
        def __init__(self, _session):
            self._session = _session

        async def get_asset(self, symbol):
            assert symbol == "SPY"
            return asset_meta

    provider = AsyncMock()
    provider.fetch_latest_snapshot = AsyncMock(side_effect=RuntimeError("provider down"))
    service.provider_registry.resolve_for_asset = lambda _asset: provider

    monkeypatch.setattr("backend.services.market_data_service.AssetCatalogService", _AssetCatalogStub)

    try:
        asyncio.run(service.get_latest_market_snapshot("SPY"))
    except HTTPException as exc:
        assert exc.status_code == 404
        assert "SPY" in str(exc.detail)
    else:
        raise AssertionError("Expected HTTPException for failed provider fallback")


def test_resolve_effective_preferences_returns_empty_without_user_scope_rows():
    service = MarketDataService(AsyncMock())
    service.preference_repository = SimpleNamespace(
        list_scope_configs=AsyncMock(return_value=[]),
    )

    async def fake_get_asset(_symbol):
        return {"asset_class": "crypto"}

    async def run():
        from unittest.mock import patch

        with patch("backend.services.market_data_service.AssetCatalogService") as asset_catalog_cls:
            asset_catalog_cls.return_value.get_asset = AsyncMock(side_effect=fake_get_asset)
            return await service.resolve_effective_preferences(7, symbol="BTC")

    result = asyncio.run(run())

    assert result["scope"] == "empty"
    assert result["symbol"] == "BTC"
    assert result["asset_class"] == "crypto"
    assert result["rows"] == []


def test_bootstrap_preferences_clears_scope_instead_of_creating_defaults():
    service = MarketDataService(AsyncMock())
    service.preference_repository = SimpleNamespace(
        replace_scope_configs=AsyncMock(return_value=[]),
    )

    async def fake_get_asset(_symbol):
        return {"asset_class": "crypto"}

    async def run():
        from unittest.mock import patch

        with patch("backend.services.market_data_service.AssetCatalogService") as asset_catalog_cls:
            asset_catalog_cls.return_value.get_asset = AsyncMock(side_effect=fake_get_asset)
            return await service.bootstrap_preferences(7, symbol="BTC", scope="symbol")

    result = asyncio.run(run())

    service.preference_repository.replace_scope_configs.assert_awaited_once_with(
        7,
        [],
        category="market",
        symbol="BTC",
        asset_class="crypto",
    )
    assert result["rows"] == []
