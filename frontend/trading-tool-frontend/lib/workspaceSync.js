"use client";

const WORKSPACE_SYNC_CHANNEL = "tradamind-workspace-sync";
const WORKSPACE_SYNC_STORAGE_KEY = "tradamind-workspace-sync:last";

let broadcastChannel = null;

function canUseDom() {
  return typeof window !== "undefined";
}

function getBroadcastChannel() {
  if (!canUseDom()) return null;
  if (broadcastChannel !== null) return broadcastChannel;
  if (typeof window.BroadcastChannel !== "function") {
    broadcastChannel = null;
    return null;
  }
  broadcastChannel = new window.BroadcastChannel(WORKSPACE_SYNC_CHANNEL);
  return broadcastChannel;
}

export function publishWorkspaceRefresh(detail = {}) {
  if (!canUseDom()) return;

  const payload = {
    symbol: String(detail.symbol || "").toUpperCase() || null,
    category: detail.category || null,
    reason: detail.reason || "workspace_update",
    timestamp: Date.now(),
  };

  try {
    getBroadcastChannel()?.postMessage(payload);
  } catch (error) {
    console.warn("Workspace sync broadcast failed:", error);
  }

  try {
    window.localStorage.setItem(WORKSPACE_SYNC_STORAGE_KEY, JSON.stringify(payload));
  } catch (error) {
    console.warn("Workspace sync storage write failed:", error);
  }
}

export function subscribeWorkspaceRefresh(callback) {
  if (!canUseDom() || typeof callback !== "function") return () => {};

  const handlePayload = (payload) => {
    if (!payload || typeof payload !== "object") return;
    callback(payload);
  };

  const channel = getBroadcastChannel();
  const handleMessage = (event) => handlePayload(event?.data || null);
  const handleStorage = (event) => {
    if (event.key !== WORKSPACE_SYNC_STORAGE_KEY || !event.newValue) return;
    try {
      handlePayload(JSON.parse(event.newValue));
    } catch (error) {
      console.warn("Workspace sync storage parse failed:", error);
    }
  };

  channel?.addEventListener("message", handleMessage);
  window.addEventListener("storage", handleStorage);

  return () => {
    channel?.removeEventListener("message", handleMessage);
    window.removeEventListener("storage", handleStorage);
  };
}
