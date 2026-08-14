import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const shellSource = await readFile(
  new URL("../components/finn/FinnWorkspaceShell.jsx", import.meta.url),
  "utf8",
);
const assistantSource = await readFile(
  new URL("../components/ui/AIAssistant.jsx", import.meta.url),
  "utf8",
);
const planSource = await readFile(
  new URL("../components/workflows/MyPlanWorkflow.jsx", import.meta.url),
  "utf8",
);

test("renders the shared FINN workspace on every protected workflow", () => {
  assert.match(shellSource, /<FinnPanel\s+[\s\S]*?previewSectionsOnly/);
  assert.doesNotMatch(shellSource, /isPlanWorkspace\s*\?/);
});

test("forwards contextual FINN requests into the regular chat", () => {
  assert.match(shellSource, /context:\s*detail\.context\s*\|\|\s*null/);
  assert.match(shellSource, /autoSubmit:\s*Boolean\(detail\.autoSubmit\)/);
  assert.match(assistantSource, /\.\.\.\(commandRequest\?\.context\s*\|\|\s*\{\}\)/);
  assert.match(assistantSource, /handleChat\(commandRequest\.query\)/);
});

test("uses compact plan actions instead of inline specialist cards", () => {
  assert.doesNotMatch(planSource, /FinnSpecialistContext/);
  assert.match(planSource, /onFinnAction=\{\(\) => askFinnForPlan\(activePlan, "setup"\)\}/);
  assert.match(planSource, /onAskFinn=\{\(\) => askFinnForPlan\(plan\)\}/);
});

test("prefers central first-dashboard context over the generic briefing template", () => {
  assert.match(assistantSource, /missionControl\?\.first_dashboard_context/);
  assert.match(assistantSource, /firstDashboardBriefingText/);
  assert.match(assistantSource, /firstDashboardContext\?\.review_label/);
  assert.match(assistantSource, /generation_status/);
  assert.match(assistantSource, /setInterval\(\(\) => \{\s*void loadMissionControl\(\)/);
});
