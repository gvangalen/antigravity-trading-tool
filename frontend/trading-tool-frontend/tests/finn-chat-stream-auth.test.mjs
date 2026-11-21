import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { runInNewContext } from "node:vm";

const source = await readFile(new URL("../lib/api/ai.js", import.meta.url), "utf8");
const streamDeclaration = source.match(/export const assistantChatStream = async \([\s\S]*?\n\};/);
assert.ok(streamDeclaration, "FINN stream function exists");

function streamHarness({ refreshSuccess }) {
  const calls = [];
  const errors = [];
  let token = "expired";
  const context = {
    AbortController,
    TextDecoder,
    Date,
    Math,
    JSON,
    console: { warn() {}, error() {}, log() {} },
    setTimeout,
    API_BASE_URL: "http://localhost",
    activeAbortController: null,
    buildAuthHeaders: () => new Headers({ Authorization: `Bearer ${token}` }),
    apiRefresh: async () => {
      calls.push("refresh");
      if (refreshSuccess) token = "renewed";
      return { success: refreshSuccess };
    },
    fetch: async (_url, options) => {
      calls.push({ token: options.headers.authorization, trace: options.headers["x-trace-id"] });
      if (token === "expired") return { status: 401, ok: false };
      const data = new TextEncoder().encode('event: envelope\ndata: {"ok":true}\n\n');
      let read = false;
      return {
        status: 200,
        ok: true,
        body: { getReader: () => ({ read: async () => {
          if (read) return { done: true };
          read = true;
          return { done: false, value: data };
        } }) },
      };
    },
  };
  runInNewContext(`${streamDeclaration[0].replace("export const", "const")}\nglobalThis.stream = assistantChatStream;`, context);
  return { calls, errors, stream: context.stream };
}

test("FINN silently refreshes a 401 and resends the same request trace", async () => {
  const harness = streamHarness({ refreshSuccess: true });
  const envelopes = [];
  await harness.stream("Analyseer BTC", {}, [], () => {}, value => envelopes.push(value), value => harness.errors.push(value));
  assert.deepEqual(harness.calls.map(call => typeof call === "string" ? call : call.token), ["Bearer expired", "refresh", "Bearer renewed"]);
  assert.equal(harness.calls[0].trace, harness.calls[2].trace);
  assert.deepEqual(envelopes.map(value => value.ok), [true]);
  assert.deepEqual(harness.errors, []);
});

test("FINN exposes a safe auth code when session refresh fails", async () => {
  const harness = streamHarness({ refreshSuccess: false });
  await harness.stream("Analyseer BTC", {}, [], () => {}, () => {}, value => harness.errors.push(value));
  assert.deepEqual(harness.calls.map(call => typeof call === "string" ? call : call.token), ["Bearer expired", "refresh"]);
  assert.deepEqual(harness.errors.map(value => value.code), ["auth_required"]);
});
