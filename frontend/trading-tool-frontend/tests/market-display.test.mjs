import assert from "node:assert/strict";
import test from "node:test";

import { marketDisplayLabel, marketDisplayQuote } from "../lib/workspace/marketDisplay.mjs";

test("legacy BTC watchlist metadata resolves to its saved USDT market", () => {
  const item = { assetClass: "crypto", tradingviewSymbol: "BINANCE:BTCUSDT" };
  assert.equal(marketDisplayQuote("BTC", item), "USDT");
  assert.equal(marketDisplayLabel("BTC", item), "BTC/USDT");
});

test("an explicit quote keeps EUR and USDT rows distinct", () => {
  assert.equal(marketDisplayLabel("BTC", { assetClass: "crypto", quoteCurrency: "EUR", tradingviewSymbol: "BINANCE:BTCUSDT" }), "BTC/EUR");
  assert.equal(marketDisplayLabel("BTC", { assetClass: "crypto", quoteCurrency: "USDT" }), "BTC/USDT");
});

test("an unresolved crypto market never appears as a standalone asset", () => {
  assert.equal(marketDisplayLabel("BTC", { assetClass: "crypto" }), null);
  assert.equal(marketDisplayLabel("BTC", { assetClass: "crypto", tradingviewSymbol: "BINANCE:ETHUSDT" }), null);
  assert.equal(marketDisplayLabel("AAPL", { assetClass: "stock" }), "AAPL");
  assert.equal(marketDisplayLabel("AAPL", { assetClass: "stock", quoteCurrency: "USD" }), "AAPL");
});
