import assert from "node:assert/strict";
import test from "node:test";

import {
  materializeWorkspaceEvidence,
  pendingWorkspaceEvidenceCategories,
} from "../lib/workspace/pendingEvidence.mjs";

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

test("materializes categories serially and continues after a provider failure", async () => {
  const calls = [];
  const results = await materializeWorkspaceEvidence(
    ["market", "macro", "technical"],
    async (category) => {
      calls.push(category);
      if (category === "macro") throw new Error("provider temporarily unavailable");
    },
  );

  assert.deepEqual(calls, ["market", "macro", "technical"]);
  assert.deepEqual(results, [
    { category: "market", status: "fulfilled" },
    { category: "macro", status: "rejected" },
    { category: "technical", status: "fulfilled" },
  ]);
});
