from datetime import datetime

import pytest

from backend.utils import scoring_engine, technical_interpreter
from backend.domain.exact_market_technical import calculate_exact_market_technical


def _rsi_rules(*, mode="standard"):
    return [
        scoring_engine.RuleRow(
            id=index + 1,
            indicator="rsi",
            range_min=low,
            range_max=high,
            score=score,
            trend=None,
            interpretation=None,
            action=None,
            score_mode=mode,
            is_active=True,
            weight=1.0,
        )
        for index, (low, high, score) in enumerate((
            (0, 20, 0), (20, 40, 25), (40, 60, 50),
            (60, 80, 75), (80, 100, 100),
        ))
    ]


@pytest.mark.parametrize(("rsi", "expected"), [
    (0, 0), (12, 0), (15, 0), (21.04, 0),
    (27.6, 25), (43.2, 50), (58.8, 75), (74.4, 100),
    (90, 100), (100, 100),
])
def test_standard_rsi_five_step_score_respects_selected_anchors(monkeypatch, rsi, expected):
    monkeypatch.setattr(scoring_engine, "fetch_rules_for_indicator", lambda *_args, **_kwargs: _rsi_rules())
    normalized = technical_interpreter.normalize_technical_value_for_rules(
        object(), "rsi", rsi, 7, "BTC",
    )
    scored = scoring_engine.score_indicator(object(), "technical", "rsi", normalized, 7, "BTC")
    assert scored["score"] == expected
    assert scored["rule_origin"] == "system_template"


def test_owner_custom_rsi_curve_keeps_raw_value_scale(monkeypatch):
    monkeypatch.setattr(scoring_engine, "fetch_rules_for_indicator", lambda *_args, **_kwargs: _rsi_rules(mode="custom"))
    assert technical_interpreter.normalize_technical_value_for_rules(
        object(), "rsi", 21.04, 7, "BTC",
    ) == 21.04


def test_zero_rsi_score_is_persisted_as_zero():
    calls = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, params):
            calls.append((statement, params))

    class Connection:
        def cursor(self):
            return Cursor()

    scoring_engine.persist_indicator_scores(
        Connection(), 7, "technical",
        [{"indicator": "rsi", "value": 15, "score": 0}],
        ts=datetime(2026, 11, 23), symbol="BTC",
    )
    assert len(calls) == 1
    assert 0 in calls[0][1]


def test_wilder_rsi_keeps_earlier_gain_after_a_later_loss():
    closes = [100, 110, *([110] * 13), 109]
    # Initial 14-delta gain average is 10/14. The final loss is smoothed
    # instead of dropping that earlier gain from the calculation window.
    assert technical_interpreter.calculate_rsi(closes) == 90.28
    candles = [{"high": close + 1, "low": close - 1, "close": close}
               for close in closes]
    assert calculate_exact_market_technical(candles)["rsi"] == 90.28
