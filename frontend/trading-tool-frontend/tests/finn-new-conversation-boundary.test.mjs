import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const assistantSource = readFileSync(
  new URL("../components/ui/AIAssistant.jsx", import.meta.url),
  "utf8",
);

test("an immediate send after Nieuw gesprek cannot reuse the previous conversation", () => {
  assert.match(assistantSource, /forceNewFinnConversationRef = useRef\(false\)/);
  assert.match(
    assistantSource,
    /startNewFinnConversation[\s\S]*forceNewFinnConversationRef\.current = true[\s\S]*setActiveFinnSessionId\(null\)/,
  );
  assert.match(
    assistantSource,
    /const chatSessionId = forceNewFinnConversationRef\.current[\s\S]*\? "new"[\s\S]*: activeFinnSessionId \|\| "new"/,
  );
  assert.match(assistantSource, /forceNewFinnConversationRef\.current = false/);
});
