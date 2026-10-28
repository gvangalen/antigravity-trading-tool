import test from "node:test";
import assert from "node:assert/strict";
import { getBotApiErrorMessage } from "../lib/bot/botApiErrorMessage.mjs";

test("bot activation shows the server's actionable validation reason", () => {
  assert.equal(getBotApiErrorMessage({
    message: "API request failed",
    body: JSON.stringify({ detail: "Koppel eerst een exchange voordat deze live bot wordt geactiveerd." }),
  }, "Botstatus bijwerken mislukt."), "Koppel eerst een exchange voordat deze live bot wordt geactiveerd.");
  assert.equal(getBotApiErrorMessage({
    message: "API request failed",
    body: JSON.stringify({ detail: { code: "BOT_RISK_ACK_REQUIRED", message: "Bevestig deze wijziging bewust." } }),
  }, "Botstatus bijwerken mislukt."), "Bevestig deze wijziging bewust.");
});

test("unexpected response body uses localized fallback", () => {
  assert.equal(getBotApiErrorMessage({ message: "API request failed", body: "<html>error</html>" }, "Kon bot niet hervatten."), "Kon bot niet hervatten.");
});

test("manual order preview shows the server's specific 409 explanation", () => {
  assert.equal(getBotApiErrorMessage({
    status: 409, message: "API request failed",
    body: JSON.stringify({ detail: {
      code: "PAPER_SETUP_MATCH_REQUIRED",
      message: "Benchmark 36,7 ligt onder minimum 61. Deze Paper-koop wacht.",
    } }),
  }, "Preview mislukt."), "Benchmark 36,7 ligt onder minimum 61. Deze Paper-koop wacht.");
});
