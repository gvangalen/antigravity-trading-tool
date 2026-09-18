import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = fs.readFileSync(path.join(root, "components/ui/AIAssistant.jsx"), "utf8");

test("cancelling a proposal removes every visible projection of that proposal", () => {
  assert.match(source, /messageProposalId !== proposalId/);
  assert.match(source, /if \(message\?\.draftCanceled \|\| message\?\.draftExecuted\) return null;/);
  assert.match(source, /actions: \[\]/);
  assert.match(source, /setup_draft: null, action_draft: null/);
});
