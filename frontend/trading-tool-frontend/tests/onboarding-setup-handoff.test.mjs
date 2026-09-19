import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  getActiveSetupId,
  getSetupId,
  normalizeSetupSaveResponse,
} from "../lib/setup/activeSetup.js";

const readSource = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("uses setup_id from the real active-setup response for onboarding strategy handoff", async () => {
  const activeResponse = {
    setup_id: 326,
    name: "BTC 4H Trade",
    symbol: "BTC",
    timeframe: "4H",
    setup_type: "trade",
  };

  assert.equal(getActiveSetupId(activeResponse), 326);
  assert.equal(getSetupId(activeResponse), 326);
  assert.equal(getActiveSetupId({ id: 326 }), null);

  const page = await readSource("app/onboarding/plan/page.jsx");
  assert.match(page, /getActiveSetupId\(setupCandidate\)/);
  assert.match(page, /setup_id:\s*getSetupId\(savedSetup\)/);
  assert.match(page, /normalizeSetupSaveResponse\(response\)/);
  assert.doesNotMatch(page, /setupCandidate\.id/);
  assert.doesNotMatch(page, /savedSetup\.id/);
});

test("the real create envelope preserves setup_id for onboarding consumers", async () => {
  const backendResponse = {
    status: "success",
    setup_id: 326,
    setup: { id: 326, name: "BTC Swing", timeframe: "4H" },
  };

  const savedSetup = normalizeSetupSaveResponse(backendResponse);
  assert.equal(savedSetup.setup_id, 326);
  assert.equal(getSetupId(savedSetup), 326);

  const form = await readSource("components/setup/SetupForm.jsx");
  assert.match(form, /normalizeSetupSaveResponse\(savedSetup\)/);
});

test("setup editor keeps stock assets instead of silently falling back to BTC", async () => {
  const form = await readSource("components/setup/SetupForm.jsx");
  assert.match(form, /selectedAsset, availableAssets/);
  assert.match(form, /initialData\?\.symbol/);
  assert.match(form, /assetOptions\.map/);
  assert.doesNotMatch(form, /<option value="BTC">/);
});

test("the onboarding consumer uses the real backend response without reading a legacy id field", async () => {
  const backendResponse = {
    setup_id: 771,
    setup: { name: "BTC Swing", symbol: "BTC", timeframe: "4H" },
  };
  const setup = normalizeSetupSaveResponse(backendResponse);

  assert.equal(getSetupId(setup), 771);
  assert.equal(setup.id, undefined);

  const page = await readSource("app/onboarding/plan/page.jsx");
  assert.match(page, /setup_id:\s*getSetupId\(savedSetup\)/);
  assert.doesNotMatch(page, /savedSetup\.id/);
});

test("keeps compact onboarding score ranges backend-owned", async () => {
  const page = await readSource("app/onboarding/plan/page.jsx");
  assert.doesNotMatch(page, /min_macro_score/);
  assert.doesNotMatch(page, /max_technical_score/);
});

test("setup management duplicates through the established creation form without copying an id", async () => {
  const workflow = await readSource("components/workflows/MyPlanWorkflow.jsx");
  assert.match(workflow, /const duplicateSetup = \(setup\)/);
  assert.match(workflow, /type: "new-setup"/);
  assert.match(workflow, /setup_id: undefined/);
  assert.match(workflow, /duplicateSetup/);
});

