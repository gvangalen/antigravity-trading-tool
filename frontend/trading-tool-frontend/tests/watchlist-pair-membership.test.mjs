import assert from "node:assert/strict";
import test from "node:test";
import { reconcileWatchlistMembership, watchlistRowKey } from "../lib/workspace/watchlistMembership.mjs";

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
