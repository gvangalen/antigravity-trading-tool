import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services.technical_data_service import TechnicalDataService


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
        return {"value": 23.4}

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
