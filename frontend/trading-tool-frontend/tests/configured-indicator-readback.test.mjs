import assert from "node:assert/strict";
import test from "node:test";

import { mergeConfiguredIndicatorRows } from "../lib/indicators/configuredIndicatorRows.mjs";

test("configured indicators remain visible when live data is not available yet", () => {
  const rows = mergeConfiguredIndicatorRows([], ["dxy", "rsi", "ma_200", "price"]);

  assert.deepEqual(rows.map((row) => row.name), ["dxy", "rsi", "ma_200", "price"]);
  assert.ok(rows.every((row) => row.configured === true));
  assert.ok(rows.every((row) => row.data_status === "pending_refresh"));
});

test("live data wins without creating a duplicate configured row", () => {
  const live = [{ name: "rsi", value: 54, score: 60 }];
  const rows = mergeConfiguredIndicatorRows(live, ["RSI", "DXY"]);

  assert.equal(rows.length, 2);
  assert.deepEqual(rows[0], live[0]);
  assert.equal(rows[1].name, "DXY");
});
