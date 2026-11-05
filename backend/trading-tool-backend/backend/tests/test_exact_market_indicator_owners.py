import asyncio
from types import SimpleNamespace

from backend.services.exact_market_indicator_service import ExactMarketIndicatorService


def test_watched_pair_inherits_owner_indicators_without_setup():
    statements = []

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

        def all(self):
            return self.rows

        def scalars(self):
            return self

    class Session:
        async def execute(self, statement, _params=None):
            statements.append(str(statement))
            if len(statements) == 1:
                return Result([(7,)])
            if len(statements) == 2:
                return Result([])
            return Result([SimpleNamespace(user_id=7, symbol="BTC", category="market",
                                           indicator="price", market_id=None, enabled=True)])

    market = SimpleNamespace(id=73, asset_symbol="BTC")
    owners = asyncio.run(ExactMarketIndicatorService(Session())._configured_owners(market))

    assert "watchlists WHERE market_id" in statements[0]
    assert owners == {7: {"market": {"price"}, "technical": set()}}
