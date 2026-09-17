import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(
  new URL("../components/ui/AIAssistant.jsx", import.meta.url),
  "utf8",
);

test("FINN proposal failures expose only human dependency copy or the safe fallback", () => {
  assert.match(source, /function publicFinnExecutionError/);
  assert.match(source, /Deze setup is nog gekoppeld aan strategie/);
  assert.match(source, /Deze strategie is nog gekoppeld aan paper-bot/);
  assert.match(source, /Dat lukte niet\. Ik heb niets gewijzigd\./);
  assert.doesNotMatch(
    source,
    /throw new Error\(publicReason \|\| execution\.failure_reason/,
  );
});
