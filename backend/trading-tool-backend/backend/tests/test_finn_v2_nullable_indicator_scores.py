import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services.finn_v2_tool_adapters.macro_tool_adapter import MacroToolAdapter
from backend.services.finn_v2_tool_adapters.technical_tool_adapter import TechnicalToolAdapter


def test_macro_snapshot_preserves_missing_and_stale_scores():
    adapter = object.__new__(MacroToolAdapter)
    old = datetime.now(timezone.utc) - timedelta(days=14)
    adapter.repository = SimpleNamespace(get_active_day_macro_data=AsyncMock(return_value=[
        SimpleNamespace(name="sp500", value=5400, score=None, trend=None,
                        timestamp=datetime.now(timezone.utc), source_observed_at=None),
        SimpleNamespace(name="dxy", value=100, score=100, trend="positive",
                        timestamp=datetime.now(timezone.utc), source_observed_at=old),
    ]))

    result = asyncio.run(adapter.execute(user_id=7, asset="AAPL"))

    assert [item.score for item in result["data"].items] == [None, None]
    assert result["data"].items[0].value == 5400
    assert result["data"].items[0].source_observed_at is None
    assert result["as_of"] == old


def test_technical_snapshot_keeps_real_zero_but_not_missing_score():
    adapter = object.__new__(TechnicalToolAdapter)
    observed = datetime.now(timezone.utc)
    adapter.service = SimpleNamespace(get_day_indicators=AsyncMock(return_value=[
        SimpleNamespace(indicator="rsi", value=30, score=0, advies=None,
                        uitleg=None, timestamp=observed, source_observed_at=observed),
        SimpleNamespace(indicator="adx", value=20, score=None, advies=None,
                        uitleg=None, timestamp=observed, source_observed_at=observed),
    ]))

    result = asyncio.run(adapter.execute(user_id=7, asset="AAPL"))

    assert [item.score for item in result["data"].items] == [0, None]
