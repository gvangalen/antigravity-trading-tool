import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

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
