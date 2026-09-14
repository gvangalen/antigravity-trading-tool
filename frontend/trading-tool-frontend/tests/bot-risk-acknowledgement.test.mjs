import assert from "node:assert/strict";
import test from "node:test";

import {
  getBotRiskAcknowledgement,
  getBotSaveErrorMessage,
} from "../lib/bot/riskAcknowledgement.mjs";

test("preserves the typed bot risk acknowledgement instead of flattening it to a generic error", () => {
  const error = {
    status: 409,
    body: JSON.stringify({
      detail: {
        code: "BOT_RISK_ACK_REQUIRED",
        message: "Confirm the change deliberately.",
        behavioral_event: { type: "budget_increase" },
      },
    }),
  };

  assert.deepEqual(getBotRiskAcknowledgement(error), {
    code: "BOT_RISK_ACK_REQUIRED",
    message: "Confirm the change deliberately.",
    behavioralEvent: { type: "budget_increase" },
  });
  assert.equal(getBotSaveErrorMessage(error, "fallback"), "Confirm the change deliberately.");
});

test("does not turn unrelated API failures into a risk acknowledgement", () => {
  const error = {
    status: 409,
    body: JSON.stringify({ detail: { code: "OTHER_POLICY_BLOCK", message: "Blocked." } }),
  };

  assert.equal(getBotRiskAcknowledgement(error), null);
  assert.equal(getBotSaveErrorMessage(error, "fallback"), "fallback");
});

test("bot forms require an explicit acknowledgement before retrying a risk-changing update", async () => {
  const { readFile } = await import("node:fs/promises");
  const [budgetForm, botForm] = await Promise.all([
    readFile(new URL("../components/bot/BotBudgetForm.jsx", import.meta.url), "utf8"),
    readFile(new URL("../components/bot/AddBotForm.jsx", import.meta.url), "utf8"),
  ]);

  for (const source of [budgetForm, botForm]) {
    assert.match(source, /getBotRiskAcknowledgement\(error\)/);
    assert.match(source, /risk_acknowledged: true/);
    assert.match(source, /submitForm\(true\)/);
  }
});
