import test from "node:test";
import assert from "node:assert/strict";

import {
  normalizeScopedAssetSymbol,
  resolveFinnBotPageContext,
  resolveFinnBotContextSymbol,
  resolveFinnContextSymbol,
  resolveFinnSubmissionContext,
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

test("sending from the visible bot ignores a stale chat asset and prior bot flow", () => {
  const livePageContext = {
    page: "/bot", bot_id: 132, symbol: "BTC", setup_id: 11, strategy_id: 22,
  };
  const submitted = resolveFinnSubmissionContext({
    pathname: "/bot", livePageContext,
    latestAssistantState: { current_flow: "read_bot", bot_id: 71, symbol: "AAPL" },
    commandContext: { bot_id: 71, symbol: "AAPL" },
    chatAssetOverride: "AAPL", locale: "nl",
  });
  assert.equal(submitted.bot_id, 132);
  assert.equal(submitted.symbol, "BTC");
  assert.equal(submitted.setup_id, 11);
  assert.equal(submitted.strategy_id, 22);
  assert.equal(submitted.locale, "nl");

  const noBot = resolveFinnSubmissionContext({
    pathname: "/bot", livePageContext: { page: "/bot", bot_id: null, symbol: "BTC" },
    latestAssistantState: { current_flow: "read_bot", bot_id: 71, symbol: "AAPL" },
  });
  assert.equal(noBot.bot_id, null);
  assert.equal(noBot.symbol, "BTC");
});

test("explicit bot review button keeps its named target instead of the open bot", () => {
  const submitted = resolveFinnSubmissionContext({
    pathname: "/bot",
    livePageContext: { page: "/bot", bot_id: 132, symbol: "BTC", strategy_id: 22 },
    commandContext: {
      bot_id: 71, bot_name: "AAPL Paper", symbol: "AAPL", strategy_id: 23,
      finn_subject_type: "bot",
    },
    query: "Beoordeel bot AAPL Paper en leg de risico's uit.",
    originalCommandQuery: "Beoordeel bot AAPL Paper en leg de risico's uit.",
    autoSubmitCommand: true,
    locale: "nl",
  });
  assert.equal(submitted.bot_id, 71);
  assert.equal(submitted.symbol, "AAPL");
  assert.equal(submitted.strategy_id, 23);

  const unrelated = resolveFinnSubmissionContext({
    pathname: "/bot",
    livePageContext: { page: "/bot", bot_id: 132, symbol: "BTC" },
    commandContext: {
      bot_id: 71, bot_name: "AAPL Paper", symbol: "AAPL", finn_subject_type: "bot",
    },
    query: "Welke bot heb ik hier open?",
  });
  assert.equal(unrelated.bot_id, 132);
  assert.equal(unrelated.symbol, "BTC");

  const edited = resolveFinnSubmissionContext({
    pathname: "/bot",
    livePageContext: { page: "/bot", bot_id: 132, symbol: "BTC" },
    commandContext: {
      bot_id: 71, bot_name: "AAPL Paper", symbol: "AAPL", finn_subject_type: "bot",
    },
    originalCommandQuery: "Beoordeel bot AAPL Paper en leg de risico's uit.",
    query: "Niet bot AAPL Paper; beoordeel deze bot op de pagina.",
    autoSubmitCommand: true,
  });
  assert.equal(edited.bot_id, 132);
  assert.equal(edited.symbol, "BTC");
});

test("direct /bot route never falls back to BTC when no user-scoped symbol is resolved", () => {
  assert.equal(normalizeScopedAssetSymbol(" btc "), "BTC");
  assert.equal(
    resolveFinnContextSymbol({ urlSymbol: "", activeSetupSymbol: undefined, selectedAsset: null }),
    null,
  );
});
