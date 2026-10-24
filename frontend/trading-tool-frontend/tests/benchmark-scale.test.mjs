import assert from "node:assert/strict";
import test from "node:test";
import { benchmarkScaleBands, benchmarkSetupView } from "../lib/setup/benchmarkScale.mjs";

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
