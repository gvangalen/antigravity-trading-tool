import test from "node:test";
import assert from "node:assert/strict";
import { finnSubmissionLocale } from "../lib/finnChatLocale.mjs";

test("chat submission uses the language already displayed after a UI switch", () => {
  assert.equal(finnSubmissionLocale("nl", "de"), "de");
  assert.equal(finnSubmissionLocale("de", "nl-NL"), "nl");
  assert.equal(finnSubmissionLocale("nl", "en-US"), "en");
});

test("chat submission falls back to the configured locale without a document language", () => {
  assert.equal(finnSubmissionLocale("de", ""), "de");
  assert.equal(finnSubmissionLocale("nl", "unsupported"), "nl");
});
