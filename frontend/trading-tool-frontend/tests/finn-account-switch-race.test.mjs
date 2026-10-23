import test from "node:test";
import assert from "node:assert/strict";

import {
  normalizeScopedAssetSymbol,
  resolveFinnBotContextSymbol,
  resolveFinnContextSymbol,
  resolveScopedAssetStatus,
  shouldBlockFinnSubmission,
} from "../lib/finnAssetIsolation.js";

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

test("direct /bot route never falls back to BTC when no user-scoped symbol is resolved", () => {
  assert.equal(normalizeScopedAssetSymbol(" btc "), "BTC");
  assert.equal(
    resolveFinnContextSymbol({ urlSymbol: "", activeSetupSymbol: undefined, selectedAsset: null }),
    null,
  );
});
