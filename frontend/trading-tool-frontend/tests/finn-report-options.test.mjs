import test from "node:test";
import assert from "node:assert/strict";

import {
  FALLBACK_FINN_REPORT_OPTIONS,
  getFinnReportOptions,
  resolveActiveFinnReportOption,
  resolveFinnReportOptions,
} from "../lib/report/finnReportOptions.mjs";

test("getFinnReportOptions uses FINN report keys instead of standard report keys", () => {
  const options = getFinnReportOptions({
    today: { label: "Vandaag", prompt: "today prompt" },
    week: { label: "Weekreflectie", prompt: "week prompt" },
    blocked: { label: "Geblokkeerd", prompt: "blocked prompt" },
    behavior: { label: "30 dagen gedrag", prompt: "behavior prompt" },
    daily: { label: "Should not be used", prompt: "wrong prompt" },
  });

  assert.deepEqual(
    options.map((option) => option.key),
    ["today", "week", "blocked", "behavior"],
  );
});

test("resolveFinnReportOptions falls back when config is missing or incomplete", () => {
  assert.deepEqual(resolveFinnReportOptions({}), FALLBACK_FINN_REPORT_OPTIONS);
  assert.deepEqual(
    resolveFinnReportOptions({
      today: { label: "Vandaag" },
    }),
    FALLBACK_FINN_REPORT_OPTIONS,
  );
});

test("resolveActiveFinnReportOption returns the requested FINN tab or the first safe fallback", () => {
  const options = resolveFinnReportOptions({
    today: { label: "Vandaag", prompt: "today prompt" },
    week: { label: "Weekreflectie", prompt: "week prompt" },
  });

  assert.equal(resolveActiveFinnReportOption(options, "week").key, "week");
  assert.equal(resolveActiveFinnReportOption(options, "blocked").key, "today");
  assert.equal(resolveActiveFinnReportOption([], "blocked").key, "today");
});
