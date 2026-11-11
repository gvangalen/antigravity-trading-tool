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
        scalars=lambda: SimpleNamespace(all=lambda: []),
    )))

    assert asyncio.run(MarketDataRepository(session).get_latest_quoted_snapshot("BTC")) is None

    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "market_data.symbol = 'BTC'" in sql
    assert "market_data.market_id IS NULL" in sql
    assert "ORDER BY market_data.source_observed_at DESC, market_data.timestamp DESC, market_data.id DESC" in sql


def test_quoted_snapshot_rejects_conflicting_top_provider_facts():
    from datetime import datetime
    stamp = datetime(2026, 11, 10, 20, 48)
    def row(row_id, price, *, minute=stamp):
        return SimpleNamespace(id=row_id, symbol="AAPL", price=price, quote_currency="USD",
                               price_provider="twelve_data", source_observed_at=minute,
                               timestamp=minute)
    consistent = [row(12, 348.49), row(11, 348.49)]
    assert MarketDataRepository._verified_top_quote(consistent).id == 12
    assert MarketDataRepository._verified_top_quote([row(12, 348.49), row(11, 348.63)]) is None
    wrong_symbol = row(11, 348.49)
    wrong_symbol.symbol = "MSFT"
    assert MarketDataRepository._verified_top_quote([row(12, 348.49), wrong_symbol]) is None
    revised_receipt = row(13, 348.63)
    revised_receipt.timestamp = datetime(2026, 11, 10, 20, 49)
    assert MarketDataRepository._verified_top_quote([revised_receipt, row(12, 348.49)]) is None
    assert MarketDataRepository._verified_top_quote([row(12, None), row(11, 348.49)]) is None
    missing_unit = row(12, 348.49)
    missing_unit.quote_currency = None
    assert MarketDataRepository._verified_top_quote([missing_unit, row(11, 348.49)]) is None
    repeated = [row(i, 348.49) for i in range(66)]
    assert MarketDataRepository._verified_top_quote(repeated).id == 65
    repeated[0].price = 348.63
    assert MarketDataRepository._verified_top_quote(repeated) is None
    assert MarketDataRepository._verified_top_quote([row(i, 348.49) for i in range(4096)]) is None
    assert MarketDataRepository._verified_top_quote([
        row(13, 349.00, minute=datetime(2026, 11, 10, 20, 49)),
        row(12, 348.49), row(11, 348.63),
    ]).id == 13


def test_quoted_batch_read_uses_same_deterministic_order():
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: []),
    )))
    assert asyncio.run(MarketDataRepository(session).get_latest_quoted_snapshots(["AAPL"])) == []
    sql = str(session.execute.await_args.args[0].compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True},
    ))
    assert "ORDER BY market_data.source_observed_at DESC, market_data.timestamp DESC, market_data.id DESC" in sql


def test_quoted_batch_omits_conflicted_symbol_without_hiding_other_assets():
    from datetime import datetime
    stamp = datetime(2026, 11, 10, 20, 48)
    rows = [
        SimpleNamespace(id=2, symbol="AAPL", price=348.63, quote_currency="USD",
                        price_provider="twelve_data", source_observed_at=stamp, timestamp=stamp),
        SimpleNamespace(id=9, symbol="BTC", price=80000, quote_currency="EUR",
                        price_provider="binance", source_observed_at=stamp, timestamp=stamp),
        SimpleNamespace(id=3, symbol="AAPL", price=348.49, quote_currency="USD",
                        price_provider="twelve_data", source_observed_at=stamp, timestamp=stamp),
    ]
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: rows),
    )))
    selected = asyncio.run(MarketDataRepository(session).get_latest_quoted_snapshots(["AAPL", "BTC"]))
    assert [row.symbol for row in selected] == ["BTC"]


def test_exact_market_batch_keeps_verified_pair_and_omits_conflicted_pair():
    from datetime import datetime
    stamp = datetime(2026, 11, 10, 20, 48)
    def row(row_id, market_id, symbol, price, quote):
        return SimpleNamespace(id=row_id, market_id=market_id, symbol=symbol,
                               price=price, quote_currency=quote, price_provider="binance",
                               source_observed_at=stamp, timestamp=stamp)
    candidates = [
        (row(1, 10, "BTC", 80000, "USDT"), "BTC", "USDT"),
        (row(2, 11, "ETH", 3000, "USDT"), "ETH", "USDT"),
        (row(3, 11, "ETH", 3100, "USDT"), "ETH", "USDT"),
    ]
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
        all=lambda: candidates,
    )))
    selected = asyncio.run(MarketDataRepository(session).get_latest_exact_market_snapshots([10, 11]))
    assert list(selected) == [10]
    sql = str(session.execute.await_args.args[0].compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True},
    ))
    assert "JOIN LATERAL" in sql
    assert "LIMIT 4096" in sql
    assert "trading_markets.venue = 'BINANCE'" in sql


def test_exact_market_price_read_requires_selected_market_id():
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
        all=lambda: [],
    )))
    repo = MarketDataRepository(session)
    assert asyncio.run(repo.get_latest_exact_market_snapshot(23)) is None
    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "market_data.market_id = 23" in sql
    assert "trading_markets.asset_symbol" in sql
    assert "trading_markets.quote_currency" in sql
    assert "market_data.symbol = trading_markets.asset_symbol" not in sql
    assert "market_data.quote_currency = trading_markets.quote_currency" not in sql
    assert "ORDER BY market_data.source_observed_at DESC, market_data.timestamp DESC, market_data.id DESC" in sql
    assert "market_data.symbol = 'BTC'" not in sql


def test_legacy_portfolio_price_requires_the_source_quote():
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: []),
    )))
    assert asyncio.run(BotRepository(session).get_valuatable_market_prices(["BTC"])) == {}
    sql = str(session.execute.await_args.args[0])
    assert "market_data.market_id IS NULL" in sql
    assert "market_data.source_observed_at IS NOT NULL" in sql


def test_live_market_snapshot_uses_row_quote_and_fails_on_conflicting_top_rows():
    from datetime import datetime
    stamp = datetime(2026, 11, 10, 20, 48)
    rows = [SimpleNamespace(id=row_id, symbol="AAPL", price=price,
                            quote_currency="USD", price_provider="twelve_data",
                            source_observed_at=stamp, timestamp=stamp)
            for row_id, price in ((12, 348.49), (11, 348.63))]
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: rows),
    )))
    repo = BotRepository(session)
    assert asyncio.run(repo.get_market_price_snapshot("AAPL")) is None
    rows[1].price = 348.49
    assert asyncio.run(repo.get_market_price_snapshot("AAPL")) == {
        "price": 348.49, "timestamp": stamp, "quote_currency": "USD",
    }
