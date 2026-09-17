import assert from "node:assert/strict";
import test from "node:test";

import { matchesSearchQuery } from "../lib/searchTerms.js";

const marketVolume = ["Relatief volume", "market_volume", "volume", "marktvolume", "market volume", "Markt Volumen"];
const priceChange = ["Prijsverandering 24 uur", "change_24h", "prijs 24h", "price 24h", "kurs 24h"];

test("market onboarding search matches localized labels, canonical names and aliases", () => {
  for (const query of ["Volume", "market", "marktvolume", "Markt Volumen"]) {
    assert.equal(matchesSearchQuery(query, marketVolume), true, query);
  }
  for (const query of ["Prijs", "price", "24h", "Kurs"]) {
    assert.equal(matchesSearchQuery(query, priceChange), true, query);
  }
});

test("search normalization is case and diacritic insensitive", () => {
  assert.equal(matchesSearchQuery("anderung", ["Änderung 24H"]), true);
});
