import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";

import { formatDcaSchedule } from "../lib/bot/dcaSchedule.mjs";

const nl = JSON.parse(fs.readFileSync(new URL("../dictionaries/nl.json", import.meta.url), "utf8"));
const copy = nl.botPage.form;

test("saved monthly DCA cadence is distinct from its 1D chart timeframe", () => {
  assert.equal(formatDcaSchedule({
    setup_type: "dca", timeframe: "1D", dca_frequency: "monthly", dca_month_day: 5,
  }, copy), "maandelijks op dag 5");
  assert.equal(formatDcaSchedule({
    setup_type: "dca", timeframe: "1D", dca_frequency: "weekly", dca_day: "6",
  }, copy), "elke zaterdag");
  assert.equal(formatDcaSchedule({
    setup_type: "trade", timeframe: "1D", dca_frequency: "monthly", dca_month_day: 5,
  }, copy), "");
});
