"use client";

const listeners = new Set();
const snapshots = new Map();

function normalizeSymbol(symbol) {
  return String(symbol || "BTC").trim().toUpperCase() || "BTC";
}

export function getWorkspaceSnapshot(symbol) {
  return snapshots.get(normalizeSymbol(symbol)) || null;
}

export function setWorkspaceSnapshot(symbol, snapshot) {
  const normalized = normalizeSymbol(symbol);
  if (!snapshot || typeof snapshot !== "object") return;
  snapshots.set(normalized, snapshot);
  listeners.forEach((listener) => {
    try {
      listener(normalized, snapshot);
    } catch (error) {
      console.error("Workspace snapshot listener failed", error);
    }
  });
}

export function subscribeWorkspaceSnapshot(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
