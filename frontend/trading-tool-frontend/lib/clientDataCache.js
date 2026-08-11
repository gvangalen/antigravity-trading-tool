"use client";

const resourceStore = new Map();

function ensureEntry(key) {
  if (!resourceStore.has(key)) {
    resourceStore.set(key, {
      data: undefined,
      updatedAt: 0,
      error: null,
      inflight: null,
      listeners: new Set(),
    });
  }
  return resourceStore.get(key);
}

function notify(entry) {
  entry.listeners.forEach((listener) => {
    try {
      listener();
    } catch (error) {
      console.error("clientDataCache listener failed", error);
    }
  });
}

export function getCachedResourceSnapshot(key, initialData) {
  const entry = ensureEntry(key);
  const hasData = entry.updatedAt > 0 || entry.data !== undefined;
  return {
    data: hasData ? entry.data : initialData,
    updatedAt: entry.updatedAt,
    error: entry.error,
    hasData,
  };
}

export function isCachedResourceFresh(key, ttlMs = 0) {
  const entry = ensureEntry(key);
  if (!entry.updatedAt) return false;
  return Date.now() - entry.updatedAt < ttlMs;
}

export function subscribeCachedResource(key, listener) {
  const entry = ensureEntry(key);
  entry.listeners.add(listener);
  return () => {
    entry.listeners.delete(listener);
  };
}

export function setCachedResourceData(key, data) {
  const entry = ensureEntry(key);
  entry.data = data;
  entry.updatedAt = Date.now();
  entry.error = null;
  notify(entry);
  return data;
}

export function updateCachedResourceData(key, updater, initialData) {
  const current = getCachedResourceSnapshot(key, initialData).data;
  return setCachedResourceData(
    key,
    typeof updater === "function" ? updater(current) : updater
  );
}

export function markCachedResourceStale(key) {
  const entry = ensureEntry(key);
  entry.updatedAt = 0;
  notify(entry);
}

export function clearCachedResource(key) {
  const entry = ensureEntry(key);
  entry.data = undefined;
  entry.updatedAt = 0;
  entry.error = null;
  entry.inflight = null;
  notify(entry);
}

export async function fetchCachedResource(
  key,
  {
    ttlMs = 0,
    forceFresh = false,
    fetcher,
    initialData,
    keepStaleOnError = true,
  }
) {
  const entry = ensureEntry(key);

  if (!forceFresh && ttlMs > 0 && isCachedResourceFresh(key, ttlMs)) {
    return getCachedResourceSnapshot(key, initialData).data;
  }

  if (!forceFresh && entry.inflight) {
    return entry.inflight;
  }

  const request = Promise.resolve()
    .then(() => fetcher())
    .then((data) => setCachedResourceData(key, data))
    .catch((error) => {
      entry.error = error;
      notify(entry);
      const snapshot = getCachedResourceSnapshot(key, initialData);
      if (keepStaleOnError && snapshot.hasData) {
        return snapshot.data;
      }
      throw error;
    })
    .finally(() => {
      if (entry.inflight === request) {
        entry.inflight = null;
      }
    });

  entry.inflight = request;
  return request;
}
