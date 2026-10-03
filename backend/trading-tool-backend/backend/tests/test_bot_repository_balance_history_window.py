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
            cash_eur REAL, net_qty REAL, price_eur REAL, invested_eur REAL
        );
        CREATE TABLE bot_configs (id INTEGER, is_live INTEGER);
        INSERT INTO bot_configs VALUES (4, 0);
        INSERT INTO portfolio_balance_snapshots VALUES
            (7, '1h', '2026-10-01T00:00:00', 10, 10, 0, 0, 0, 0),
            (7, '1h', '2026-10-02T00:00:00', 20, 20, 0, 0, 0, 0),
            (7, '1h', '2026-10-03T00:00:00', 30, 30, 0, 0, 0, 0);
        INSERT INTO bot_portfolio_snapshots VALUES
            (7, 4, '1h', '2026-10-01T00:00:00', 10, 10, 0, 1, 0),
            (7, 4, '1h', '2026-10-02T00:00:00', 20, 20, 0, 1, 0),
            (7, 4, '1h', '2026-10-03T00:00:00', 30, 30, 0, 1, 0);
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
