import assert from "node:assert/strict";
import test from "node:test";
import { marketPairLabel } from "../lib/marketPairLabel.mjs";

test("saved markets retain their actual quote across setup, strategy, and bot", () => {
  assert.equal(marketPairLabel({ symbol: "BTC", market_id: 1, quote_currency: "EUR" }), "BTC/EUR");
  assert.equal(marketPairLabel({ symbol: "BTC", setup_market_id: 2, market_quote_currency: "USDT" }), "BTC/USDT");
  assert.equal(marketPairLabel({ symbol: "BTC", market_id: 3, quote_currency: "USDT", base_currency: "EUR" }), "BTC/USDT");
  assert.equal(marketPairLabel({ strategy: { setup: { symbol: "BTC", market_id: 4, quote_currency: "EUR" } } }), "BTC/EUR");
  assert.equal(marketPairLabel({ symbol: "AAPL", quote_currency: "USD" }), "AAPL");
});
