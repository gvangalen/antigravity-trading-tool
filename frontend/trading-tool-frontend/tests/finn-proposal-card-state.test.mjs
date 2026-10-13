import assert from "node:assert/strict";
import test from "node:test";
import { inactiveProposalIds, isFinnProposalCorrection, retireFinnProposalCards, suspendedProposalIds, suspendFinnProposalCards, verifiedPaperBotStrategy } from "../lib/finnProposalCardState.mjs";

test("a direct amount correction suspends an old proposal while a hypothetical question does not", () => {
  assert.equal(isFinnProposalCorrection("Corrigeer het bedrag naar €75. Bevestig niets."), true);
  assert.equal(isFinnProposalCorrection("De naam is alleen Apple DCA Nieuwe QA."), true);
  assert.equal(isFinnProposalCorrection("Kan ik het bedrag veranderen?"), false);
  const card = { actions: [{ type: "v2_proposal", proposal_id: "old" }], canConfirm: true };
  assert.equal(suspendFinnProposalCards([card], new Set(["old"]))[0].confirmationSuspended, true);
});

test("a Paper-bot card is confirmable only for its owner-scoped proposal strategy", () => {
  const strategies = [{ id: 81, name: "ETH DCA" }, { id: 82, name: "Other" }];
  const target = { target_type: "strategy", target_id: "81" };
  assert.equal(verifiedPaperBotStrategy({ target, draftStrategyId: 81, ownerStrategies: strategies })?.name, "ETH DCA");
  assert.equal(verifiedPaperBotStrategy({ target, draftStrategyId: 82, ownerStrategies: strategies }), null);
  assert.equal(verifiedPaperBotStrategy({ target: { target_type: "bot", target_id: 81 }, draftStrategyId: 81, ownerStrategies: strategies }), null);
  assert.equal(verifiedPaperBotStrategy({ target, draftStrategyId: 81, ownerStrategies: [] }), null);
  assert.equal(verifiedPaperBotStrategy({ target: null, draftStrategyId: 81, ownerStrategies: strategies }), null);
});

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

test("a clarification or failed status read cannot reactivate the previous card", () => {
  const cards = [{
    role: "assistant", canConfirm: true,
    actions: [{ type: "v2_proposal", proposal_id: "old" }],
  }];
  const openResults = [{ status: "fulfilled", value: { status: "draft" } }];
  const suspended = suspendedProposalIds(["old"], openResults, true);
  assert.equal(suspended.has("old"), true);
  assert.equal(suspendFinnProposalCards(cards, suspended)[0].confirmationSuspended, true);
  assert.equal(suspendedProposalIds(["old"], openResults).size, 0);
  assert.equal(suspendedProposalIds(["old"], [{ status: "rejected" }]).has("old"), true);
});
