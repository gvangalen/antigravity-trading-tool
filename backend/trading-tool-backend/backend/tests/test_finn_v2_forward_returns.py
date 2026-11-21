import asyncio
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.schemas.finn_v2_evidence_schema import ForwardReturnsData
from backend.schemas.market_data_schema import MarketForwardReturnResponse
from backend.services.finn_v2_responses_tool_catalog import FinnResponsesToolCatalog
from backend.services.finn_v2_tool_adapters.forward_returns_tool_adapter import ForwardReturnsToolAdapter


def test_forward_returns_contract_and_responses_read():
    catalog = FinnResponsesToolCatalog()
    call = catalog.validate("get_forward_returns", {"asset": "BTC"})
    assert call.read_tools == ("read_active_asset", "read_forward_returns")
    assert catalog.validate("get_forward_returns", {"asset": "BTC", "quote_currency": "USDT"}).read_tools == call.read_tools
    assert "read_forward_returns" in catalog.read_definitions


def test_forward_returns_reads_stored_periods_and_marks_partial_current_period():
    today = datetime.now(timezone.utc)
    records = [
        SimpleNamespace(period=period, start_date=today, end_date=today,
                        change=value, created_at=today)
        for period, value in (("7d", 1.0), ("30d", 2.0), ("90d", 3.0), ("365d", 4.0))
    ]
    adapter = ForwardReturnsToolAdapter(object())
    adapter.repository.get_forward_returns = AsyncMock(return_value=records)

    result = asyncio.run(adapter.execute(asset="btc"))

    assert result["schema_name"] == "ForwardReturnsData"
    data = result["data"]
    assert isinstance(data, ForwardReturnsData)
    assert set(data.periods) == {"week", "month", "quarter", "year"}
    assert {period: marker.value for period, marker in data.partial.items()} == {
        "week": 1.0, "month": 2.0, "quarter": 3.0, "year": 4.0,
    }
    adapter.repository.get_forward_returns.assert_awaited_once_with("BTC")


def test_forward_returns_accepts_date_columns_from_existing_market_table():
    today = datetime.now(timezone.utc).date()
    record = SimpleNamespace(
        period="30d", start_date=today.replace(day=1), end_date=today,
        change=2.5, created_at=datetime.now(timezone.utc),
    )
    adapter = ForwardReturnsToolAdapter(object())
    adapter.repository.get_forward_returns = AsyncMock(return_value=[record])

    result = asyncio.run(adapter.execute(asset="BTC"))

    assert result["data"].periods["month"][0].values[today.month - 1] == 2.5
    assert result["data"].observed_through == today


def test_raw_forward_return_response_accepts_date_only_period_bounds():
    observed_date = date(2026, 11, 21)
    record = SimpleNamespace(
        id=1, symbol="BTC", period="30d", start_date=observed_date,
        end_date=observed_date, change=2.5, avg_daily=0.1,
        created_at=datetime(2026, 11, 21, tzinfo=timezone.utc),
    )

    response = MarketForwardReturnResponse.from_orm(record)

    assert response.start.date() == observed_date
    assert response.end.date() == observed_date
