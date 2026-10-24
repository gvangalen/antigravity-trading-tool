import assert from "node:assert/strict";
import test from "node:test";

import { paperPriceMessageKey } from "../lib/bot/paperPriceMessage.mjs";

const paperAapl = { isLive: false, symbol: "AAPL", reasonCode: "market_price_stale" };

test("the passed time determines whether regular AAPL market hours have ended", () => {
  assert.equal(paperPriceMessageKey({ ...paperAapl, at: "2026-10-24T12:00:00Z" }), "paperAaplMarketClosed");
  assert.equal(paperPriceMessageKey({ ...paperAapl, at: "2026-10-23T18:00:00Z" }), "paperPriceUnavailable");
  assert.equal(paperPriceMessageKey({ ...paperAapl, at: "2026-10-23T21:00:00Z" }), "paperAaplMarketClosed");
});

test("an unknown session, other asset or other safety reason does not claim a closed AAPL market", () => {
  assert.equal(paperPriceMessageKey({ ...paperAapl, at: null }), "paperPriceUnavailable");
  assert.equal(paperPriceMessageKey({ ...paperAapl, at: "bad-date" }), "paperPriceUnavailable");
  assert.equal(paperPriceMessageKey({ ...paperAapl, symbol: "BTC", at: "2026-10-24T12:00:00Z" }), "paperPriceUnavailable");
  assert.equal(paperPriceMessageKey({ ...paperAapl, isLive: true, at: "2026-10-24T12:00:00Z" }), null);
  assert.equal(paperPriceMessageKey({ ...paperAapl, reasonCode: "insufficient_funds", at: "2026-10-24T12:00:00Z" }), null);
});
