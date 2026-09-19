import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(
  new URL("../components/ui/AIAssistant.jsx", import.meta.url),
  "utf8",
);

test("renders V2 setup drafts and proposals inside the simple FINN modal", () => {
  assert.match(source, /\{renderV2SetupDraftCard\(m, i\)\}/);
  assert.match(source, /\{renderV2ActionDraftCard\(m, i\)\}/);
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
  assert.match(source, /Concept setup/);
  assert.match(source, /Concept strategie/);
  assert.match(source, /Concept paper-bot/);
  assert.match(source, /Nog niet opgeslagen/);
  assert.match(source, /draftCards\.missing/);
  assert.match(source, /Verder invullen/);
  assert.match(source, /Geen live trading/);
  assert.match(source, /Gekoppeld aan/);
  assert.match(source, /Timeframe/);
  assert.match(source, /→/);
  assert.match(source, /Verwijderen/);
  assert.match(source, /Aanpassen/);
  assert.match(source, /Annuleren/);
  assert.match(source, /\["succeeded", "already_executed"\]\.includes\(execution\.status\)/);
  assert.match(source, /display_context:/);
  assert.match(source, /strategy_name: resolvedStrategyName/);
  assert.match(source, /operationId\?\.includes\("strategy"\) \? resolvedStrategyName : null/);
  assert.match(source, /Paper · niet-live/);
  assert.match(source, /execution\.error_codes\?\.\[0\]/);
  assert.match(source, /replace\(\/\^\\d\{3\}:\\s\*\//);
  assert.doesNotMatch(source, /\{context\.page_type \|\| "Finn"\} · \{context\.symbol \|\| "BTC"\} · \{context\.timeframe \|\| "1D"\}/);
  assert.doesNotMatch(source, /draft\.strategy_id \? `#\$\{draft\.strategy_id\}`/);
  assert.doesNotMatch(source, /draft\.setup_id \? `#\$\{draft\.setup_id\}`/);
  assert.doesNotMatch(source, /#\$\{option\.id\} · \$\{option\.symbol\}/);
  assert.doesNotMatch(source, /bot #\$\{res\.bot_id\}/);
  assert.doesNotMatch(source, /strategy #\$\{res\.strategy_id\}/);
  assert.doesNotMatch(source, /proposal_payload/);
});

test("keeps confirmation controls inside a single calm draft card", () => {
  assert.match(source, /const dedicatedDraftOperation = message\.setupDraft\?\.operation_id/);
  assert.match(source, /"create_setup", "create_strategy", "create_bot",[\s\S]*?\]\.includes\(dedicatedDraftOperation\)/);
  assert.match(source, /if \(actionOnly\.length === 0 \|\| message\.draft \|\| hasDedicatedDraftCard\) return null/);
  assert.match(source, /draftActionButtons\(message, messageIndex/);
  assert.match(source, /min-w-0 overflow-hidden rounded-2xl/);
  assert.match(source, /break-words text-xs/);
  assert.match(source, /flex flex-wrap items-center gap-2/);
  assert.match(source, /displayContext\.strategy_name \|\| activeSetup\?\.strategy_name/);
  assert.match(source, /onClick=\{\(\) => void handleExecuteAction\(proposal\)\}/);
  assert.doesNotMatch(source, /if \(event\.detail !== 0\) return/);
  assert.doesNotMatch(source, /onPointerUp=/);
});

test("keeps a typed guided answer out of command search", () => {
  assert.match(source, /hasActiveFinnV2GuidedTurn/);
  assert.match(source, /!hasActiveFinnV2GuidedTurn && isSimpleFinnModal && commandCenterRef\.current\?\.handleKeyDown/);
  assert.match(source, /!hasActiveFinnV2GuidedTurn && isSimpleFinnModal && commandCenterRef\.current\?\.submitPrimary/);
});
