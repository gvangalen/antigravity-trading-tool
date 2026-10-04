import assert from "node:assert/strict";
import test from "node:test";
import { inactiveProposalIds, retireFinnProposalCards } from "../lib/finnProposalCardState.mjs";

test("retired server proposal loses its confirmation card while a new draft remains", () => {
  const oldCard = {
    role: "assistant", text: "ETH-concept", canConfirm: true,
    actions: [{ type: "v2_proposal", proposal_id: "old" }],
    setupDraft: { operation_id: "create_setup" },
    state: { setup_draft: { operation_id: "create_setup" } },
  };
  const newCard = {
    role: "assistant", text: "AAPL-concept", canConfirm: true,
    actions: [{ type: "v2_proposal", proposal_id: "new" }],
  };
  const retired = inactiveProposalIds(["old", "new"], [
    { status: "fulfilled", value: { status: "cancelled" } },
    { status: "fulfilled", value: { status: "draft" } },
  ]);
  const result = retireFinnProposalCards([oldCard, newCard], retired);
  assert.deepEqual(result[0].actions, []);
  assert.equal(result[0].canConfirm, false);
  assert.equal(result[0].setupDraft, null);
  assert.equal(result[0].state.setup_draft, null);
  assert.equal(result[0].proposalRetired, true);
  assert.equal(result[1], newCard);
});

test("a failed status read does not invent a cancellation", () => {
  const retired = inactiveProposalIds(["pending"], [
    { status: "rejected", reason: new Error("network") },
  ]);
  assert.equal(retired.size, 0);
});
