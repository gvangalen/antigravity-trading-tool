import test from "node:test";
import assert from "node:assert/strict";
import { normalizeDcaWeekday } from "../lib/setup/dcaWeekday.mjs";

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
