import pytest
from datetime import datetime, timezone

from backend.engine.trading_bot_execution import _auto_execute_decision, _get_live_exchange_balance, _get_live_price, _validate_live_auto_order_risk


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split()).lower()
        self.connection.queries.append(normalized)
        if "from bot_ledger" in normalized:
            self.rows = [(self.connection.spent,)]
        elif "from bot_orders" in normalized:
            self.rows = self.connection.pending
        elif "from market_data" in normalized:
            legacy_rows = (self.connection.market_by_asset or {}).get(params[0], self.connection.market)
            self.rows = [
                (*row, datetime.now(timezone.utc), row[2]) if len(row) == 3 else row
                for row in legacy_rows
            ]
        else:
            raise AssertionError(normalized)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, *, spent=0, pending=None, market=None, market_by_asset=None):
        self.queries = []
        self.spent = spent
        self.pending = pending or []
        self.market = market if market is not None else [(50000, 0, "EUR")]
        self.market_by_asset = market_by_asset

    def cursor(self):
        return _Cursor(self)


def test_auto_live_exposure_accepts_confirmable_order():
    connection = _Connection()
    _validate_live_auto_order_risk(
        connection, 1, "BTC", 100,
        {"total": {"EUR": 900, "BTC": 0.002}}, 100,
    )
    spend_query = next(sql for sql in connection.queries if "from bot_ledger" in sql)
    assert "o.execution_environment='live'" in spend_query
    assert "o.execution_environment is null" in spend_query


def test_auto_live_exposure_counts_pending_orders():
    with pytest.raises(RuntimeError, match="exposure limit"):
        _validate_live_auto_order_risk(
            _Connection(pending=[("BTC", 650)]), 1, "BTC", 100,
            {"total": {"EUR": 900, "BTC": 0.002}}, 100,
        )


def test_auto_live_exposure_fails_without_market_price():
    with pytest.raises(RuntimeError, match="price unavailable"):
        _validate_live_auto_order_risk(
            _Connection(market=[]), 1, "BTC", 100,
            {"total": {"EUR": 900, "BTC": 0.002}}, 100,
        )


def test_auto_live_exposure_uses_exchange_ticker_for_unpriced_holdings(monkeypatch):
    from backend.engine import trading_bot_execution

    monkeypatch.setattr(trading_bot_execution, "_get_live_asset_eur_price", lambda *_args: 0.9)
    _validate_live_auto_order_risk(
        _Connection(market_by_asset={"BTC": [(50000, 0, "EUR")], "USDT": []}),
        1, "BTC", 10,
        {"total": {"EUR": 900, "USDT": 100}}, 100,
        exchange_name="bybit",
    )


def test_live_price_rejects_stale_or_invalid_market_snapshot():
    assert _get_live_price(_Connection(market=[(50000, 301, "EUR")]), "BTC", max_age_seconds=300) is None
    assert _get_live_price(_Connection(market=[(50000, 299, "EUR")]), "BTC", max_age_seconds=300) == 50000
    assert _get_live_price(_Connection(market=[(50000, None, "EUR")]), "BTC", max_age_seconds=300) is None
    assert _get_live_price(_Connection(market=[(50000, 0, "USDT")]), "BTC", max_age_seconds=300) is None
    assert _get_live_price(_Connection(market=[(0, 0, "EUR")]), "BTC", max_age_seconds=300) is None
    assert _get_live_price(_Connection(market=[(-1, 0, "EUR")]), "BTC", max_age_seconds=300) is None
    assert _get_live_price(_Connection(market=[(float("nan"), 0, "EUR")]), "BTC", max_age_seconds=300) is None


def test_auto_live_exposure_uses_verified_eur_ticker_instead_of_usdt_market_data(monkeypatch):
    from backend.engine import trading_bot_execution

    prices = []
    def eur_ticker(_conn, _user_id, _exchange, asset):
        prices.append(asset)
        return 50000
    monkeypatch.setattr(trading_bot_execution, "_get_live_asset_eur_price", eur_ticker)
    _validate_live_auto_order_risk(
        _Connection(market=[(49000, 0, "USDT")]), 1, "BTC", 100,
        {"total": {"EUR": 900, "BTC": 0.002}}, 100,
        exchange_name="bitvavo",
    )
    assert prices == ["BTC"]


def test_auto_live_order_rechecks_limit_against_exchange_quote(monkeypatch):
    from backend.engine import trading_bot_execution

    monkeypatch.setattr(trading_bot_execution, "_get_live_asset_eur_price", lambda *_args: 50000)
    with pytest.raises(RuntimeError, match="deviates from current exchange quote"):
        _validate_live_auto_order_risk(
            _Connection(), 1, "BTC", 100,
            {"total": {"EUR": 900, "BTC": 0.002}}, 100,
            exchange_name="bitvavo", order_price=55000,
        )
    _validate_live_auto_order_risk(
        _Connection(), 1, "BTC", 100,
        {"total": {"EUR": 900, "BTC": 0.002}}, 100,
        exchange_name="bitvavo", order_price=50100,
    )

    def unavailable_quote(*_args):
        raise ValueError("Exchange quote is stale")

    monkeypatch.setattr(trading_bot_execution, "_get_live_asset_eur_price", unavailable_quote)
    with pytest.raises(ValueError, match="Exchange quote is stale"):
        _validate_live_auto_order_risk(
            _Connection(), 1, "BTC", 100,
            {"total": {"EUR": 900, "BTC": 0.002}}, 100,
            exchange_name="bitvavo", order_price=50000,
        )


def test_auto_live_execution_rejects_ambiguous_exchange_connection():
    class ExchangeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args):
            pass

        def fetchall(self):
            return [("bitvavo", "key", "secret", None), ("bybit", "key", "secret", None)]

    class ExchangeConnection:
        def cursor(self):
            return ExchangeCursor()

    with pytest.raises(RuntimeError, match="Exactly one active exchange"):
        _get_live_exchange_balance(ExchangeConnection(), 1)


def test_auto_live_execution_serializes_with_manual_orders_and_rejects_unresolved_order():
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params=None):
            connection.queries.append(" ".join(sql.split()).lower())

        def fetchone(self):
            return (1,)

    class Connection:
        def __init__(self):
            self.queries = []

        def cursor(self):
            return Cursor()

    connection = Connection()
    with pytest.raises(RuntimeError, match="unresolved"):
        _auto_execute_decision(
            conn=connection, user_id=1, bot_id=2, decision_id=3,
            order={"symbol": "BTC", "side": "buy", "estimated_qty": 0.001,
                   "estimated_price": 50000}, is_live=True, mode="auto",
        )
    assert connection.queries[0] == "select pg_advisory_xact_lock(%s, %s)"
    assert "from bot_orders" in connection.queries[1]
