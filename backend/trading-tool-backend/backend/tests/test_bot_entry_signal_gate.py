from datetime import datetime, timezone

import pytest

from backend.engine import trading_bot_execution as execution


RULE = {
    "version": 1, "event": "close_crosses_reference", "direction": "above",
    "timeframe": "1D", "reference": {"kind": "sma", "period": 200},
}


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, *_):
        pass

    def fetchone(self):
        return self.rows.pop(0)


class Connection:
    def __init__(self, rows):
        self.rows = rows

    def cursor(self):
        return Cursor(self.rows)


def test_entry_gate_holds_without_cross_and_never_blocks_exit():
    buy = {"action": "buy", "amount_eur": 100, "position_size": 1}
    result = execution._enforce_entry_signal(buy, {"status": "insufficient_closed_candles"})
    assert result["action"] == "hold"
    assert result["amount_eur"] == 0
    assert execution._enforce_entry_signal(
        {"action": "sell"}, {"status": "closed_candle_stale_or_unconfirmed"},
    )["action"] == "sell"


def test_paper_execution_rejects_changed_or_replayed_signal(monkeypatch):
    evidence = {
        "status": "triggered", "rule": RULE, "market_id": 7,
        "closed_at": datetime(2026, 11, 1, 23, 59, 59, tzinfo=timezone.utc).isoformat(),
        "signal_key": "same-closed-candle",
    }
    saved = {
        "entry_signal": RULE, "price_currency_confirmed": True,
        "price_currency": "EUR", "entry": 100, "stop_loss": 90,
        "targets": [110],
    }
    plan = {"source_price_currency": "EUR", "source_levels": {
        "entry": 100, "stop_loss": 90, "targets": [110],
    }}
    monkeypatch.setattr(execution, "_assess_saved_entry_signal", lambda *_: evidence)
    rows = [("trade", saved, plan, evidence, 7, 9), (1,)]
    with pytest.raises(execution.BotSafetyBlock, match="al uitgevoerd"):
        execution._recheck_paper_trade_entry(
            Connection(rows), user_id=1, decision_id=10, symbol="BTC", market_id=7,
        )
    rows = [("trade", saved, plan, {**evidence, "signal_key": "old"}, 7, 9)]
    with pytest.raises(execution.BotSafetyBlock, match="niet meer"):
        execution._recheck_paper_trade_entry(
            Connection(rows), user_id=1, decision_id=10, symbol="BTC", market_id=7,
        )


def test_paper_execution_accepts_same_closed_candle_evidence_and_fresh_pair_price(monkeypatch):
    evidence = {"status": "triggered", "rule": RULE, "market_id": 7,
                "signal_key": "verified-candle-values"}
    saved = {"entry_signal": RULE, "price_currency_confirmed": True,
             "price_currency": "EUR", "entry": 100, "stop_loss": 90,
             "targets": [110]}
    plan = {"source_price_currency": "EUR", "source_levels": {
        "entry": 100, "stop_loss": 90, "targets": [110],
    }}
    monkeypatch.setattr(execution, "_assess_saved_entry_signal", lambda *_: evidence)
    monkeypatch.setattr(execution, "_get_trade_quote_fx_context", lambda *_args, **_kwargs: {
        "market_price_eur": 100.5, "quote_currency": "EUR",
    })
    rows = [("trade", saved, plan, evidence, 7, 9), None]
    assert execution._recheck_paper_trade_entry(
        Connection(rows), user_id=1, decision_id=10, symbol="BTC", market_id=7,
    ) == 100.5
