import assert from "node:assert/strict";
import test from "node:test";

import { normalizePaperBudgetAmount } from "../lib/paperBudgetAmount.mjs";

test("Paper budget preserves cents beyond JavaScript's safe number range", () => {
  assert.equal(normalizePaperBudgetAmount("1000000000000000,01"), "1000000000000000.01");
  assert.equal(normalizePaperBudgetAmount("1250,50"), "1250.50");
});

test("Paper budget rejects zero and ambiguous grouped amounts", () => {
  for (const raw of ["0", "0,00", "1 234,56", "1.234,56", "1.2.3", "-100", "NaN"]) {
    assert.equal(normalizePaperBudgetAmount(raw), null);
  }
});
