import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from backend.services.macro_data_service import MacroDataService
from backend.services.market_data_service import MarketDataService


@pytest.mark.parametrize("service_type,method_name,repository_method", [
    (MarketDataService, "delete_user_market_indicator", "delete_user_market_indicator"),
    (MacroDataService, "delete_macro_indicator", "delete_user_macro_indicator"),
])
def test_pending_asset_indicator_can_be_removed_without_source_row(
    service_type, method_name, repository_method,
):
    service = service_type.__new__(service_type)
    service.session = SimpleNamespace(commit=AsyncMock())
    service.preference_repository = SimpleNamespace(remove_user_config=AsyncMock(return_value=True))
    delete_row = AsyncMock(return_value=False)
    service.repository = SimpleNamespace(**{repository_method: delete_row})
    service._get_asset_scope = AsyncMock(return_value={"asset_class": "stock"})

    result = asyncio.run(getattr(service, method_name)("DXY", 17, symbol="AAPL"))

    assert result["rows_deleted"] == 0
    assert service.preference_repository.remove_user_config.await_args.kwargs["symbol"] == "AAPL"
    assert delete_row.await_args.kwargs["symbol"] == "AAPL"
    if service_type is MarketDataService:
        service.session.commit.assert_awaited_once()


@pytest.mark.parametrize("service_type,method_name,repository_method", [
    (MarketDataService, "delete_user_market_indicator", "delete_user_market_indicator"),
    (MacroDataService, "delete_macro_indicator", "delete_user_macro_indicator"),
])
def test_asset_indicator_removal_still_rejects_unknown_indicator(
    service_type, method_name, repository_method,
):
    service = service_type.__new__(service_type)
    service.session = SimpleNamespace(commit=AsyncMock())
    service.preference_repository = SimpleNamespace(remove_user_config=AsyncMock(return_value=False))
    service.repository = SimpleNamespace(**{repository_method: AsyncMock(return_value=False)})
    service._get_asset_scope = AsyncMock(return_value={"asset_class": "stock"})

    with pytest.raises(HTTPException) as error:
        asyncio.run(getattr(service, method_name)("DXY", 17, symbol="AAPL"))
    assert error.value.status_code == 404
