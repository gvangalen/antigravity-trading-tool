import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(
  new URL("../components/ui/AIAssistant.jsx", import.meta.url),
  "utf8",
);

test("renders V2 setup drafts and proposals inside the simple FINN modal", () => {
  assert.match(source, /\{renderV2SetupDraftCard\(m\)\}/);
  assert.match(source, /\{renderV2ActionDraftCard\(m\)\}/);
  assert.match(source, /\{renderInlineActionCard\(m\)\}/);
  assert.match(source, /"v2_proposal"/);
  assert.doesNotMatch(source, /\{!isSimpleFinnModal && renderV2SetupDraftCard\(m\)\}/);
  assert.doesNotMatch(source, /\{!isSimpleFinnModal && renderInlineActionCard\(m\)\}/);
});

test("builds strategy and bot draft cards from the terminal runtime contract", () => {
  assert.match(source, /draftOperations\.includes\(initialOperationId\) \? initialOperationId : finalOperationId/);
  assert.match(source, /persistedActionDraft = projection\?\.action_draft \|\| null/);
  assert.match(source, /actionDraft = persistedActionDraft \|\|/);
  assert.match(source, /supplied_inputs: projection\?\.supplied_inputs \|\| \{\}/);
  assert.match(source, /draftTitles\.strategy/);
  assert.match(source, /draftTitles\.bot/);
  assert.match(source, /hiddenIdentityFields = new Set\(\["setup_id", "strategy_id", "bot_id"\]\)/);
  assert.match(source, /\["succeeded", "already_executed"\]\.includes\(execution\.status\)/);
  assert.match(source, /display_context:/);
  assert.match(source, /Paper · niet-live/);
  assert.match(source, /execution\.error_codes\?\.\[0\]/);
  assert.match(source, /replace\(\/\^\\d\{3\}:\\s\*\//);
  assert.doesNotMatch(source, /\{context\.page_type \|\| "Finn"\} · \{context\.symbol \|\| "BTC"\} · \{context\.timeframe \|\| "1D"\}/);
  assert.doesNotMatch(source, /draft\.strategy_id \? `#\$\{draft\.strategy_id\}`/);
  assert.doesNotMatch(source, /draft\.setup_id \? `#\$\{draft\.setup_id\}`/);
  assert.doesNotMatch(source, /#\$\{option\.id\} · \$\{option\.symbol\}/);
  assert.doesNotMatch(source, /proposal_payload/);
});

test("keeps a typed guided answer out of command search", () => {
  assert.match(source, /hasActiveFinnV2GuidedTurn/);
  assert.match(source, /!hasActiveFinnV2GuidedTurn && isSimpleFinnModal && commandCenterRef\.current\?\.handleKeyDown/);
  assert.match(source, /!hasActiveFinnV2GuidedTurn && isSimpleFinnModal && commandCenterRef\.current\?\.submitPrimary/);
});
