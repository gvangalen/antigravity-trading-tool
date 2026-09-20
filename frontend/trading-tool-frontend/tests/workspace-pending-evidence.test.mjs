import assert from "node:assert/strict";
import test from "node:test";

import { pendingWorkspaceEvidenceCategories } from "../lib/workspace/pendingEvidence.mjs";

test("materializes only configured evidence that is visibly pending or incomplete", () => {
  const categories = pendingWorkspaceEvidenceCategories({
    categories: {
      market: { rows: [{ name: "price", value: 101 }] },
      macro: { rows: [{ name: "dxy", value: null, data_status: "pending_refresh" }] },
      technical: { rows: [{ name: "rsi", value: null, data_status: "insufficient_data" }] },
    },
  });

  assert.deepEqual(categories, ["macro", "technical"]);
});

test("does not synchronize already materialized or absent evidence", () => {
  assert.deepEqual(pendingWorkspaceEvidenceCategories({
    categories: {
      market: { rows: [{ name: "price", value: 101, data_status: "available" }] },
      macro: { rows: [] },
      technical: { rows: [{ name: "rsi", value: null, data_status: "available" }] },
    },
  }), []);
});
