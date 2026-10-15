import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from backend.infrastructure.repositories.setup_repository import SetupRepository
from backend.schemas.bot_schema import BotManualOrderSchema
from backend.services.bot_service import BotService
from backend.services.setup_market_match_service import SetupMarketMatchService


def _payload(side="buy"):
    return BotManualOrderSchema(bot_id=9, symbol="BTC", side=side, quantity=1, price=100)


def _service(monkeypatch, *, setup, match_status="insufficient_data", match_components=None):
    service = BotService(AsyncMock())
    service.repository.get_bot_config = AsyncMock(return_value={
        "id": 9, "setup_id": 7, "strategy_id": 11,
        "symbol": "BTC", "is_live": False, "is_active": True,
    })
    service.repository.get_bot_ledger_stats = AsyncMock(return_value={})
    service.repository.get_asset_quote_currencies = AsyncMock(return_value={"BTC": "EUR"})
    service.repository.create_manual_order = AsyncMock()
    get_setup = AsyncMock(return_value=setup)
    for_asset = AsyncMock(return_value={
        "matches": [{"setup_id": 7, "status": match_status,
                     "components": match_components or {}}],
    })
    monkeypatch.setattr(SetupRepository, "get_setup_by_id", get_setup)
    monkeypatch.setattr(SetupMarketMatchService, "for_asset", for_asset)
    return service, get_setup, for_asset


@pytest.mark.parametrize("status", ["insufficient_data", "outside_conditions"])
def test_paper_preview_and_write_hold_when_saved_score_conditions_do_not_match(monkeypatch, status):
    service, get_setup, for_asset = _service(
        monkeypatch,
        setup={"id": 7, "symbol": "BTC", "min_macro_score": 30},
        match_status=status,
    )

    preview = asyncio.run(service.preview_manual_order(_payload(), user_id=3))
    assert preview["blocked"] is True
    assert preview["not_persisted"] is True
    assert preview["setup_match_status"] == status
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.create_manual_order(_payload(), user_id=3))
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "PAPER_SETUP_MATCH_REQUIRED"
    with pytest.raises(HTTPException) as preflight_exc:
        asyncio.run(service.preflight_manual_order(_payload(), user_id=3))
    assert preflight_exc.value.status_code == 409
    service.repository.create_manual_order.assert_not_awaited()
    get_setup.assert_awaited_with(7, 3)
    assert for_asset.await_count == 3


def test_outside_score_preview_explains_the_verified_boundary(monkeypatch):
    service, _, _ = _service(
        monkeypatch,
        setup={"id": 7, "symbol": "BTC", "min_macro_score": 30},
        match_status="outside_conditions",
        match_components={
            "macro": {"score": 20, "minimum": 30, "maximum": None, "within_range": False},
        },
    )

    preview = asyncio.run(service.preview_manual_order(_payload(), user_id=3))

    assert preview["ok"] is False and preview["blocked"] is True
    assert preview["symbol"] == "BTC" and preview["side"] == "buy"
    assert "Macro 20 ligt onder minimum 30" in preview["message"]


def test_matching_setup_allows_paper_buy_check(monkeypatch):
    service, _, _ = _service(
        monkeypatch,
        setup={"id": 7, "symbol": "BTC", "min_macro_score": 20},
        match_status="matches",
    )
    result = asyncio.run(service._paper_manual_buy_match(3, {
        "setup_id": 7, "is_live": False,
    }, _payload()))
    assert result == {"allowed": True, "status": "matches", "setup_id": 7}


def test_score_free_dca_and_sell_do_not_require_setup_match(monkeypatch):
    service, _, for_asset = _service(
        monkeypatch,
        setup={"id": 7, "symbol": "BTC", "setup_type": "dca"},
    )
    unbounded = asyncio.run(service._paper_manual_buy_match(3, {
        "setup_id": 7, "is_live": False,
    }, _payload()))
    sell = asyncio.run(service._paper_manual_buy_match(3, {
        "setup_id": 7, "is_live": False,
    }, _payload("sell")))
    assert unbounded["allowed"] is True
    assert sell["allowed"] is True
    for_asset.assert_not_awaited()


def test_unlinked_paper_buy_fails_closed(monkeypatch):
    service, _, _ = _service(monkeypatch, setup=None)
    result = asyncio.run(service._paper_manual_buy_match(3, {
        "setup_id": 7, "is_live": False,
    }, _payload()))
    assert result["allowed"] is False
    assert result["status"] == "unverified_setup"
