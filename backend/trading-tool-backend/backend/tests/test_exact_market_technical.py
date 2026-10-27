from math import isfinite

from backend.domain.exact_market_technical import calculate_exact_market_technical


def _candles(count: int, *, rising: bool) -> list[dict]:
    rows = []
    for index in range(count):
        close = 100 + (index * 0.25 if rising else -index * 0.25)
        rows.append({"high": close + 1, "low": close - 1, "close": close})
    return rows


def test_exact_pair_indicators_need_completed_history():
    assert calculate_exact_market_technical(_candles(14, rising=True)) == {}
    partial = calculate_exact_market_technical(_candles(16, rising=True))
    assert set(partial) == {"rsi", "atr_pct"}
    assert "ma_200" not in calculate_exact_market_technical(_candles(199, rising=True))


def test_exact_pair_indicators_use_directional_candles():
    rising = calculate_exact_market_technical(_candles(220, rising=True))
    falling = calculate_exact_market_technical(_candles(220, rising=False))
    expected = {"rsi", "ma_50", "ma_200", "ema_20_gap_pct",
                "ema_50_gap_pct", "macd_hist_pct", "atr_pct", "adx"}
    assert set(rising) == set(falling) == expected
    assert all(isfinite(value) for value in rising.values())
    assert rising["ma_200"] > 1 > falling["ma_200"]
    assert rising["rsi"] > falling["rsi"]
    assert rising["macd_hist_pct"] >= 0 >= falling["macd_hist_pct"]
