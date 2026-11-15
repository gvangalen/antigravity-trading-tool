import assert from "node:assert/strict";
import test from "node:test";

import { canonicalAssetPairSearch } from "../lib/setup/assetPairLink.mjs";

test("pair deep links become canonical asset and quote links", () => {
  const params = new URLSearchParams(canonicalAssetPairSearch(
    "symbol=btc%2Fusdt&quote=EUR&variant=v3&tab=market",
  ));
  assert.equal(params.get("symbol"), "BTC");
  assert.equal(params.get("quote"), "USDT");
  assert.equal(params.get("variant"), "v3");
  assert.equal(params.get("tab"), "market");
});

test("canonical and unrecognized symbols are left alone", () => {
  assert.equal(canonicalAssetPairSearch("symbol=BTC&quote=USDT"), null);
  assert.equal(canonicalAssetPairSearch("symbol=BTC%2FCHF"), null);
});
