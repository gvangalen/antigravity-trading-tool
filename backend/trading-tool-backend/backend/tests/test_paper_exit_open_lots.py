"""The Paper exit must validate the whole still-open buying episode."""

from backend.engine.trading_bot_execution import (
    _open_paper_trade_lots,
    _paper_lot_matches_plan,
)


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, *_args):
        pass

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, rows):
        self.rows = rows

    def cursor(self):
        return _Cursor(self.rows)


def _buy(row_id, qty, *, stop=342, strategy=7):
    return (
        row_id, qty, row_id + 100,
        {"trade_plan": {"source_price_currency": "USD", "source_levels": {
            "entry": 347.14, "stop_loss": stop, "targets": [357.42]
        }}}, strategy,
    )


def _open(rows, qty):
    return _open_paper_trade_lots(
        _Connection(rows), user_id=1, bot_id=2, symbol="AAPL", position_qty=qty,
    )


def test_additional_buy_keeps_oldest_opening_identity_and_checks_every_plan():
    lots = _open([_buy(12, .3), _buy(11, 1.2, stop=341)], 1.5)
    assert [lot[0] for lot in lots] == [12, 11]
    assert _paper_lot_matches_plan(
        lots[0], strategy_id=7, currency="USD", entry=347.14,
        stop=342, first_target=357.42,
    )
    assert not _paper_lot_matches_plan(
        lots[1], strategy_id=7, currency="USD", entry=347.14,
        stop=342, first_target=357.42,
    )


def test_partial_sale_still_requires_original_open_plan():
    # The latest sell removes some quantity, but the opening plan survives.
    lots = _open([(13, -.3, 113, {}, 7), _buy(12, .3), _buy(11, 1.2)], 1.2)
    assert [lot[0] for lot in lots] == [12, 11]


def test_missing_opening_or_conflicting_strategy_holds():
    assert _open([_buy(12, .3)], 1.5) is None
    lots = _open([_buy(12, .3, strategy=8), _buy(11, 1.2)], 1.5)
    assert lots is not None
    assert not _paper_lot_matches_plan(
        lots[0], strategy_id=7, currency="USD", entry=347.14,
        stop=342, first_target=357.42,
    )
