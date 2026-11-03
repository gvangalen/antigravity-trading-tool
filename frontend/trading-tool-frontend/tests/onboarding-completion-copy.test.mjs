import assert from "node:assert/strict";
import test from "node:test";
import { onboardingCompletionDescription } from "../lib/onboardingCompletionCopy.js";

const copy = {
  completeDescription: "setup",
  completeDescriptionWithStrategy: "strategy",
  completeDescriptionWithBot: "bot",
  completeDescriptionWithStrategyAndBot: "both",
};

test("completion describes the saved optional steps", () => {
  assert.equal(onboardingCompletionDescription(copy, {}), "setup");
  assert.equal(onboardingCompletionDescription(copy, { has_strategy: true }), "strategy");
  assert.equal(onboardingCompletionDescription(copy, { has_bot: true }), "bot");
  assert.equal(onboardingCompletionDescription(copy, { has_strategy: true, has_bot: true }), "both");
});
