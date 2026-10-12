import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const shellSource = await readFile(
  new URL("../components/finn/FinnWorkspaceShell.jsx", import.meta.url), "utf8",
);
const feedSource = await readFile(
  new URL("../components/finn/FinnCoachFeed.jsx", import.meta.url), "utf8",
);
const assistantSource = await readFile(
  new URL("../components/ui/AIAssistant.jsx", import.meta.url), "utf8",
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
});

test("feed discussion has independent request state and chat component identity", () => {
  assert.match(shellSource, /setPendingFeedHandoff\(handoff\)/);
  assert.match(shellSource, /key=\{pendingFeedHandoff\?\.nonce\s*\|\|\s*"general"\}/);
  assert.match(shellSource, /commandRequest=\{currentFinnRequest\(pendingFeedHandoff, commandRequest\)\}/);
  assert.match(feedSource, /onDiscuss\?\.\(item\.id,/);
  assert.match(assistantSource, /resolveFeedDraftQuery\(/);
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
