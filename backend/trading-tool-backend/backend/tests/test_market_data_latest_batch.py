import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy.dialects import postgresql

from backend.infrastructure.repositories.market_data_repository import MarketDataRepository


def test_latest_quote_batch_uses_indexed_top_one_lookup_per_symbol():
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: []),
    )))

    assert asyncio.run(MarketDataRepository(session).get_latest_snapshots(
        ["btc", "ETH", "BTC"],
    )) == []

    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "VALUES ('BTC'), ('ETH')" in sql
    assert "JOIN LATERAL" in sql
    assert "market_data.symbol = requested.symbol" in sql
    assert "ORDER BY market_data.timestamp DESC" in sql
    assert "LIMIT 1" in sql
    assert "row_number" not in sql.lower()
