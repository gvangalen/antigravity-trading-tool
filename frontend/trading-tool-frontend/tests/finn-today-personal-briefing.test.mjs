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
    /const workspaceSupport = personalWorkspaceSummary \|\|/,
    "the personal plan summary must take precedence over generic support copy",
  );
  assert.match(
    assistantSource,
    /if \(isOpen\) \{\s*loadMissionControl\(\);/,
    "the compact FINN Today preview must load the same typed mission-control projection",
  );
});
