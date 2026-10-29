import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services.pair_indicator_config_service import (
    PairIndicatorConfigService, effective_pair_configs,
)


def _config(market_id, indicator="rsi", enabled=True):
    return SimpleNamespace(user_id=7, symbol="BTC", market_id=market_id,
                           category="technical", indicator=indicator, enabled=enabled,
                           config_json={}, priority=100)


def test_pair_preference_overrides_base_without_changing_other_quote():
    base = _config(None)
    eur_disabled = _config(41, enabled=False)
    usdt = _config(42)
    assert effective_pair_configs([base, eur_disabled]) == {}
    assert effective_pair_configs([base, usdt])[(7, "technical", "rsi")] is usdt
    assert effective_pair_configs([base])[(7, "technical", "rsi")] is base


def test_same_indicator_is_allowed_on_second_pair_but_not_twice_on_same_pair():
    session = SimpleNamespace(add=lambda _row: None, commit=AsyncMock())
    service = PairIndicatorConfigService(session)
    eur = SimpleNamespace(id=41, asset_symbol="BTC", quote_currency="EUR")
    usdt = SimpleNamespace(id=42, asset_symbol="BTC", quote_currency="USDT")
    eur_row = _config(41)
    rows = {41: [eur_row], 42: [eur_row]}
    service.rows = AsyncMock(side_effect=lambda _owner, market: rows[market.id])
    service.base.repository.get_system_indicator_rules = AsyncMock(return_value=[
        SimpleNamespace(range_min=low, range_max=high)
        for low, high in ((0, 20), (20, 40), (40, 60), (60, 80), (80, 100))
    ])

    with pytest.raises(ValueError, match="indicator_already_configured_for_pair"):
        asyncio.run(service.save(7, eur, "technical", "rsi", mode="add",
                                 score_mode="standard", weight=1, rules=[]))

    result = asyncio.run(service.save(7, usdt, "technical", "rsi", mode="add",
                                      score_mode="standard", weight=2, rules=[]))
    assert result.market_id == 42
    assert result.config_json == {"score_mode": "standard", "weight": 2.0}
    assert eur_row.config_json == {}
    session.commit.assert_awaited_once()


def test_removing_one_pair_keeps_the_other_pair_selected():
    session = SimpleNamespace(add=lambda _row: None, commit=AsyncMock())
    service = PairIndicatorConfigService(session)
    eur = SimpleNamespace(id=41, asset_symbol="BTC")
    base = _config(None)
    eur_row = _config(41)
    usdt_row = _config(42)
    service.rows = AsyncMock(return_value=[base, eur_row, usdt_row])

    asyncio.run(service.disable(7, eur, "technical", "rsi"))

    assert eur_row.enabled is False
    assert usdt_row.enabled is True
    assert effective_pair_configs([base, eur_row]) == {}
    assert effective_pair_configs([base, usdt_row])[(7, "technical", "rsi")] is usdt_row
    session.commit.assert_awaited_once()
