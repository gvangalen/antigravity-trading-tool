from datetime import datetime, timedelta, timezone
import asyncio

from backend.engine.trading_bot_execution import _get_live_price
from backend.api.bot_api import get_verified_portfolio_value_history
from backend.celery_task import portfolio_fx_task
from backend.services.portfolio_snapshot_service import _snapshot_verified_paper
from backend.services.portfolio_overview_service import project_portfolio
import json


class _Cursor:
    def __init__(self, *, bots, prices, fx):
        self.bots, self.prices, self.fx = bots, prices, fx
        self.rows = []
        self.snapshots = []
        self.queries = []

    def execute(self, sql, params=None):
        statement = " ".join(sql.lower().split())
        self.queries.append((statement, params))
        if "from bot_configs c" in statement:
            self.rows = [row if len(row) == 8 else (*row, False) for row in self.bots]
        elif "from portfolio_fx_rates" in statement and "quote_currency in" in statement:
            self.rows = self.fx
        elif "from portfolio_fx_rates" in statement:
            quote = params[0]
            match = next((row for row in self.fx if row[0] == quote), None)
            self.rows = [(match[1], match[2])] if match else []
        elif "from market_data m" in statement and "any(%s)" in statement:
            self.rows = [(symbol, *self.prices[symbol], index) for index, symbol in enumerate(params[0]) if symbol in self.prices]
        elif "from market_data m" in statement:
            self.rows = [(
                self.prices[params[0]][0], 0, self.prices[params[0]][2],
                self.prices[params[0]][1],
                self.prices[params[0]][3] if len(self.prices[params[0]]) > 3 else self.prices[params[0]][2],
            )] if params[0] in self.prices else []
        elif "into portfolio_value_snapshots_v2" in statement:
            self.snapshots.append(params)
            self.rows = []
        else:
            self.rows = []

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def test_verified_paper_snapshot_requires_all_bots_and_uses_fx():
    now = datetime.now(timezone.utc)
    cursor = _Cursor(
        bots=[(1, "ETH", True, 100, 1, False, now), (2, "BTC", True, 50, 0, False, now)],
        prices={"ETH": (2500, now, "USDT")},
        fx=[("USDT", 0.8, now, "binance", "EURUSDT")],
    )
    assert _snapshot_verified_paper(cursor, 17, "1h", now) is True
    assert len(cursor.snapshots) == 1
    assert cursor.snapshots[0][0] == 17
    assert cursor.snapshots[0][3:7] == (2150.0, 150.0, 2000.0, 2)
    assert "c.user_id=%s and c.is_live=false" in cursor.queries[0][0]
    evidence = json.loads(cursor.snapshots[0][-1])
    assert evidence["positions"][0]["cash_eur"] == 100
    assert evidence["positions"][0]["price_row_id"] == 0
    assert evidence["positions"][1]["cash_eur"] == 50
    assert evidence["positions"][1]["portfolio_updated_at"] == now.isoformat()


def test_unfunded_or_stale_fx_never_writes_partial_history():
    now = datetime.now(timezone.utc)
    stale = _Cursor(bots=[(1, "ETH", True, 100, 1, False, now)],
                    prices={"ETH": (2500, now, "USDT")},
                    fx=[("USDT", 0.8, now-timedelta(hours=25), "binance", "EURUSDT")])
    assert _snapshot_verified_paper(stale, 17, "1h", now) is False
    assert stale.snapshots == []
    unfunded = _Cursor(bots=[(1, "ETH", False, None, None, False, None)], prices={}, fx=[])
    assert _snapshot_verified_paper(unfunded, 17, "1h", now) is False
    assert unfunded.snapshots == []


def test_empty_paper_bot_does_not_hide_funded_history():
    now = datetime.now(timezone.utc)
    cursor = _Cursor(bots=[
        (129, "BTC", True, 10000, 0, False, now, True),
        (130, "AAPL", False, None, None, False, None, False),
    ], prices={}, fx=[])
    assert _snapshot_verified_paper(cursor, 17, "1h", now) is True
    assert cursor.snapshots[0][3:7] == (10000.0, 10000.0, 0.0, 2)


