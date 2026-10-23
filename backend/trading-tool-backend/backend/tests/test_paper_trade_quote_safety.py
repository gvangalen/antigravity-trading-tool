"""Paper trade levels must be compared in one verified, recent unit."""

from datetime import datetime, timedelta, timezone

import pytest

from backend.engine import trading_bot_execution as worker
from backend.services.portfolio_fx_service import trade_quote_context


NOW = datetime(2026, 10, 23, 18, 0, tzinfo=timezone.utc)


def _fx(value, minutes_ago=10):
    return {"eur_per_unit": value, "observed_at": NOW - timedelta(minutes=minutes_ago)}


def _context(**overrides):
    values = {
        "price": 347.14,
        "price_at": NOW - timedelta(minutes=5),
        "row_quote": "USDT",
        "catalog_quote": "USDT",
        "usd_fx": _fx(0.85),
        "quote_fx": _fx(0.84),
        "now": NOW,
    }
    values.update(overrides)
    return trade_quote_context(**values)


def test_trade_quote_uses_independent_usd_and_usdt_factors():
    result = _context()
    assert result["reason"] is None
    assert result["market_price_eur"] == pytest.approx(347.14 * 0.84)
    assert result["usd_fx_eur_per_unit"] == 0.85
    assert result["market_fx_eur_per_unit"] == 0.84
    assert result["market_price_at"] == NOW - timedelta(minutes=5)


@pytest.mark.parametrize(("changes", "reason"), [
    ({"row_quote": None}, "market_quote_unverified"),
    ({"row_quote": "USD"}, "market_quote_unverified"),
    ({"price_at": NOW - timedelta(minutes=31)}, "market_price_stale"),
    ({"usd_fx": None}, "usd_eur_fx_unavailable"),
    ({"quote_fx": None}, "market_quote_eur_fx_unavailable"),
    ({"usd_fx": _fx(0.85, 121)}, "usd_eur_fx_unavailable"),
    ({"quote_fx": _fx(0.84, 121)}, "market_quote_eur_fx_unavailable"),
    ({"usd_fx": _fx(0.85, 115)}, "trade_quote_sources_out_of_sync"),
])
def test_trade_quote_holds_on_missing_or_stale_sources(changes, reason):
    assert _context(**changes)["reason"] == reason


def test_eur_trade_does_not_need_usd_rate():
    result = _context(
        price=100, row_quote="EUR", catalog_quote="EUR",
        usd_fx=None, quote_fx=None, require_usd=False,
    )
    assert result["market_price_eur"] == 100
    assert result["usd_fx_eur_per_unit"] is None


class _Cursor:
    def __init__(self, strategy, plan):
        self.strategy = strategy
        self.plan = plan

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, *_args):
        return None

    def fetchone(self):
        return ("trade", self.strategy, self.plan)


class _Connection:
    def __init__(self, strategy, plan):
        self.strategy = strategy
        self.plan = plan

    def cursor(self):
        return _Cursor(self.strategy, self.plan)


def _recheck(monkeypatch, *, market_price_eur, strategy=None, plan=None):
    strategy = strategy or {
        "price_currency": "USD", "price_currency_confirmed": True,
        "entry": 100, "stop_loss": 95, "targets": [110],
    }
    plan = plan or {
        "source_price_currency": "USD",
        "source_levels": {"entry": 100, "stop_loss": 95, "targets": [110]},
    }
    monkeypatch.setattr(worker, "_get_trade_quote_fx_context", lambda *_args, **_kwargs: {
        "market_price_eur": market_price_eur,
        "usd_fx_eur_per_unit": 0.85,
    })
    return worker._recheck_paper_trade_entry(
        _Connection(strategy, plan), user_id=1, decision_id=2, symbol="BTC",
    )


def test_paper_execution_rechecks_usd_entry_against_current_eur_quote(monkeypatch):
    assert _recheck(monkeypatch, market_price_eur=85.5) == 85.5
    with pytest.raises(worker.BotSafetyBlock, match="buiten de opgeslagen instapzone"):
        _recheck(monkeypatch, market_price_eur=86.5)


def test_paper_execution_blocks_when_saved_levels_change(monkeypatch):
    with pytest.raises(worker.BotSafetyBlock, match="strategieprijzen zijn gewijzigd"):
        _recheck(monkeypatch, market_price_eur=85.5, strategy={
            "price_currency": "USD", "price_currency_confirmed": True,
            "entry": 101, "stop_loss": 95, "targets": [110],
        })
