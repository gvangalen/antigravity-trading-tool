import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { canCacheMissionControl, firstBriefingPhase } from "../lib/finn/firstBriefingState.mjs";

test("a pending plan summary is never restored as a saved FINN briefing", () => {
  const pending = { first_dashboard_context: {
    is_first_dashboard: true,
    response_source: "deterministic_fallback_while_generating",
    generation_status: "queued",
  } };
  assert.equal(firstBriefingPhase(pending.first_dashboard_context), "generating");
  assert.equal(canCacheMissionControl(pending), false);
});

test("Dutch onboarding shell and navigation use Dutch labels", () => {
  const copy = JSON.parse(readFileSync(new URL("../dictionaries/nl.json", import.meta.url), "utf8"));
  assert.equal(copy.finnWorkspace.onboardingHeader.eyebrow, "Begeleide start");
  assert.equal(copy.nav.automation, "Automatisering");
  assert.equal(copy.traderProfile.onboardingOverview.steps.bot.title, "Automatisering");
});

test("the completed owner briefing is read from the server after refresh", () => {
  const ready = { first_dashboard_context: {
    is_first_dashboard: true,
    response_source: "cached_ai",
    generation_status: "ready",
  } };
  assert.equal(firstBriefingPhase(ready.first_dashboard_context), "saved");
  assert.equal(canCacheMissionControl(ready), false);
  assert.equal(canCacheMissionControl({ summary: { headline: "Other dashboard" } }), true);
  assert.equal(canCacheMissionControl({ first_dashboard_context: {
    is_first_dashboard: true,
    response_source: "stale_while_revalidate",
    generation_status: "stale_while_revalidate",
  } }), false);
});
