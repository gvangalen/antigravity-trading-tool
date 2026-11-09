import assert from "node:assert/strict";
import test from "node:test";

import { firstDisplayReason } from "../lib/bot/displayReason.mjs";

test("bot reasons remain readable across current and legacy response shapes", () => {
  assert.equal(firstDisplayReason(["", "Daglimiet bereikt"]), "Daglimiet bereikt");
  assert.equal(firstDisplayReason({ reason: "  Daglimiet bereikt  " }), "Daglimiet bereikt");
  assert.equal(firstDisplayReason({ detail: "Hercontrole nodig" }), "Hercontrole nodig");
  assert.equal(firstDisplayReason({ reason: "{}" }), undefined);
  assert.equal(firstDisplayReason("Daglimiet bereikt"), undefined);
  assert.equal(firstDisplayReason(null), undefined);
});
