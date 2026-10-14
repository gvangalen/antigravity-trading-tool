const PREFIX = "finn-composer-draft:v1";
const MAX_LENGTH = 10000;

function keyFor(ownerId) {
  return ownerId === null || ownerId === undefined || ownerId === ""
    ? null
    : `${PREFIX}:${String(ownerId)}`;
}

export function readFinnComposerDraft(storage, ownerId) {
  const key = keyFor(ownerId);
  if (!key || !storage) return "";
  try {
    return String(storage.getItem(key) || "").slice(0, MAX_LENGTH);
  } catch {
    return "";
  }
}

export function writeFinnComposerDraft(storage, ownerId, value) {
  const key = keyFor(ownerId);
  if (!key || !storage) return;
  try {
    const draft = String(value || "").slice(0, MAX_LENGTH);
    if (draft) storage.setItem(key, draft);
    else storage.removeItem(key);
  } catch {
    // Browsers can disable session storage; the in-memory draft still works.
  }
}
