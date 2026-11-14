"""A revised reading for one source candle must have a stable winner."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.dialects import postgresql

from backend.infrastructure.repositories.macro_data_repository import MacroDataRepository
from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
from backend.infrastructure.repositories.technical_data_repository import TechnicalDataRepository


def _captured_sql(call):
    return str(call.args[0].compile(dialect=postgresql.dialect())).lower()


def _empty_session():
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session = SimpleNamespace(execute=AsyncMock(return_value=result))
    return session


def test_daily_indicator_reads_break_equal_source_times_by_record_id():
    technical = _empty_session()
    market = _empty_session()
    macro = _empty_session()

    asyncio.run(TechnicalDataRepository(technical).get_day_data(1, "AAPL"))
    asyncio.run(MarketDataRepository(market).get_active_day_indicators(1, "AAPL"))
    asyncio.run(MacroDataRepository(macro).get_active_day_macro_data(1, "AAPL"))

    for session, table in ((technical, "technical_indicators"),
                           (market, "market_data_indicators"),
                           (macro, "macro_data")):
        sql = _captured_sql(session.execute.call_args)
        assert f"{table}.source_observed_at desc nulls last" in sql
        assert f"{table}.id desc" in sql
        assert sql.index(f"{table}.source_observed_at desc nulls last") < sql.index(f"{table}.id desc")
