const ACTIVE_FINN_CONVERSATION_STORAGE_PREFIX = "finn-active-conversation:v1";

function normalizeStorageScope(userId) {
  return String(userId || "anonymous").trim() || "anonymous";
}

function normalizeConversationId(value) {
  if (typeof value !== "string") return null;
  const normalized = value.trim();
  return normalized.startsWith("finn-v2-conv-") ? normalized : null;
}

export function activeFinnConversationStorageKey(userId) {
  return `${ACTIVE_FINN_CONVERSATION_STORAGE_PREFIX}:${normalizeStorageScope(userId)}`;
}

export function readActiveFinnConversation(storage, userId) {
  if (!storage || typeof storage.getItem !== "function") return null;
  try {
    return normalizeConversationId(storage.getItem(activeFinnConversationStorageKey(userId)));
  } catch {
    return null;
  }
}

export function writeActiveFinnConversation(storage, userId, conversationId) {
  const normalized = normalizeConversationId(conversationId);
  if (!storage || typeof storage.setItem !== "function" || !normalized) return null;
  try {
    storage.setItem(activeFinnConversationStorageKey(userId), normalized);
    return normalized;
  } catch {
    return null;
  }
}

export function clearActiveFinnConversation(storage, userId) {
  if (!storage || typeof storage.removeItem !== "function") return;
  try {
    storage.removeItem(activeFinnConversationStorageKey(userId));
  } catch {
    // Browser storage can be unavailable in restricted browsing contexts.
  }
}
