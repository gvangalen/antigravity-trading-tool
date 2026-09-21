import test from "node:test";
import assert from "node:assert/strict";

import {
  activeFinnConversationStorageKey,
  clearActiveFinnConversation,
  readActiveFinnConversation,
  writeActiveFinnConversation,
} from "../lib/finnActiveConversation.mjs";

function memoryStorage() {
  const values = new Map();
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
    removeItem(key) {
      values.delete(key);
    },
  };
}

test("a confirmed V2 conversation survives a component remount in the same tab", () => {
  const storage = memoryStorage();
  const conversationId = "finn-v2-conv-confirmed-update";

  assert.equal(writeActiveFinnConversation(storage, "user-a", conversationId), conversationId);
  assert.equal(readActiveFinnConversation(storage, "user-a"), conversationId);
});

test("active FINN conversations are isolated per authenticated user", () => {
  const storage = memoryStorage();
  writeActiveFinnConversation(storage, "user-a", "finn-v2-conv-user-a");

  assert.equal(readActiveFinnConversation(storage, "user-b"), null);
  assert.notEqual(activeFinnConversationStorageKey("user-a"), activeFinnConversationStorageKey("user-b"));
});

test("Nieuw gesprek clears only the current user's browser conversation", () => {
  const storage = memoryStorage();
  writeActiveFinnConversation(storage, "user-a", "finn-v2-conv-user-a");
  writeActiveFinnConversation(storage, "user-b", "finn-v2-conv-user-b");

  clearActiveFinnConversation(storage, "user-a");

  assert.equal(readActiveFinnConversation(storage, "user-a"), null);
  assert.equal(readActiveFinnConversation(storage, "user-b"), "finn-v2-conv-user-b");
});

test("invalid or legacy session identifiers cannot become V2 conversation authority", () => {
  const storage = memoryStorage();

  assert.equal(writeActiveFinnConversation(storage, "user-a", "legacy-session"), null);
  storage.setItem(activeFinnConversationStorageKey("user-a"), "legacy-session");
  assert.equal(readActiveFinnConversation(storage, "user-a"), null);
});
