import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const assistantSource = fs.readFileSync(
  path.join(root, "components/ui/AIAssistant.jsx"),
  "utf8",
);

test("FINN Today renders the typed personal mission-control briefing", () => {
  assert.match(
    assistantSource,
    /missionControl\?\.finn_briefing\?\.summary/,
    "the compact workspace must consume the persisted personal briefing",
  );
  assert.match(
    assistantSource,
    /firstDashboardContext\?\.coaching_briefing/,
    "the UI must consume the dedicated coach presentation contract",
  );
  for (const field of ["assessment", "reasoning", "recommended_action", "data_limitation"]) {
    assert.match(
      assistantSource,
      new RegExp(`firstDashboardCoaching\\?\\.${field}`),
      `the coach presentation must consume ${field}`,
    );
  }
  assert.doesNotMatch(
    assistantSource,
    /const workspaceSupport = personalWorkspaceSummary \|\|/,
    "the database-like workspace summary must not override FINN Today coaching copy",
  );
  assert.match(
    assistantSource,
    /if \(isOpen\) \{\s*loadMissionControl\(\);/,
    "the compact FINN Today preview must load the same typed mission-control projection",
  );
  assert.match(
    assistantSource,
    /if \(Object\.keys\(preferences\)\.length === 0\)/,
    "the compact first-login preview must load the persisted trader profile",
  );
  assert.doesNotMatch(
    assistantSource,
    /Laatste analyse nog niet beschikbaar\./,
    "missing fresh market data must not erase the known personal context",
  );
  assert.match(
    assistantSource,
    /if \(!isOpen\) return;[\s\S]*?\["pending", "queued", "generating", "retry_scheduled"\]/,
    "the compact FINN Today preview must keep polling while background enrichment is active",
  );
  assert.match(
    assistantSource,
    /firstDashboardContext\?\.review_state === "not_reviewed_yet"[\s\S]*?uiText\.workspaceFirstDashboardLabel/,
    "review state must render through locale copy rather than a backend English label",
  );
  assert.match(assistantSource, /const firstDashboardHeadline = firstDashboardCoaching\?\.assessment/);
  assert.match(assistantSource, /normalizeVisibleBriefing\(firstDashboardBriefingText/);
  assert.match(assistantSource, /NOT_REVIEWED_YET\|not_reviewed_yet/);
  assert.match(assistantSource, /raw\.includes\("not_reviewed"\).*workspaceFirstDashboardLabel/);
});

test("recoverable FINN Today failures are never persisted in browser cache", () => {
  assert.match(assistantSource, /const isRecoverableFailure = \["failed", "error", "fallback_error"\]/);
  assert.match(assistantSource, /normalized && !isRecoverableFailure/);
  assert.match(assistantSource, /sessionStorage\.removeItem\(requestKey\)/);
});
