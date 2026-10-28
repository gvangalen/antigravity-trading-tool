import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy.dialects import postgresql

from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
from backend.infrastructure.repositories.bot_repository import BotRepository


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
    assert "market_data.market_id IS NULL" in sql
    assert "ORDER BY market_data.timestamp DESC" in sql
    assert "LIMIT 1" in sql
    assert "row_number" not in sql.lower()


def test_legacy_price_read_excludes_exact_market_rows():
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
        scalars=lambda: SimpleNamespace(first=lambda: None),
    )))

    assert asyncio.run(MarketDataRepository(session).get_latest_quoted_snapshot("BTC")) is None

    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "market_data.symbol = 'BTC'" in sql
    assert "market_data.market_id IS NULL" in sql


def test_exact_market_price_read_requires_selected_market_id():
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
        scalars=lambda: SimpleNamespace(first=lambda: None),
    )))
    repo = MarketDataRepository(session)
    assert asyncio.run(repo.get_latest_exact_market_snapshot(23)) is None
    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "market_data.market_id = 23" in sql
    assert "market_data.symbol =" not in sql


def test_legacy_portfolio_price_requires_the_source_quote():
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
        fetchall=lambda: [],
    )))
    assert asyncio.run(BotRepository(session).get_valuatable_market_prices(["BTC"])) == {}
    sql = str(session.execute.await_args.args[0])
    assert "market_id IS NULL" in sql
    assert "quote_currency IS NOT NULL" in sql
