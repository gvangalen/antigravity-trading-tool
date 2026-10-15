from __future__ import annotations

import asyncio
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.infrastructure.repositories.bot_repository import BotRepository


class _Session:
    def __init__(self, connection):
        self.connection = connection

    async def execute(self, statement, params):
        rows = self.connection.execute(str(statement), params).fetchall()
        return SimpleNamespace(fetchall=lambda: [SimpleNamespace(_mapping=dict(row)) for row in rows])


def test_balance_history_returns_latest_window_in_chart_order():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE portfolio_balance_snapshots (
            user_id INTEGER, bucket TEXT, ts TEXT, equity_eur REAL, cash_eur REAL,
            btc_qty REAL, btc_value_eur REAL, invested_eur REAL, unrealized_pnl_eur REAL
        );
        CREATE TABLE bot_portfolio_snapshots (
            user_id INTEGER, bot_id INTEGER, bucket TEXT, ts TEXT, equity_eur REAL,
            cash_eur REAL, net_qty REAL, price_eur REAL, invested_eur REAL,
            symbol TEXT
        );
        CREATE TABLE bot_configs (id INTEGER, user_id INTEGER, is_live INTEGER);
        INSERT INTO bot_configs VALUES (4, 7, 0);
        INSERT INTO bot_configs VALUES (5, 7, 1);
        INSERT INTO portfolio_balance_snapshots VALUES
            (7, '1h', '2026-10-01T00:00:00', 10, 10, 0, 0, 0, 0),
            (7, '1h', '2026-10-02T00:00:00', 20, 20, 0, 0, 0, 0),
            (7, '1h', '2026-10-03T00:00:00', 30, 30, 0, 0, 0, 0);
        INSERT INTO bot_portfolio_snapshots VALUES
            (7, 4, '1h', '2026-10-01T00:00:00', 10, 10, 0, 1, 0, 'BTC'),
            (7, 4, '1h', '2026-10-02T00:00:00', 20, 20, 0, 1, 0, 'BTC'),
            (7, 4, '1h', '2026-10-03T00:00:00', 30, 30, 0, 1, 0, 'BTC'),
            (7, 5, '1h', '2026-10-03T00:00:00', 0, -100, 0.002, 50000, 100, 'BTC');
    """)
    repository = BotRepository(_Session(connection))
    repository.check_table_exists = AsyncMock(return_value=True)

    async def read():
        return (
            await repository.get_portfolio_balance_history(7, "1h", 2),
            await repository.get_bot_balance_history(7, 4, "1h", 2),
            await repository.get_filtered_portfolio_balance_history(7, False, "1h", 2),
        )

    for rows in asyncio.run(read()):
        assert [row["ts"] for row in rows] == [
            "2026-10-02T00:00:00", "2026-10-03T00:00:00",
        ]
        assert rows[-1]["equity_eur"] == 30
    assert asyncio.run(repository.get_bot_balance_history(7, 5, "1h", 2)) == []


def test_live_history_does_not_present_unfunded_ledger_cash_as_equity():
    repository = BotRepository(session=None)
    assert asyncio.run(repository.get_filtered_portfolio_balance_history(7, True, "1h", 10)) == []


def test_paper_history_values_btc_and_other_assets_separately():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE bot_configs (id INTEGER, user_id INTEGER, is_live INTEGER);
        CREATE TABLE bot_portfolio_snapshots (
            user_id INTEGER, bot_id INTEGER, bucket TEXT, ts TEXT, equity_eur REAL,
            cash_eur REAL, net_qty REAL, price_eur REAL, invested_eur REAL, symbol TEXT
        );
        INSERT INTO bot_configs VALUES (4, 7, 0), (6, 7, 0);
        INSERT INTO bot_portfolio_snapshots VALUES
            (7, 4, '1h', '2026-10-03', 100, 0, 1, 100, 100, 'BTC'),
            (7, 6, '1h', '2026-10-03', 200, 0, 1, 200, 100, 'ETH');
    """)
    repository = BotRepository(_Session(connection))
    repository.check_table_exists = AsyncMock(return_value=True)

    rows = asyncio.run(repository.get_filtered_portfolio_balance_history(7, False, "1h", 10))

    assert rows[0]["equity_eur"] == 300
    assert rows[0]["btc_qty"] == 1
    assert rows[0]["btc_value_eur"] == 100
    assert rows[0]["unrealized_pnl_eur"] == 100
