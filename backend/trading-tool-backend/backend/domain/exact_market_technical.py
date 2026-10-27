"""Technical measurements from completed candles of one exact trading pair."""

from __future__ import annotations

from math import isfinite
from typing import Mapping, Sequence

import pandas as pd

from backend.utils.technical_interpreter import calculate_rsi


def calculate_exact_market_technical(candles: Sequence[Mapping[str, object]]) -> dict[str, float]:
    """Return only indicators backed by enough completed, ordered candles.

    Callers must scope candles to one verified market ID and exclude the open
    candle. Values are raw indicator measurements; Score 2.0 applies the
    owner's rule and weight separately.
    """
    valid = []
    for candle in candles:
        try:
            high = float(candle["high"])
            low = float(candle["low"])
            close = float(candle["close"])
        except (KeyError, TypeError, ValueError):
            continue
        if not all(isfinite(value) and value > 0 for value in (high, low, close)):
            continue
        if high < max(low, close) or low > close:
            continue
        valid.append((high, low, close))
    if len(valid) < 15:
        return {}

    frame = pd.DataFrame(valid, columns=("high", "low", "close"), dtype="float64")
    close = frame["close"]
    high = frame["high"]
    low = frame["low"]
    output: dict[str, float] = {}

    def record(name: str, value: object) -> None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return
        if isfinite(number):
            output[name] = number

    record("rsi", calculate_rsi(close.tolist(), period=14))
    for period in (50, 200):
        if len(frame) >= period:
            average = float(close.tail(period).mean())
            if average > 0:
                record(f"ma_{period}", close.iloc[-1] / average)
            ema = close.ewm(span=period, adjust=False, min_periods=period).mean().iloc[-1]
            if period == 50 and ema > 0:
                record("ema_50_gap_pct", (close.iloc[-1] / ema - 1) * 100)
    if len(frame) >= 20:
        ema20 = close.ewm(span=20, adjust=False, min_periods=20).mean().iloc[-1]
        if ema20 > 0:
            record("ema_20_gap_pct", (close.iloc[-1] / ema20 - 1) * 100)
    if len(frame) >= 35:
        macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
        signal = macd.ewm(span=9, adjust=False).mean()
        record("macd_hist_pct", (macd.iloc[-1] - signal.iloc[-1]) / close.iloc[-1] * 100)

    previous_close = close.shift(1)
    true_range = pd.concat((high - low, (high - previous_close).abs(),
                            (low - previous_close).abs()), axis=1).max(axis=1)
    atr = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    if atr.iloc[-1] > 0:
        record("atr_pct", atr.iloc[-1] / close.iloc[-1] * 100)
    if len(frame) >= 28:
        high_move = high.diff()
        low_move = -low.diff()
        plus_dm = high_move.where((high_move > low_move) & (high_move > 0), 0.0)
        minus_dm = low_move.where((low_move > high_move) & (low_move > 0), 0.0)
        smoothed_atr = atr.replace(0, float("nan"))
        plus_di = 100 * plus_dm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean() / smoothed_atr
        minus_di = 100 * minus_dm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean() / smoothed_atr
        di_sum = (plus_di + minus_di).replace(0, float("nan"))
        dx = 100 * (plus_di - minus_di).abs() / di_sum
        adx = dx.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean().iloc[-1]
        record("adx", adx)
    return output
