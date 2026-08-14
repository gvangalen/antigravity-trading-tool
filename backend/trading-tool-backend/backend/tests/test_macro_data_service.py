import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.domain.macro_indicator_catalog import get_active_macro_indicator_definitions
from backend.services.macro_data_service import MacroDataService


def test_add_macro_indicator_normalizes_name_before_scoring_and_preference_save():
    service = MacroDataService(AsyncMock())
    service.preference_repository = SimpleNamespace(
        ensure_user_config=AsyncMock(),
    )
    service.repository = SimpleNamespace(
        check_indicator_exists=AsyncMock(return_value=False),
        get_indicator_info=AsyncMock(return_value=SimpleNamespace(source="manual", link="test://fear-greed")),
        add_macro_data=AsyncMock(),
    )
    service._mark_onboarding = AsyncMock()
    service._sync_score_indicator = lambda category, indicator, value, user_id: {
        "score": 55,
        "trend": "neutral",
        "interpretation": "ok",
        "action": "hold",
    }

    async def fake_get_asset(_symbol):
        return {"asset_class": "crypto"}

    async def run():
        from unittest.mock import patch

        with patch("backend.services.macro_data_service.AssetCatalogService") as asset_catalog_cls:
            asset_catalog_cls.return_value.get_asset = AsyncMock(side_effect=fake_get_asset)
            return await service.add_macro_indicator(
                7,
                "Fear Greed Index",
                42.0,
                symbol="BTC",
            )

    result = asyncio.run(run())

    service.preference_repository.ensure_user_config.assert_awaited_once_with(
        7,
        "fear_greed_index",
        category="macro",
        symbol="BTC",
        asset_class="crypto",
    )
    assert result.score == 55
    assert result.message == "Indicator 'Fear Greed Index' opgeslagen."


def test_get_all_macro_indicators_merges_canonical_catalog_with_db_rows():
    service = MacroDataService(AsyncMock())
    service.repository = SimpleNamespace(
        get_global_indicators=AsyncMock(
            return_value=[
                SimpleNamespace(name="sp500", display_name="S&P 500 Index"),
                SimpleNamespace(name="fear_greed_index", display_name="Fear & Greed Index"),
            ]
        )
    )

    async def run():
        return await service.get_all_macro_indicators()

    rows = asyncio.run(run())
    names = {row.name for row in rows}

    assert "sp500" in names
    assert "fear_greed_index" in names
    assert "gold_price" in names
    assert "us10y" in names
    assert "us02y" in names
    assert "etf_bitcoin_inflow" in names
    assert "google_trends" not in names


def test_add_macro_indicator_uses_canonical_macro_source_when_db_row_is_stale():
    service = MacroDataService(AsyncMock())
    service.preference_repository = SimpleNamespace(
        ensure_user_config=AsyncMock(),
    )
    service.repository = SimpleNamespace(
        check_indicator_exists=AsyncMock(return_value=False),
        get_indicator_info=AsyncMock(
            return_value=SimpleNamespace(
                name="sp500",
                source="legacy",
                link="https://stale.example/sp500",
                display_name="Old S&P 500",
            )
        ),
        add_macro_data=AsyncMock(),
    )
    service._mark_onboarding = AsyncMock()
    service._sync_score_indicator = lambda category, indicator, value, user_id: {
        "score": 80,
        "trend": "bullish",
        "interpretation": "ok",
        "action": "risk-on",
    }

    fetch_calls = []

    def fake_fetch(indicator_name, source, link):
        fetch_calls.append((indicator_name, source, link))
        return {"value": 7733.85}

    service._sync_fetch_macro_value = fake_fetch

    async def fake_get_asset(_symbol):
        return {"asset_class": "crypto"}

    async def run():
        from unittest.mock import patch

        with patch("backend.services.macro_data_service.AssetCatalogService") as asset_catalog_cls:
            asset_catalog_cls.return_value.get_asset = AsyncMock(side_effect=fake_get_asset)
            return await service.add_macro_indicator(
                7,
                "sp500",
                None,
                symbol="BTC",
            )

    result = asyncio.run(run())

    assert fetch_calls == [("sp500", "fred", "fred:SP500")]
    assert result.value == 7733.85


def test_all_active_macro_indicators_resolve_to_catalog_definition_when_db_row_is_stale():
    service = MacroDataService(AsyncMock())

    stale_db_row = SimpleNamespace(
        source="legacy",
        link="https://stale.example/indicator",
        display_name="Stale row",
    )

    for definition in get_active_macro_indicator_definitions():
        resolved = service._resolve_indicator_info(definition["name"], stale_db_row)

        assert resolved is not None
        assert resolved.name == definition["name"]
        assert resolved.source == definition["source"]
        assert resolved.link == definition["link"]
        assert resolved.category == "macro"


def test_resolve_effective_preferences_returns_empty_without_user_scope_rows():
    service = MacroDataService(AsyncMock())
    service.preference_repository = SimpleNamespace(
        list_scope_configs=AsyncMock(return_value=[]),
    )

    async def fake_get_asset(_symbol):
        return {"asset_class": "crypto"}

    async def run():
        from unittest.mock import patch

        with patch("backend.services.macro_data_service.AssetCatalogService") as asset_catalog_cls:
            asset_catalog_cls.return_value.get_asset = AsyncMock(side_effect=fake_get_asset)
            return await service.resolve_effective_preferences(7, symbol="BTC")

    result = asyncio.run(run())

    assert result["scope"] == "empty"
    assert result["symbol"] == "BTC"
    assert result["asset_class"] == "crypto"
    assert result["rows"] == []


def test_bootstrap_preferences_clears_scope_instead_of_creating_defaults():
    service = MacroDataService(AsyncMock())
    service.preference_repository = SimpleNamespace(
        replace_scope_configs=AsyncMock(return_value=[]),
    )

    async def fake_get_asset(_symbol):
        return {"asset_class": "crypto"}

    async def run():
        from unittest.mock import patch

        with patch("backend.services.macro_data_service.AssetCatalogService") as asset_catalog_cls:
            asset_catalog_cls.return_value.get_asset = AsyncMock(side_effect=fake_get_asset)
            return await service.bootstrap_preferences(7, symbol="BTC", scope="symbol")

    result = asyncio.run(run())

    service.preference_repository.replace_scope_configs.assert_awaited_once_with(
        7,
        [],
        category="macro",
        symbol="BTC",
        asset_class="crypto",
    )
    assert result["rows"] == []
