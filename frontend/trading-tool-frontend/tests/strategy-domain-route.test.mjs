import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readSource = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("keeps the strategy workspace reachable for additional strategies under a setup", async () => {
  const page = await readSource("app/(protected)/strategy/page.jsx");

  assert.match(page, /StrategiesWorkspaceSection/);
  assert.doesNotMatch(page, /router\.replace/);
  assert.doesNotMatch(page, /\/setup\$\{/);
});
