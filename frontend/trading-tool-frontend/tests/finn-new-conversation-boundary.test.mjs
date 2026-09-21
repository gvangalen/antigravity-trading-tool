import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const assistantSource = readFileSync(
  new URL("../components/ui/AIAssistant.jsx", import.meta.url),
  "utf8",
);

test("an immediate send after Nieuw gesprek cannot reuse the previous conversation", () => {
  assert.match(assistantSource, /forceNewFinnConversationRef = useRef\(false\)/);
  assert.match(assistantSource, /activeFinnSessionIdRef = useRef\(null\)/);
  assert.match(
    assistantSource,
    /startNewFinnConversation[\s\S]*forceNewFinnConversationRef\.current = true[\s\S]*activeFinnSessionIdRef\.current = null[\s\S]*setActiveFinnSessionId\(null\)/,
  );
  assert.match(
    assistantSource,
    /const chatSessionId = forceNewFinnConversationRef\.current[\s\S]*\? "new"[\s\S]*: activeFinnSessionIdRef\.current \|\| activeFinnSessionId \|\| readBrowserFinnConversation\(\) \|\| "new"/,
  );
  assert.match(assistantSource, /forceNewFinnConversationRef\.current = false/);
  assert.match(
    assistantSource,
    /startNewFinnConversation[\s\S]*clearActiveFinnConversation\(window\.sessionStorage, user\?\.id\)/,
  );
});

test("a terminal V2 envelope is immediately authoritative for the next turn", () => {
  assert.match(
    assistantSource,
    /persistActiveFinnSessionId[\s\S]*activeFinnSessionIdRef\.current = normalized[\s\S]*setActiveFinnSessionId\(normalized\)[\s\S]*writeActiveFinnConversation\(window\.sessionStorage, user\?\.id, normalized\)/,
  );
  assert.match(
    assistantSource,
    /await persistActiveFinnSessionId\(envelope\?\.session_id \|\| chatSessionId\)/,
  );
});

test("a confirmed V2 proposal rebinds the composer to its verified conversation", () => {
  assert.match(
    assistantSource,
    /conversation_id: projection\?\.conversation_id \|\| run\?\.conversation_id \|\| null/,
  );
  assert.match(
    assistantSource,
    /let confirmedConversationId = normalizeFinnSessionId\([\s\S]*execution\.conversation_id \|\| displayContext\.conversation_id/,
  );
  assert.match(
    assistantSource,
    /isFinnV2ConversationId\(confirmedConversationId\)[\s\S]*await persistActiveFinnSessionId\(confirmedConversationId\)/,
  );
});

test("a confirmed proposal re-reads the committed run when its delivery response lacks a session", () => {
  assert.match(
    assistantSource,
    /!isFinnV2ConversationId\(confirmedConversationId\) && displayContext\.run_id/,
  );
  assert.match(
    assistantSource,
    /await fetchFinnV2Run\(displayContext\.run_id\)/,
  );
  assert.match(
    assistantSource,
    /confirmedRun\?\.conversation_id[\s\S]*runtime_trace\?\.terminal_projection\?\.conversation_id/,
  );
});
