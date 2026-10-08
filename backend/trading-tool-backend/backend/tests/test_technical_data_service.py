import asyncio
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services.technical_data_service import TechnicalDataService
from backend.services.providers.twelve_data_technical_indicator_adapter import TechnicalSourceRateLimited
from backend.api.technical_data_api import add_technical_indicator as add_technical_indicator_api


def test_crypto_rsi_reuses_distinct_completed_market_source_days():
    today = datetime.now(timezone.utc).date()
    rows = [
        (datetime.combine(today - timedelta(days=offset), time(23, 59, 59)),
         100.0 + (16 - offset))
        for offset in range(16, 0, -1)
    ]
    rows.append((rows[-1][0], 9999.0))  # newest saved row wins for that day
    rows.append((datetime.combine(today, time.min), 1.0))  # incomplete day is excluded by query
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: rows[:-1])))
    service = TechnicalDataService(session)

    reading = asyncio.run(service._rsi_from_dated_market_history("ETH"))

    assert reading is not None
    assert reading["observed_at"].date() == today - timedelta(days=1)
    assert 0 <= reading["value"] <= 100
    session.execute.assert_awaited_once()


def test_crypto_rsi_needs_fifteen_dated_days_before_local_calculation():
    today = datetime.now(timezone.utc).date()
    rows = [
        (datetime.combine(today - timedelta(days=offset), time(23, 59, 59)), 100.0 + offset)
        for offset in range(14, 0, -1)
    ]
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: rows)))

    assert asyncio.run(TechnicalDataService(session)._rsi_from_dated_market_history("ETH")) is None


def test_crypto_rsi_prefers_verified_market_history_over_new_provider_call(monkeypatch):
    service = TechnicalDataService(AsyncMock())
    service._rsi_from_dated_market_history = AsyncMock(return_value={
        "value": 54.0, "observed_at": datetime.now(timezone.utc),
    })
    service.provider_registry = SimpleNamespace(resolve_for_asset=lambda *_: (
        _ for _ in ()).throw(AssertionError("provider must not be called"))
    )

    class _Catalog:
        def __init__(self, _session):
            pass

        async def get_asset(self, _symbol):
            return {"symbol": "ETH", "display_name": "Ethereum", "asset_class": "crypto"}

    monkeypatch.setattr("backend.services.technical_data_service.AssetCatalogService", _Catalog)

    reading = asyncio.run(service._fetch_indicator_value(
        name="rsi", source="twelve_data", link="twelve_data:rsi", symbol="ETH",
    ))

    assert reading["value"] == 54.0
    service._rsi_from_dated_market_history.assert_awaited_once_with("ETH")


def test_get_all_technical_indicators_merges_canonical_catalog_with_db_rows():
    service = TechnicalDataService(AsyncMock())
    service.repository = SimpleNamespace(
        get_all_indicators=AsyncMock(
            return_value=[
                {"name": "rsi", "display_name": "RSI"},
                {"name": "legacy_indicator", "display_name": "Legacy Indicator"},
            ]
        )
    )

    async def run():
        return await service.get_all_indicators()

    rows = asyncio.run(run())
    names = {row["name"] for row in rows}

    assert "rsi" in names
    assert "ma_50" in names
    assert "ma_200" in names
    assert "ema_20_gap_pct" in names
    assert "ema_50_gap_pct" in names
    assert "macd_hist_pct" in names
    assert "atr_pct" in names
    assert "adx" in names
    assert "legacy_indicator" in names


