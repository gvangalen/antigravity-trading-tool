import assert from "node:assert/strict";
import test from "node:test";
import {
  createWatchlistRequestTracker,
  ownerScopedWatchlistValues,
  reconcileWatchlistMembership,
  watchlistCacheKey,
  watchlistRowKey,
} from "../lib/workspace/watchlistMembership.mjs";
import { getCachedResourceSnapshot, setCachedResourceData } from "../lib/clientDataCache.js";

const eur = { symbol: "BTC", market_id: 41, quote_currency: "EUR" };
const usdt = { symbol: "BTC", market_id: 42, quote_currency: "USDT" };

test("switching the selected pair cannot remove another saved pair", () => {
  const rows = reconcileWatchlistMembership(
    [eur, usdt],
    [{ ...usdt, price: 75000 }],
    [{ symbol: "BTC", marketId: 41, lastPrice: "€ 68.000" }],
  );

  assert.deepEqual(rows.map(({ saved }) => watchlistRowKey(saved)), ["market:41", "market:42"]);
  assert.equal(rows[0].workspace, null);
  assert.equal(rows[0].previous.lastPrice, "€ 68.000");
  assert.equal(rows[1].workspace.price, 75000);
});

test("adding and removing a pair follows saved membership immediately", () => {
  const staleWorkspace = [{ ...usdt, price: 75000 }];
  const added = reconcileWatchlistMembership([eur, usdt], staleWorkspace);
  assert.deepEqual(added.map(({ saved }) => watchlistRowKey(saved)), ["market:41", "market:42"]);
  assert.equal(added[0].workspace, null);

  const removed = reconcileWatchlistMembership([usdt], [{ ...eur, price: 68000 }, ...staleWorkspace]);
  assert.deepEqual(removed.map(({ saved }) => watchlistRowKey(saved)), ["market:42"]);
});

test("saved pairs from one account cannot populate another account's cache", () => {
  const firstKey = watchlistCacheKey(701);
  const secondKey = watchlistCacheKey(702);
  setCachedResourceData(firstKey, [eur, usdt]);

  assert.notEqual(firstKey, secondKey);
  assert.deepEqual(getCachedResourceSnapshot(secondKey, []).data, []);
  assert.equal(watchlistCacheKey(null), null);
});

test("an older watchlist response cannot replace a newer add or remove", async () => {
  const tracker = createWatchlistRequestTracker();
  const key = watchlistCacheKey(701);
  let finishOld;
  const oldResponse = new Promise((resolve) => { finishOld = resolve; });
  const oldGeneration = tracker.next(key);
  const newGeneration = tracker.next(key);
  const applied = [];

  const oldCompletion = oldResponse.then((rows) => {
    if (tracker.isCurrent(key, oldGeneration)) applied.push(rows);
  });
  if (tracker.isCurrent(key, newGeneration)) applied.push([eur, usdt]);
  finishOld([usdt]);
  await oldCompletion;

  assert.deepEqual(applied, [[eur, usdt]]);
});

test("an account switch hides old rows and rejects its late response", () => {
  const tracker = createWatchlistRequestTracker();
  const firstKey = watchlistCacheKey(701);
  const secondKey = watchlistCacheKey(702);
  const firstGeneration = tracker.next(firstKey);
  tracker.next(firstKey);
  tracker.next(secondKey);

  assert.equal(tracker.isCurrent(firstKey, firstGeneration), false);
  assert.deepEqual(ownerScopedWatchlistValues({ ownerId: 701, rows: [eur] }, 702, "rows"), []);
  assert.deepEqual(ownerScopedWatchlistValues({ ownerId: 702, rows: [usdt] }, 702, "rows"), [usdt]);
});
