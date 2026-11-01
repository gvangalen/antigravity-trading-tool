import assert from "node:assert/strict";
import test from "node:test";
import { movingAverageSeries, rsiSeries } from "../lib/charts/technicalStudies.mjs";

const candles = (closes) => closes.map((close, index) => ({ time: index + 1, close }));

test("RSI uses closed candles and distinguishes rising, falling and flat prices", () => {
  assert.equal(rsiSeries(candles(Array.from({ length: 16 }, (_, index) => index + 1)))[0].value, 100);
  assert.equal(rsiSeries(candles(Array.from({ length: 16 }, (_, index) => 16 - index)))[0].value, 0);
  assert.equal(rsiSeries(candles(Array(16).fill(10)))[0].value, 50);
  assert.equal(rsiSeries(candles(Array(14).fill(10))).length, 0);
});

test("moving averages align to the source candle and do not invent warmup values", () => {
  assert.deepEqual(movingAverageSeries(candles([1, 2, 3, 4]), 3), [
    { time: 3, value: 2 }, { time: 4, value: 3 },
  ]);
  assert.deepEqual(movingAverageSeries(candles([1, 2, 3, 4]), 3, true), [
    { time: 3, value: 2 }, { time: 4, value: 3 },
  ]);
  assert.deepEqual(movingAverageSeries(candles([1, 2]), 3), []);
});