def test_add_technical_indicator_uses_canonical_twelve_data_config_when_db_row_is_stale():
    service = TechnicalDataService(AsyncMock())
    service.repository = SimpleNamespace(
        ensure_user_config=AsyncMock(),
        get_indicator_config=AsyncMock(
            return_value=SimpleNamespace(
                name="adx",
                source="legacy",
                link="https://stale.example/adx",
                display_name="Old ADX",
                active=True,
            )
        ),
        add_indicator=AsyncMock(
            return_value=SimpleNamespace(
                id=17,
                value=23.4,
                score=61.0,
                advies="constructief",
                uitleg="ok",
            )
        ),
    )
    service._score_indicator_with_fallback = lambda **_: {
        "score": 61,
        "trend": "constructief",
        "interpretation": "ok",
        "action": "watch",
    }

    fetch_calls = []

    async def fake_fetch_indicator_value(**kwargs):
        fetch_calls.append(kwargs)
        return {"value": 23.4, "observed_at": datetime(2026, 10, 2)}

    service._fetch_indicator_value = fake_fetch_indicator_value

    async def fake_get_asset(_symbol):
        return {"asset_class": "crypto"}

    async def run():
        from unittest.mock import patch

        with patch("backend.services.technical_data_service.AssetCatalogService") as asset_catalog_cls, patch(
            "backend.services.technical_data_service.mark_step_completed",
            AsyncMock(),
        ):
            asset_catalog_cls.return_value.get_asset = AsyncMock(side_effect=fake_get_asset)
            return await service.add_technical_indicator("ADX", 7, symbol="BTC")

    result = asyncio.run(run())

    service.repository.ensure_user_config.assert_awaited_once_with(
        7,
        "adx",
        symbol="BTC",
        asset_class="crypto",
    )
    assert fetch_calls == [
        {
            "name": "adx",
            "source": "twelve_data",
            "link": "twelve_data:adx",
            "symbol": "BTC",
        }
    ]
    assert result["id"] == 17
    assert result["score"] == 61.0
    assert service.repository.add_indicator.await_args.kwargs["observed_at"] == datetime(2026, 10, 2)


def test_rate_limited_user_add_keeps_configuration_without_inventing_a_score():
    service = TechnicalDataService(AsyncMock())
    service.repository = SimpleNamespace(
        ensure_user_config=AsyncMock(),
        get_indicator_config=AsyncMock(return_value=None),
        add_indicator=AsyncMock(),
    )
    service._get_asset_scope = AsyncMock(return_value={"asset_class": "stock"})
    service._fetch_indicator_value = AsyncMock(side_effect=TechnicalSourceRateLimited())

    result = asyncio.run(service.add_technical_indicator("MA 200", 7, symbol="AAPL"))

    assert result["status"] == "pending_source"
    assert result["value"] is None
    assert result["score"] is None
    service.repository.ensure_user_config.assert_awaited_once_with(
        7, "ma_200", symbol="AAPL", asset_class="stock",
    )
    service.repository.add_indicator.assert_not_awaited()


def test_rate_limited_refresh_remains_a_failed_read():
    service = TechnicalDataService(AsyncMock())
    service.repository = SimpleNamespace(
        get_indicator_config=AsyncMock(return_value=None),
        add_indicator=AsyncMock(),
    )
    service._get_asset_scope = AsyncMock(return_value={"asset_class": "stock"})
    service._fetch_indicator_value = AsyncMock(side_effect=TechnicalSourceRateLimited())

    try:
        asyncio.run(service._add_technical_indicator(
            "MA 200", 7, symbol="AAPL", persist_preference=False,
        ))
    except TechnicalSourceRateLimited:
        pass
    else:
        raise AssertionError("A refresh must not report a rate-limited read as synced")

    service.repository.add_indicator.assert_not_awaited()


def test_rate_limited_add_api_commits_pending_configuration():
    from unittest.mock import patch

    session = AsyncMock()
    request = SimpleNamespace(json=AsyncMock(return_value={
        "indicator": "MA 200", "symbol": "AAPL",
    }))
    service = SimpleNamespace(add_technical_indicator=AsyncMock(return_value={
        "status": "pending_source", "indicator": "ma_200", "score": None,
    }))

    async def run():
        with patch("backend.api.technical_data_api.TechnicalDataService", return_value=service):
            return await add_technical_indicator_api(
                request, current_user={"id": 7}, session=session,
            )

    result = asyncio.run(run())
    assert result["status"] == "pending_source"
    assert result["score"] is None
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


