import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(new URL("../lib/api/strategy.js", import.meta.url), "utf8");

test("strategy updates exclude create-only setup and form state fields", () => {
  assert.match(source, /const allowedFields = \[/);
  assert.match(source, /'name', 'symbol', 'timeframe', 'execution_mode', 'base_amount'/);
  assert.match(source, /data\[field\] !== undefined/);
  assert.doesNotMatch(source, /\.\.\.data,/);
});