test("all active-setup consumers preserve setup_id as the canonical identifier", async () => {
  const [brain, assistant, provider, setupApi, strategies, strategyForm] = await Promise.all([
    readSource("components/dashboard/TradingBrain.jsx"),
    readSource("components/ui/AIAssistant.jsx"),
    readSource("app/providers/SetupProvider.tsx"),
    readSource("lib/api/setups.js"),
    readSource("components/my-plan/StrategiesWorkspaceSection.jsx"),
    readSource("components/strategy/StrategyForm.jsx"),
  ]);

  assert.match(brain, /useSetupStrategy\(getActiveSetupId\(activeSetup\)\)/);
  assert.match(assistant, /setup_id:\s*getActiveSetupId\(activeSetup\)/);
  assert.match(provider, /normalizeSetupSaveResponse\(resActive\?\.active \?\? null\)/);
  assert.match(setupApi, /const normalizePublicSetup/);
  assert.match(strategies, /setup_id: getSetupId\(setup\)/);
  assert.match(strategyForm, /String\(getSetupId\(s\)\) === String\(form\.setup_id\)/);
  assert.match(strategyForm, /String\(getSetupId\(s\)\) === value/);
  assert.match(strategyForm, /key=\{getSetupId\(s\)\} value=\{getSetupId\(s\) \?\? ""\}/);
  assert.doesNotMatch(strategyForm, /String\(s\.id\) === String\(form\.setup_id\)/);
});

test("opening or saving a plan synchronizes its setup with the FINN workspace", async () => {
  const workflow = await readSource("components/workflows/MyPlanWorkflow.jsx");

  assert.match(workflow, /const \{ activeSetup, setActiveSetup \} = useActiveSetup\(\)/);
  assert.match(workflow, /setActiveSetup\(\{ \.\.\.setup, setup_id: setupId \}\)/);
  assert.match(workflow, /setActiveSetup\(\{ \.\.\.savedSetup, setup_id: setupId \}\)/);
});

test("onboarding hands the saved strategy to Automation and never renders a blank loading page", async () => {
  const [planPage, botPage] = await Promise.all([
    readSource("app/onboarding/plan/page.jsx"),
    readSource("app/(protected)/bot/page.jsx"),
  ]);

  assert.match(planPage, /action=new_bot/);
  assert.match(planPage, /strategy_id=/);
  assert.match(planPage, /savedStrategy\?\.strategy_id \?\? savedStrategy\?\.id/);
  assert.doesNotMatch(botPage, /fallback=\{<div className="min-h-screen bg-\[#020617\]" \/>\}/);
  assert.match(botPage, /aria-busy="true"/);
  assert.match(botPage, /animate-pulse/);
});

test("plan management uses setup_id for strategy, delete, and active-plan handoffs", async () => {
  const workflow = await readSource("components/workflows/MyPlanWorkflow.jsx");

  assert.match(workflow, /const setupId = getSetupId\(setup\)/);
  assert.match(workflow, /deleteSetup\(getSetupId\(plan\.setup\)\)/);
  assert.match(workflow, /setup_id: getSetupId\(drawer\.setup\)/);
  assert.match(workflow, /normalizeId\(getSetupId\(plan\.setup\)\) === setupId/);
});

test("onboarding status updates are published to independently mounted surfaces", async () => {
  const [api, hook] = await Promise.all([
    readSource("lib/api/onboarding.js"),
    readSource("hooks/useOnboarding.js"),
  ]);

  assert.match(api, /ONBOARDING_STATUS_UPDATED_EVENT/);
  assert.match(api, /export function subscribeOnboardingStatus/);
  assert.match(api, /publishOnboardingStatus\(status\)/);
  assert.match(hook, /subscribeOnboardingStatus/);
});

test("analysis onboarding rehydrates the persisted asset only before an explicit replacement", async () => {
  const page = await readSource("app/onboarding/analysis/page.jsx");

  assert.match(page, /hydratedAssetSymbolRef/);
  assert.match(page, /status\?\.has_asset/);
  assert.match(page, /Do not re-hydrate the previous persisted asset/);
});

test("a persisted setup remains reachable while later onboarding phases are incomplete", async () => {
  const guard = await readSource("components/auth/AuthGuard.jsx");

  assert.match(guard, /canManageSavedSetup/);
  assert.match(guard, /pathname\.startsWith\("\/setup"\) && Boolean\(status\?\.has_setup\)/);
});
