import assert from "node:assert/strict";
import test from "node:test";
import { formatMarketPrice } from "../lib/marketPriceFormat.mjs";

test("exact quotes display their own unit, including non-ISO USDT", () => {
  assert.match(formatMarketPrice(71000, "nl-NL", "EUR"), /€.*71\.000/);
  assert.equal(formatMarketPrice(80050, "nl-NL", "USDT"), "80.050 USDT");
  assert.equal(formatMarketPrice(null, "nl-NL", "USDT"), "---");
});
