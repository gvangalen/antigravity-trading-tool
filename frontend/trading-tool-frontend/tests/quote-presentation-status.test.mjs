import assert from "node:assert/strict";
import test from "node:test";

import { quotePresentationStatus } from "../lib/workspace/quotePresentationStatus.mjs";

const stock = {
  stale: true,
  assetClass: "stock",
  marketRegion: "us",
  timeZone: "America/New_York",
};

test("Friday's US stock quote is labeled as the last available quote on Saturday", () => {
  assert.equal(quotePresentationStatus({
    ...stock,
    sourceAt: "2026-10-23T19:59:00Z",
    now: "2026-10-24T12:00:00Z",
  }), "closed_session");
});

test("an older stock quote remains stale even on a closed-market weekend", () => {
  assert.equal(quotePresentationStatus({
    ...stock,
    sourceAt: "2026-10-22T19:59:00Z",
    now: "2026-10-24T12:00:00Z",
  }), "stale");
});

test("Friday's closing quote is the last available US stock quote before Monday's regular session", () => {
  assert.equal(quotePresentationStatus({
    ...stock,
    sourceAt: "2026-10-30T19:59:00Z",
    now: "2026-11-02T12:00:00Z",
  }), "closed_session");
  assert.equal(quotePresentationStatus({
    ...stock,
    sourceAt: "2026-10-29T19:59:00Z",
    now: "2026-11-02T12:00:00Z",
  }), "stale");
  assert.equal(quotePresentationStatus({
    ...stock,
    sourceAt: "2026-10-30T19:59:00Z",
    now: "2026-11-02T15:00:00Z",
  }), "stale");
  assert.equal(quotePresentationStatus({
    ...stock, assetClass: "index",
    sourceAt: "2026-10-30T19:59:00Z",
    now: "2026-11-02T12:00:00Z",
  }), "closed_session");
});

test("a stale stock quote during the open week remains stale", () => {
  assert.equal(quotePresentationStatus({
    ...stock,
    sourceAt: "2026-10-23T19:59:00Z",
    now: "2026-10-26T15:00:00Z",
  }), "stale");
});

test("crypto and unknown exchanges do not get a closed-market label", () => {
  const sourceAt = "2026-10-23T19:59:00Z";
  const now = "2026-10-24T12:00:00Z";
  assert.equal(quotePresentationStatus({ ...stock, assetClass: "crypto", sourceAt, now }), "stale");
  assert.equal(quotePresentationStatus({ ...stock, marketRegion: "global", sourceAt, now }), "stale");
  assert.equal(quotePresentationStatus({ ...stock, stale: false, sourceAt, now }), "closed_session");
  assert.equal(quotePresentationStatus({ ...stock, stale: false, sourceAt, now: "2026-10-26T15:00:00Z" }), "current");
});
