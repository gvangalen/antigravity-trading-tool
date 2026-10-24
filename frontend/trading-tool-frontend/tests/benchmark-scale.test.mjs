import assert from "node:assert/strict";
import test from "node:test";
import { benchmarkScaleBands, benchmarkSetupSessionKey, benchmarkSetupView, selectedBenchmarkSetupMatch, withSelectedBenchmarkSetup } from "../lib/setup/benchmarkScale.mjs";

test("benchmark scale follows the saved setup presets without gaps", () => {
  const bands = benchmarkScaleBands();
  assert.equal(bands[0].start, 0);
  assert.equal(bands.at(-1).end, 100);
  for (let index = 1; index < bands.length; index += 1) {
    assert.equal(bands[index].start, bands[index - 1].end);
  }
  assert.deepEqual(bands.map(({ min, max }) => [min, max]), [[0, 25], [26, 45], [46, 60], [61, 75], [76, 100]]);
});

test("a verified setup boundary uses the displayed whole-point benchmark", () => {
  const match = {
    conditions: { benchmark: { minimum: 26, maximum: 45 } },
    components: { benchmark: { score: 26 } },
    status: "matches",
  };
  const view = benchmarkSetupView(25.6, match);
  assert.equal(view.currentBand.id, "pressure");
  assert.equal(view.preset.id, "pressure");
  assert.equal(view.zone.start, 25.5);
  assert.equal(view.zone.end, 45.5);
  assert.equal(view.status, "matches");
  assert.equal(benchmarkSetupView(50, match).status, "updating");
});

test("missing score or absent setup condition never becomes a match", () => {
  const match = { conditions: { benchmark: { minimum: 0, maximum: 25 } }, status: "matches" };
  assert.equal(benchmarkSetupView(null, match).status, "insufficient_data");
  assert.equal(benchmarkSetupView(null, match).currentBand, null);
  assert.equal(benchmarkSetupView(50, { conditions: {}, status: "unconfigured" }).zone, null);
  assert.equal(benchmarkSetupView(50, { conditions: {}, status: "unconfigured" }).status, "no_condition");
  assert.equal(benchmarkSetupView(50, null).status, "no_setup");
});

test("custom and one-sided setup bounds use their saved range", () => {
  const custom = {
    conditions: { benchmark: { minimum: 18, maximum: 47 } },
    components: { benchmark: { score: 50 } },
    status: "outside_conditions",
  };
  const view = benchmarkSetupView(50, custom);
  assert.equal(view.preset, null);
  assert.deepEqual(view.zone, { start: 17.5, end: 47.5 });
  assert.equal(view.status, "outside_conditions");
  assert.deepEqual(benchmarkSetupView(80, {
    conditions: { benchmark: { minimum: 70, maximum: null } },
    components: { benchmark: { score: 80 } },
    status: "matches",
  }).zone, { start: 69.5, end: 100 });
});

test("the chosen setup survives refresh in the URL without replacing asset context", () => {
  const query = withSelectedBenchmarkSetup("symbol=BTC&tab=market&variant=v3", 42);
  const params = new URLSearchParams(query);
  assert.equal(params.get("symbol"), "BTC");
  assert.equal(params.get("tab"), "market");
  assert.equal(params.get("benchmarkSetup"), "42");
  assert.equal(new URLSearchParams(withSelectedBenchmarkSetup(query, null)).has("benchmarkSetup"), false);
  assert.equal(new URLSearchParams(withSelectedBenchmarkSetup(query, "not-an-id")).has("benchmarkSetup"), false);
});

test("a remembered setup selection is isolated by authenticated owner and asset", () => {
  assert.equal(benchmarkSetupSessionKey(17, "btc"), "benchmarkSetup:17:BTC");
  assert.equal(benchmarkSetupSessionKey(17, "ETH"), "benchmarkSetup:17:ETH");
  assert.equal(benchmarkSetupSessionKey(18, "BTC"), "benchmarkSetup:18:BTC");
  assert.equal(benchmarkSetupSessionKey(null, "BTC"), null);
  assert.equal(benchmarkSetupSessionKey(17, "BTC?symbol=ETH"), null);
});

test("returning from another page restores only a setup in the owner's loaded list", () => {
  const ownerMatches = [{ setup_id: 10, is_best: true }, { setup_id: 20, is_best: false }];
  assert.equal(selectedBenchmarkSetupMatch(ownerMatches, 20).setup_id, 20);
  assert.equal(selectedBenchmarkSetupMatch(ownerMatches, 999).setup_id, 10);
  assert.equal(selectedBenchmarkSetupMatch([], 20), null);
});