def test_resolve_effective_preferences_returns_empty_without_user_scope_rows():
    service = TechnicalDataService(AsyncMock())
    service.repository = SimpleNamespace(
        list_scope_configs=AsyncMock(return_value=[]),
    )

    async def fake_get_asset(_symbol):
        return {"asset_class": "crypto"}

    async def run():
        from unittest.mock import patch

        with patch("backend.services.technical_data_service.AssetCatalogService") as asset_catalog_cls:
            asset_catalog_cls.return_value.get_asset = AsyncMock(side_effect=fake_get_asset)
            return await service.resolve_effective_preferences(7, symbol="BTC")

    result = asyncio.run(run())

    assert result["scope"] == "empty"
    assert result["symbol"] == "BTC"
    assert result["asset_class"] == "crypto"
    assert result["rows"] == []


def test_bootstrap_preferences_clears_scope_instead_of_creating_defaults():
    service = TechnicalDataService(AsyncMock())
    service.repository = SimpleNamespace(
        replace_scope_configs=AsyncMock(return_value=[]),
    )

    async def fake_get_asset(_symbol):
        return {"asset_class": "crypto"}

    async def run():
        from unittest.mock import patch

        with patch("backend.services.technical_data_service.AssetCatalogService") as asset_catalog_cls:
            asset_catalog_cls.return_value.get_asset = AsyncMock(side_effect=fake_get_asset)
            return await service.bootstrap_preferences(7, symbol="BTC", scope="symbol")

    result = asyncio.run(run())

    service.repository.replace_scope_configs.assert_awaited_once_with(
        7,
        [],
        symbol="BTC",
        asset_class="crypto",
    )
    assert result["rows"] == []


def test_add_technical_indicator_uses_isolated_asset_scope_lookup(monkeypatch):
    outer_session = AsyncMock(name="outer_session")
    isolated_session = AsyncMock(name="isolated_session")
    service = TechnicalDataService(outer_session)
    service.repository = SimpleNamespace(
        ensure_user_config=AsyncMock(),
        get_indicator_config=AsyncMock(
            return_value=SimpleNamespace(
                name="rsi",
                source="twelve_data",
                link="twelve_data:rsi",
                display_name="RSI",
                active=True,
            )
        ),
        add_indicator=AsyncMock(
            return_value=SimpleNamespace(
                id=9,
                value=54.0,
                score=62.0,
                advies="constructief",
                uitleg="ok",
            )
        ),
    )
    service._score_indicator_with_fallback = lambda **_: {
        "score": 62,
        "trend": "constructief",
        "interpretation": "ok",
        "action": "watch",
    }
    service._fetch_indicator_value = AsyncMock(return_value={"value": 54.0})

    class _FactoryContext:
        async def __aenter__(self):
            return isolated_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "backend.services.technical_data_service.async_session_factory",
        lambda: _FactoryContext(),
    )

    async def fake_get_asset(symbol):
        assert symbol == "BTC"
        return {"asset_class": "crypto"}

    async def run():
        from unittest.mock import patch

        with patch("backend.services.technical_data_service.AssetCatalogService") as asset_catalog_cls, patch(
            "backend.services.technical_data_service.mark_step_completed",
            AsyncMock(),
        ):
            asset_catalog_cls.return_value.get_asset = AsyncMock(side_effect=fake_get_asset)
            return await service.add_technical_indicator("RSI", 7, symbol="BTC")

    result = asyncio.run(run())

    assert result["id"] == 9
    service.repository.ensure_user_config.assert_awaited_once_with(
        7,
        "rsi",
        symbol="BTC",
        asset_class="crypto",
    )
    isolated_session.rollback.assert_awaited()
    outer_session.rollback.assert_not_awaited()


def test_technical_asset_scope_falls_back_when_isolated_session_factory_fails(monkeypatch):
    service = TechnicalDataService(AsyncMock())

    class _FailingFactoryContext:
        async def __aenter__(self):
            raise RuntimeError("factory boom")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "backend.services.technical_data_service.async_session_factory",
        lambda: _FailingFactoryContext(),
    )

    async def run():
        from unittest.mock import patch

        with patch("backend.services.technical_data_service.AssetCatalogService") as asset_catalog_cls:
            asset_catalog_cls.return_value._fallback_asset.return_value = {"asset_class": "crypto"}
            return await service._get_asset_scope("BTC")

    result = asyncio.run(run())

    assert result == {"asset_class": "crypto"}
