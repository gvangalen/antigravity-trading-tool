import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { readFinnComposerDraft, writeFinnComposerDraft } from "../lib/finnComposerDraft.mjs";

const shellSource = await readFile(
  new URL("../components/finn/FinnWorkspaceShell.jsx", import.meta.url), "utf8",
);
const feedSource = await readFile(
  new URL("../components/finn/FinnCoachFeed.jsx", import.meta.url), "utf8",
);
const assistantSource = await readFile(
  new URL("../components/ui/AIAssistant.jsx", import.meta.url), "utf8",
);
const assistantApiSource = await readFile(
  new URL("../lib/api/ai.js", import.meta.url), "utf8",
);
const planSource = await readFile(
  new URL("../components/workflows/MyPlanWorkflow.jsx", import.meta.url), "utf8",
);
const analysisSource = await readFile(
  new URL("../components/workspaces/asset/AssetWorkspaceV3.jsx", import.meta.url), "utf8",
);

test("shared workspace shows the persisted coach feed and opens chat on demand", () => {
  assert.match(shellSource, /<FinnCoachFeed\s+key=/);
  assert.match(shellSource, /<AIAssistant\s+[\s\S]*?commandRequest=/);
  assert.doesNotMatch(shellSource, /loadMissionControl|first_dashboard_context/);
  assert.doesNotMatch(assistantSource, /loadMissionControl\(|fetchFinnMissionControl/);
  assert.doesNotMatch(assistantApiSource, /assistant\/mission-control/);
});

test("feed discussion enters the persistent FINN panel with its event identity", () => {
  assert.match(shellSource, /setFeedDiscussion\(\{ request: handoff, draft: nextQuery \}\)/);
  assert.match(shellSource, /data-feed-handoff-id=\{feedDiscussion\?\.request\.context\.feed_item_id \|\| undefined\}/);
  assert.match(shellSource, /data-testid="finn-chat-panel"/);
  assert.match(shellSource, /commandRequest=\{feedDiscussion \? feedDiscussion\.request : commandRequest\}/);
  assert.match(shellSource, /closeFeedDiscussion\(feedDiscussion\.request\.nonce\)/);
  assert.match(shellSource, /closeLabel=\{workspaceCopy\.closeBackdrop\}/);
  assert.match(feedSource, /onDiscuss\?\.\(item\.id,/);
  assert.match(assistantSource, /resolveFeedDraftQuery\(/);
  assert.match(assistantSource, /aria-label=\{closeLabel \|\| at\("uiText\.closeChat"\)\}/);
});

test("ordinary questions submit directly and chat stays beside the workspace", () => {
  assert.match(shellSource, /mode: "chat", query: composerQuery\.trim\(\), autoSubmit: true/);
  assert.match(shellSource, /xl:pr-\[440px\]/);
  assert.match(shellSource, /dock\s+expanded=/);
  assert.doesNotMatch(shellSource, /backdrop-blur-sm/);
  assert.match(assistantSource, /if \(event\.key === "Enter" && !event\.shiftKey && !event\.nativeEvent\.isComposing\)/);
  assert.match(assistantSource, /\{isCommandSearchOpen \? \(\s*<FinnCommandCenter/);
});

test("unsent composer drafts survive remount only for their owner", () => {
  const entries = new Map();
  const storage = {
    getItem: (key) => entries.get(key) ?? null,
    setItem: (key, value) => entries.set(key, value),
    removeItem: (key) => entries.delete(key),
  };
  writeFinnComposerDraft(storage, 17, "Onverzonden ETH-conceptvraag");
  assert.equal(readFinnComposerDraft(storage, 17), "Onverzonden ETH-conceptvraag");
  assert.equal(readFinnComposerDraft(storage, 18), "");
  writeFinnComposerDraft(storage, 17, "");
  assert.equal(readFinnComposerDraft(storage, 17), "");
  assert.match(shellSource, /hydratedDraftOwnerId === ownerId/);
});

test("explicit contextual requests still reach ordinary FINN chat", () => {
  assert.match(shellSource, /context:\s*detail\.context\s*\|\|\s*null/);
  assert.match(shellSource, /autoSubmit:\s*Boolean\(detail\.autoSubmit\)/);
  assert.match(assistantSource, /\.\.\.\(commandRequest\?\.context\s*\|\|\s*\{\}\)/);
});

test("indicator questions use FINN chat rather than the retired specialist", () => {
  assert.match(analysisSource, /query: ui\.indicatorQuestion\(row\.name, symbol, category, period\)/);
  assert.match(analysisSource, /openFinnContext\(\{/);
  assert.doesNotMatch(analysisSource, /requestIndicatorContext|finnResult/);
});

test("plan actions use FINN chat rather than inline specialist cards", () => {
  assert.doesNotMatch(planSource, /FinnSpecialistContext/);
  assert.match(planSource, /onFinnAction=\{\(\) => askFinnForPlan\(activePlan, "setup"\)\}/);
  assert.match(planSource, /onAskFinn=\{\(\) => askFinnForPlan\(plan\)\}/);
});
