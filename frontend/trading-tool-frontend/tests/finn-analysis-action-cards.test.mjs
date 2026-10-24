import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = fs.readFileSync(path.join(root, "components/ui/AIAssistant.jsx"), "utf8");
const watchlistHook = fs.readFileSync(path.join(root, "hooks/useWatchlist.js"), "utf8");

test("analysis proposals render operation-specific human cards", () => {
  assert.match(source, /const isWatchlistAction = \["watchlist_add", "watchlist_remove"\]/);
  assert.match(source, /const isIndicatorAction = \["create_indicator_configuration", "update_indicator_configuration", "delete_indicator_configuration"\]/);
  assert.match(source, /Aan watchlist toevoegen/);
  assert.match(source, /Indicator toevoegen/);
  assert.match(source, /Technisch bewijs/);
  assert.match(source, /Marktindicatoren/);
  assert.match(source, /aan je watchlist toegevoegd/);
  assert.match(source, /toegevoegd aan.*categoryLabel/);
});

test("analysis proposal cards suppress the generic inline action card", () => {
  assert.match(source, /"watchlist_add", "watchlist_remove",\s*"create_indicator_configuration"/);
  assert.match(source, /if \(actionOnly\.length === 0 \|\| message\.draft \|\| hasDedicatedDraftCard\) return null/);
});

test("a confirmed FINN watchlist change invalidates the shared watchlist before Analyse reads it", () => {
  assert.match(source, /\["succeeded", "already_executed"\]\.includes\(execution\.status\)/);
  assert.match(source, /operationId === "watchlist_add" \|\| operationId === "watchlist_remove"[\s\S]*?invalidateWatchlist\(\)/);
  assert.match(watchlistHook, /function invalidateWatchlist\(\)[\s\S]*?markCachedResourceStale\(WATCHLIST_CACHE_KEY\)[\s\S]*?dispatchEvent\(new CustomEvent\("watchlist-updated"\)\)/);
});
