import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const shellSource = await readFile(
  new URL("../components/finn/FinnWorkspaceShell.jsx", import.meta.url),
  "utf8",
);

test("renders the shared FINN workspace on every protected workflow", () => {
  assert.match(shellSource, /<FinnPanel\s+[\s\S]*?previewSectionsOnly/);
  assert.doesNotMatch(shellSource, /isPlanWorkspace\s*\?/);
});
