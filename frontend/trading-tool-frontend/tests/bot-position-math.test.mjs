import test from "node:test";
import assert from "node:assert/strict";
import { botSessionPerformance, fullPaperPositionQuantity } from "../lib/botPositionMath.mjs";

test("100% Paper sale preserves the ledger quantity", () => {
  assert.equal(fullPaperPositionQuantity(0.00138012), "0.00138012");
  assert.equal(fullPaperPositionQuantity(0), "");
});

test("closed Paper result uses purchases, not residual net cash, as return denominator", () => {
  assert.deepEqual(botSessionPerformance(0, -0.38, 100), {
    pnlEur: -0.38, pnlPct: -0.38,
  });
  assert.deepEqual(botSessionPerformance(100, -100, 100), {
    pnlEur: 0, pnlPct: 0,
  });
  assert.deepEqual(botSessionPerformance(null, -100, 100), {
    pnlEur: null, pnlPct: null,
  });
});
