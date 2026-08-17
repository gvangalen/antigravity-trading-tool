"use client";

const listeners = new Set();
const snapshots = new Map();

function normalizeSymbol(symbol) {
  const normalized = String(symbol || "").trim().toUpperCase();
  return normalized || "UNKNOWN";
}

function normalizeScope(scope) {
  return String(scope || "anonymous").trim() || "anonymous";
}

function snapshotKey(symbol, scope) {
  return `${normalizeScope(scope)}:${normalizeSymbol(symbol)}`;
}

export function getWorkspaceSnapshot(symbol, scope = "anonymous") {
  return snapshots.get(snapshotKey(symbol, scope)) || null;
}

export function setWorkspaceSnapshot(symbol, snapshot, scope = "anonymous") {
  const normalized = normalizeSymbol(symbol);
  if (!snapshot || typeof snapshot !== "object") return;
  const key = snapshotKey(normalized, scope);
  snapshots.set(key, snapshot);
  listeners.forEach((listener) => {
    try {
      listener(normalized, snapshot, normalizeScope(scope));
    } catch (error) {
      console.error("Workspace snapshot listener failed", error);
    }
  });
}

export function subscribeWorkspaceSnapshot(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
