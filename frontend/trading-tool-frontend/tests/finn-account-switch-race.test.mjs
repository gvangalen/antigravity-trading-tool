import test from "node:test";
import assert from "node:assert/strict";

import {
  normalizeScopedAssetSymbol,
  resolveFinnBotPageContext,
  resolveFinnBotContextSymbol,
  resolveFinnContextSymbol,
  resolveScopedAssetStatus,
  shouldBlockFinnSubmission,
} from "../lib/finnAssetIsolation.js";
import { matchesWorkspaceAsset } from "../lib/workspace/workspaceAssetScope.mjs";

test("asset switch cannot show an AAPL workspace beneath a BTC heading", () => {
  const periods = { market: "day", macro: "day", technical: "day" };
  const previousWorkspace = { symbol: "AAPL", periods, quote: { price: 347.73 } };
  const currentWorkspace = { symbol: "BTC", periods, quote: { price: 80606 } };
  assert.equal(matchesWorkspaceAsset(previousWorkspace, "BTC", periods), false);
  assert.equal(matchesWorkspaceAsset(currentWorkspace, "BTC", periods), true);
  assert.equal(matchesWorkspaceAsset(currentWorkspace, "BTC", { ...periods, technical: "week" }), false);
  assert.equal(matchesWorkspaceAsset(null, "BTC"), false);
});

test("BTC-user logout to AAPL-user direct /bot keeps FINN blocked during hydration race", () => {
  const btcUserState = {
    isPublicAuthRoute: false,
    sessionChecked: true,
    isAuthenticated: true,
    preferencesHydrated: true,
    selectedAsset: "BTC",
  };
  assert.equal(resolveScopedAssetStatus(btcUserState), "resolved");
  assert.equal(
    resolveFinnContextSymbol({ urlSymbol: null, activeSetupSymbol: null, selectedAsset: "BTC" }),
    "BTC",
  );

  const afterLogout = {
    isPublicAuthRoute: false,
    sessionChecked: true,
    isAuthenticated: false,
    preferencesHydrated: false,
    selectedAsset: null,
  };
  assert.equal(resolveScopedAssetStatus(afterLogout), "unconfigured");
  assert.equal(
    resolveFinnContextSymbol({ urlSymbol: null, activeSetupSymbol: null, selectedAsset: null }),
    null,
  );

  const aaplHydratingOnBotRoute = {
    isPublicAuthRoute: false,
    sessionChecked: true,
    isAuthenticated: true,
    preferencesHydrated: false,
    selectedAsset: null,
  };
  const hydratingStatus = resolveScopedAssetStatus(aaplHydratingOnBotRoute);
  assert.equal(hydratingStatus, "loading");
  assert.equal(
    resolveFinnContextSymbol({ urlSymbol: null, activeSetupSymbol: null, selectedAsset: null }),
    null,
  );
  assert.equal(
    shouldBlockFinnSubmission({ isAuthenticated: true, assetStatus: hydratingStatus }),
    true,
  );

  const aaplResolvedFromUrlDuringHydration = {
    ...aaplHydratingOnBotRoute,
    selectedAsset: "AAPL",
  };
  assert.equal(resolveScopedAssetStatus(aaplResolvedFromUrlDuringHydration), "resolved");
  assert.equal(
    shouldBlockFinnSubmission({ isAuthenticated: true, assetStatus: "resolved" }),
    false,
  );

  const aaplHydrated = {
    ...aaplHydratingOnBotRoute,
    preferencesHydrated: true,
    selectedAsset: "AAPL",
  };
  assert.equal(resolveScopedAssetStatus(aaplHydrated), "resolved");
  assert.equal(
    resolveFinnContextSymbol({ urlSymbol: null, activeSetupSymbol: null, selectedAsset: "AAPL" }),
    "AAPL",
  );
});

test("selected bot determines FINN asset even when the route still names a previous bot", () => {
  const ethBot = { symbol: "ETH", strategy: { setup: { symbol: "ETH" } } };
  assert.equal(resolveFinnBotContextSymbol({ bot: ethBot, routeSymbol: "BTC", selectedAsset: "BTC" }), "ETH");
  assert.equal(resolveFinnBotContextSymbol({ bot: null, routeSymbol: "BTC", selectedAsset: "ETH" }), "BTC");
});

test("visible bot URL outranks a stale bot provider and old asset selection", () => {
  const staleAaplBot = { id: 71, symbol: "AAPL" };
  const context = resolveFinnBotPageContext({
    search: "?symbol=BTC&bot_id=132",
    activeBot: staleAaplBot,
    selectedAsset: "AAPL",
  });
  assert.equal(context.botId, 132);
  assert.equal(context.bot, null);
  assert.equal(context.symbol, "BTC");
});

test("direct /bot route never falls back to BTC when no user-scoped symbol is resolved", () => {
  assert.equal(normalizeScopedAssetSymbol(" btc "), "BTC");
  assert.equal(
    resolveFinnContextSymbol({ urlSymbol: "", activeSetupSymbol: undefined, selectedAsset: null }),
    null,
  );
});
