import assert from "node:assert/strict";
import test from "node:test";
import { inactiveProposalIds, isFinnProposalCorrection, mapBackendSessionMessages, retireEarlierFinnProposalCards, retireFinnProposalCards, setupDraftFrequencyLabel, suspendedProposalIds, suspendFinnProposalCards, verifiedPaperBotStrategy } from "../lib/finnProposalCardState.mjs";
import { hasConfirmableDraft } from "../lib/finnDraftConversation.mjs";

test("only an active server proposal restores its confirmable draft card", () => {
  const messages = mapBackendSessionMessages([
    { role: "assistant", content: "Oude kaart", proposal_id: "old" },
    { role: "assistant", content: "Dit is je ETH-concept", pending_proposal: {
      proposal_id: "open", run_id: "run-open", conversation_id: "finn-v2-conv-owned",
      operation_id: "create_setup", asset: "ETH",
      draft: { operation_id: "create_setup", draft_status: "complete",
        supplied_inputs: { name: "ETH QA", symbol: "ETH", timeframe: "1D" }, missing_inputs: [] },
    } },
  ]);
  assert.equal(hasConfirmableDraft(messages[0]), false);
  assert.equal(hasConfirmableDraft(messages[1]), true);
  assert.equal(messages[1].setupDraft.supplied_inputs.name, "ETH QA");
  assert.equal(messages[1].actions[0].proposal_id, "open");
  assert.equal(messages[1].actions[0].display_context.conversation_id, "finn-v2-conv-owned");
  assert.equal(JSON.stringify(messages).includes("confirmation_token"), false);
});

test("trade drafts have no DCA frequency and DCA labels cannot stringify objects", () => {
  const translate = (value) => value;
  assert.equal(setupDraftFrequencyLabel({ setup_type: "trade" }, translate), "");
  assert.equal(setupDraftFrequencyLabel({ setup_type: "dca", dca_frequency: "weekly", dca_day: "monday" }, translate), "weekly · monday");
  assert.equal(setupDraftFrequencyLabel({ setup_type: "dca", dca_frequency: {} }, translate), "");
});

test("a direct amount correction suspends an old proposal while a hypothetical question does not", () => {
  assert.equal(isFinnProposalCorrection("Corrigeer het bedrag naar €75. Bevestig niets."), true);
  assert.equal(isFinnProposalCorrection("Correctie: ik bedoel een andere ETH-setup. Bevestig niets."), true);
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

test("a repeated proposal ID leaves exactly one confirmable card", () => {
  const first = {
    streamId: "first", role: "assistant", text: "ETH voorstel", canConfirm: true,
    actions: [{ type: "v2_proposal", proposal_id: "same" }],
    setupDraft: { operation_id: "create_setup" },
  };
  const latest = { streamId: "latest", role: "assistant", text: "Ik toon het voorstel opnieuw" };
  const unrelated = {
    streamId: "other", role: "assistant", canConfirm: true,
    actions: [{ type: "v2_proposal", proposal_id: "different" }],
  };
  const result = retireEarlierFinnProposalCards([first, latest, unrelated], "latest", "same");
  assert.equal(result[0].canConfirm, false);
  assert.deepEqual(result[0].actions, []);
  assert.equal(result[0].setupDraft, null);
  assert.equal(result[0].text, first.text);
  assert.equal(result[1], latest);
  assert.equal(result[2], unrelated);
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
