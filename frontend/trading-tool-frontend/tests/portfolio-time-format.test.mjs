import assert from "node:assert/strict";
import test from "node:test";

import { PORTFOLIO_TIME_OPTIONS } from "../lib/portfolioDateTime.mjs";

test("Portfolio formats source moments with an explicit Amsterdam time zone", () => {
  const sourceMoment = new Date("2026-11-09T09:00:00Z");
  for (const locale of ["nl-NL", "en-US"]) {
    const formatted = new Intl.DateTimeFormat(locale, PORTFOLIO_TIME_OPTIONS).format(sourceMoment);
    assert.match(formatted, /2026/);
    assert.match(formatted, /10:00/);
  }
});