def test_twenty_assets_use_one_price_read_and_one_complete_snapshot():
    now = datetime.now(timezone.utc)
    bots = [(index, f"ASSET{index}", True, 10, 1, False, now) for index in range(20)]
    prices = {f"ASSET{index}": (100, now, "EUR") for index in range(20)}
    cursor = _Cursor(bots=bots, prices=prices, fx=[])
    assert _snapshot_verified_paper(cursor, 17, "1h", now)
    assert cursor.snapshots[0][3:7] == (2200.0, 200.0, 2000.0, 20)
    assert sum("from market_data m" in sql for sql, _ in cursor.queries) == 1


def test_legacy_unverified_paper_ledger_never_enters_verified_history():
    now = datetime.now(timezone.utc)
    cursor = _Cursor(bots=[(1, "ETH", True, 100, 1, True, now)],
                     prices={"ETH": (2500, now, "USDT")},
                     fx=[("USDT", 0.8, now, "binance", "EURUSDT")])
    assert _snapshot_verified_paper(cursor, 17, "1h", now) is False
    assert cursor.snapshots == []


def test_unverified_ledger_is_visible_per_bot_without_claiming_a_value():
    result = project_portfolio({"bots": [{
        "bot_id": 1, "symbol": "ETH", "name": "Legacy",
        "is_live": False, "portfolio_initialized": True,
        "unverified_ledger": True, "price_available": True,
        "cash": 100, "qty": 1, "position_value": 200,
    }]}, environment="paper")
    assert result.valuation_status == "unverified_ledger"
    assert result.bots[0].valuation_status == "unverified_ledger"
    assert result.bots[0].equity is None


def test_paper_order_price_is_eur_and_live_non_eur_does_not_use_catalog_quote():
    now = datetime.now(timezone.utc)
    cursor = _Cursor(bots=[], prices={"ETH": (2500, now, "USDT")}, fx=[("USDT", 0.8, now)])
    conn = _Connection(cursor)
    assert _get_live_price(conn, "ETH") == 2000.0
    assert _get_live_price(conn, "ETH", max_age_seconds=60) is None


def test_paper_price_rejects_legacy_or_mismatched_row_quote():
    now = datetime.now(timezone.utc)
    for row_quote in (None, "USD"):
        cursor = _Cursor(
            bots=[], prices={"BTC": (100, now, "USDT", row_quote)},
            fx=[("USDT", 0.8, now)],
        )
        assert _get_live_price(_Connection(cursor), "BTC", paper_execution=True) is None


def test_fx_refresh_rejects_undated_quote_and_keeps_other_source(monkeypatch):
    now = datetime.now(timezone.utc)
    stored = []
    monkeypatch.setattr(portfolio_fx_task, "_readings", lambda: [
        ("USD", "twelve_data", "EUR/USD", 1.25, now),
        ("USDT", "binance", "EURUSDT", 1.25, None),
    ])
    monkeypatch.setattr(portfolio_fx_task, "store_portfolio_fx_rates", lambda rows: stored.extend(rows))
    assert portfolio_fx_task.refresh_portfolio_fx_rates.run() == {"stored": 1}
    assert stored[0][:4] == ("USD", 0.8, "twelve_data", "EUR/USD")


def test_history_route_is_owner_scoped_and_never_invents_live_total():
    class Session:
        def __init__(self):
            self.parameters = None

        async def execute(self, statement, parameters):
            self.parameters = parameters
            assert "user_id=:user_id" in str(statement)
            return self

        def fetchall(self):
            return []

    session = Session()
    paper = asyncio.run(get_verified_portfolio_value_history(
        environment="paper", bucket="1h", limit=50, current_user={"id": 17}, db=session,
    ))
    assert session.parameters == {"user_id": 17, "bucket": "1h", "limit": 50}
    assert paper["status"] == "no_verified_history"
    live = asyncio.run(get_verified_portfolio_value_history(
        environment="live", bucket="1h", limit=50, current_user={"id": 17}, db=session,
    ))
    assert live["status"] == "unreconciled_live" and live["points"] == []
