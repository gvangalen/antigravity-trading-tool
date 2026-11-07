import assert from "node:assert/strict";
import test from "node:test";

import {
  FINN_ASSETS,
  buildExactPairOptions,
  closeFeedDiscussionIfCurrent,
  getCommandTokens,
  getDefaultIndicatorCategory,
  isDirectCommandSearchMode,
  isExactMarketInWatchlist,
  matchesCommandQuery,
  normalizeCommandText,
  openFinnContext,
  resolveFeedDraftQuery,
  shouldAttachFeedContext,
  updateFeedDiscussionDraftIfCurrent,
} from "../lib/finnCommandSearch.js";

test("asset picker lists exact EUR and USDT markets as separate results", () => {
  const markets = {
    BTC: [
      { pair: "BTC/EUR", quote_currency: "EUR", status: "available" },
      { pair: "BTC/USDT", quote_currency: "USDT", status: "available" },
    ],
    ETH: [{ pair: "ETH/USDT", quote_currency: "USDT", status: "available" }],
  };
  assert.deepEqual(buildExactPairOptions(FINN_ASSETS, markets).map(({ market }) => market.pair),
    ["BTC/EUR", "BTC/USDT", "ETH/USDT"]);
  assert.deepEqual(buildExactPairOptions(FINN_ASSETS, markets, "btc/eur").map(({ market }) => market.pair),
    ["BTC/EUR"]);
});

test("normalizes accents and punctuation in natural commands", () => {
  assert.equal(normalizeCommandText("Öffne: Ethereum!"), "offne ethereum");
});

test("removes common command words before matching", () => {
  assert.deepEqual(getCommandTokens("Voeg RSI toe aan Technisch"), ["rsi", "technisch"]);
  assert.equal(matchesCommandQuery("RSI technische indicator", "Voeg RSI toe aan Technisch"), true);
});

test("matches asset commands without requiring an exact phrase", () => {
  assert.equal(matchesCommandQuery("ETH Ethereum", "Open Ethereum"), true);
  assert.equal(matchesCommandQuery("ETH Ethereum", "Wissel naar ETH"), true);
  assert.equal(matchesCommandQuery("BTC Bitcoin", "Zoek BTC"), true);
  assert.equal(matchesCommandQuery("BTC Bitcoin", "Open Ethereum"), false);
});

test("the same asset may be added for a second exact trading pair", () => {
  const watchlist = [{ symbol: "BTC", market_id: 12, pair: "BTC/USDT" }];
  assert.equal(isExactMarketInWatchlist(watchlist, 12), true);
  assert.equal(isExactMarketInWatchlist(watchlist, 13), false);
  assert.equal(isExactMarketInWatchlist([...watchlist, { symbol: "BTC", market_id: 13 }], 13), true);
});

test("matches workspace navigation commands", () => {
  assert.equal(matchesCommandQuery("plan Mijn Plan werkruimte", "Ga naar Mijn Plan"), true);
});

test("chooses the indicator category from the active workspace", () => {
  assert.equal(getDefaultIndicatorCategory("/macro"), "macro");
  assert.equal(getDefaultIndicatorCategory("/market"), "market");
  assert.equal(getDefaultIndicatorCategory("/asset"), "technical");
});

test("opens a feed item as an explicit chat draft with its exact event identity", () => {
  const previousWindow = globalThis.window;
  const previousCustomEvent = globalThis.CustomEvent;
  let dispatched;
  globalThis.window = { dispatchEvent: (event) => { dispatched = event; } };
  globalThis.CustomEvent = class {
    constructor(type, options) {
      this.type = type;
      this.detail = options.detail;
    }
  };
  try {
    openFinnContext({
      query: " Bespreek BTC Full Base ",
      context: { feed_item_id: "feed-plan-b" },
      autoSubmit: false,
    });
    assert.equal(dispatched.type, "finn-command-search:open");
    assert.deepEqual(dispatched.detail, {
      mode: "chat",
      query: "Bespreek BTC Full Base",
      context: { feed_item_id: "feed-plan-b" },
      autoSubmit: false,
    });
  } finally {
    globalThis.window = previousWindow;
    globalThis.CustomEvent = previousCustomEvent;
  }
});

test("a chat handoff does not search assets, pages or indicators", () => {
  assert.equal(isDirectCommandSearchMode("chat"), false);
  assert.equal(isDirectCommandSearchMode("all"), true);
  assert.equal(isDirectCommandSearchMode("asset"), true);
  assert.equal(isDirectCommandSearchMode("indicator"), true);
});

test("feed identity follows the first explicit question even when its draft is rewritten", () => {
  const request = { nonce: 8, query: "Bespreek QA Plan B", context: { feed_item_id: "feed-b" } };
  assert.equal(shouldAttachFeedContext(request, "Bespreek QA Plan B", null), true);
  assert.equal(shouldAttachFeedContext(request, "Bespreek QA Plan B", 8), false);
  assert.equal(shouldAttachFeedContext(request, "Is 4H opgeslagen of nog een voorstel?", null), true);
  assert.equal(shouldAttachFeedContext(request, "Is 4H opgeslagen of nog een voorstel?", 8), false);
  assert.equal(shouldAttachFeedContext(request, "", null), false);
});

test("a second feed selection keeps its own draft even if restored chat clears parent input", () => {
  const first = { mode: "chat", nonce: 8, query: "Bespreek Plan A",
    context: { feed_item_id: "feed-a" } };
  const second = { mode: "chat", nonce: 9, query: "Bespreek Plan B",
    context: { feed_item_id: "feed-b" } };
  assert.equal(resolveFeedDraftQuery(first, "", null, null), "Bespreek Plan A");
  assert.equal(resolveFeedDraftQuery(second, "", null, 8), "Bespreek Plan B");
  assert.equal(resolveFeedDraftQuery(second, "", { nonce: 9, value: "Waarom B?" }, 8), "Waarom B?");
  assert.equal(resolveFeedDraftQuery(second, "", null, 9), "");
});

test("a late close or draft change from A cannot replace selected discussion B", () => {
  const planB = { request: { nonce: "feed:b:2", context: { feed_item_id: "feed-b" } },
    draft: "Bespreek Plan B" };
  assert.equal(closeFeedDiscussionIfCurrent(planB, "feed:a:1"), planB);
  assert.equal(updateFeedDiscussionDraftIfCurrent(planB, "feed:a:1", ""), planB);
  assert.deepEqual(updateFeedDiscussionDraftIfCurrent(planB, "feed:b:2", "Waarom B?"),
    { ...planB, draft: "Waarom B?" });
  assert.equal(closeFeedDiscussionIfCurrent(planB, "feed:b:2"), null);
});
