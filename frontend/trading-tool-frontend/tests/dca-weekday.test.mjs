import test from "node:test";
import assert from "node:assert/strict";
import { normalizeDcaWeekday } from "../lib/setup/dcaWeekday.mjs";
import { initialSetupFormState } from "../lib/setup/setupFormState.mjs";

test("saved ISO weekday five selects Friday in the setup editor", () => {
  assert.equal(normalizeDcaWeekday("5"), "friday");
  assert.equal(normalizeDcaWeekday(5), "friday");
  assert.equal(normalizeDcaWeekday("friday"), "friday");
});

test("all saved ISO weekdays map to the editor choices", () => {
  const days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
  days.forEach((day, index) => assert.equal(normalizeDcaWeekday(String(index + 1)), day));
  assert.equal(normalizeDcaWeekday(null), null);
  assert.equal(normalizeDcaWeekday("9"), "");
});

test("existing and newly saved Friday plans initialize the editor on Friday", () => {
  for (const id of [80, 82]) {
    const form = initialSetupFormState({
      id, name: `ETH Friday ${id}`, symbol: "ETH", setup_type: "dca",
      timeframe: "1D", dca_frequency: "weekly", dca_day: "5",
    });
    assert.equal(form.dcaDay, "friday");
    assert.equal(form.dcaFrequency, "weekly");
  }
  assert.equal(initialSetupFormState().dcaDay, "monday");
});
