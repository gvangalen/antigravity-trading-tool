import assert from "node:assert/strict";
import test from "node:test";
import { marketContextFromEvidence } from "../lib/workspace/marketContext.mjs";

const now = new Date("2026-10-24T18:00:00Z");
const quote = { price: 80_000, change_24h: -2.75, as_of: "2026-10-24T17:58:00Z" };
const maRow = { name: "ma_200", raw: {
  value: 1.04,
  source_observed_at: "2026-10-23T23:59:59Z",
  freshness: { status: "available", stale: false },
} };

test("fresh owner-scoped day readings describe a price above MA200 and a recent fall", () => {
  const context = marketContextFromEvidence({ quote, quoteStatus: "current", technicalRows: [maRow], now });
  assert.equal(context.ma.position, "above");
  assert.equal(context.change.direction, "down");
  assert.equal(context.change.percent, -2.75);
  assert.equal(context.available, true);
});

test("a closed equity session remains historical context, not a current quote", () => {
  const context = marketContextFromEvidence({ quote, quoteStatus: "closed_session", technicalRows: [], now });
  assert.equal(context.change.closedSession, true);
  assert.equal(context.ma, null);
});

test("stale and incomplete sources cannot create a market-context claim", () => {
  const staleMa = { ...maRow, raw: { ...maRow.raw, freshness: { status: "available", stale: true } } };
  assert.deepEqual(marketContextFromEvidence({ quote, quoteStatus: "stale", technicalRows: [staleMa], now }), {
    ma: null, change: null, available: false,
  });
  assert.equal(marketContextFromEvidence({
    quote: { ...quote, as_of: null }, quoteStatus: "current", technicalRows: [], now,
  }).available, false);
  assert.equal(marketContextFromEvidence({
    quote: { ...quote, change_24h: null }, quoteStatus: "current", technicalRows: [], now,
  }).available, false);
});

test("a weekly aggregated MA200 reading is never described as a day-candle comparison", () => {
  const context = marketContextFromEvidence({
    quote, quoteStatus: "current", technicalRows: [maRow], technicalPeriod: "week", now,
  });
  assert.equal(context.ma, null);
  assert.equal(context.change.direction, "down");
});

test("a current MA200 reading can be shown without inventing a short-term trend", () => {
  const context = marketContextFromEvidence({
    quote: null, quoteStatus: "stale", technicalRows: [maRow], now,
  });
  assert.equal(context.ma.position, "above");
  assert.equal(context.change, null);
  assert.equal(context.available, true);
});

test("a future-dated MA200 reading is not presented as current context", () => {
  const futureMa = { ...maRow, raw: { ...maRow.raw, source_observed_at: "2026-10-25T12:00:00Z" } };
  assert.equal(marketContextFromEvidence({
    quote: null, quoteStatus: "stale", technicalRows: [futureMa], now,
  }).available, false);
});
