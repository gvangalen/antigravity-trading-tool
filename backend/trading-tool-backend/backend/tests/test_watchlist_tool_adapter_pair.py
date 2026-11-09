import asyncio
from types import SimpleNamespace

from backend.schemas.finn_v2_evidence_schema import WatchlistData
from backend.services.finn_v2_reasoning_context_service import FinnV2ReasoningContextService
from backend.services.finn_v2_tool_adapters.watchlist_tool_adapter import WatchlistToolAdapter


class _Rows:
    def all(self):
        return [
            (SimpleNamespace(symbol="BTC", market_id=17), SimpleNamespace(quote_currency="USDT")),
            (SimpleNamespace(symbol="ETH", market_id=18), SimpleNamespace(quote_currency="EUR")),
            (SimpleNamespace(symbol="AAPL", market_id=None), None),
        ]


class _Session:
    async def execute(self, statement):
        assert "watchlists.user_id" in str(statement)
        assert "trading_markets" in str(statement)
        return _Rows()


def test_watchlist_read_preserves_exact_market_identity_for_multiple_assets():
    result = asyncio.run(WatchlistToolAdapter(_Session()).execute(user_id=7, asset="BTC"))
    data = WatchlistData.parse_obj(result["data"])
    assert [(row.symbol, row.quote_currency, row.pair) for row in data.symbols] == [
        ("BTC", "USDT", "BTC/USDT"),
        ("ETH", "EUR", "ETH/EUR"),
        ("AAPL", None, None),
    ]
    assert data.contains_target_asset is True
    context = FinnV2ReasoningContextService(session=object())._sanitize_facts(result["data"], "read_watchlist")
    assert context["symbols"][0]["pair"] == "BTC/USDT"
