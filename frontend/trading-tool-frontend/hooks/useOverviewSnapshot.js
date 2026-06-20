"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchLatestPrice } from "@/lib/api/market";
import { fetchMarketIntelligence } from "@/lib/api/marketIntelligence";

const SNAPSHOT_TTL_MS = 60_000;
const snapshotCache = new Map();
const inflightSnapshotRequests = new Map();

function getCacheKey(symbol = "BTC") {
  return String(symbol || "BTC").toUpperCase();
}

export function useOverviewSnapshot(symbol = "BTC") {
  const cacheKey = getCacheKey(symbol);
  const [snapshot, setSnapshot] = useState(() => {
    const cached = snapshotCache.get(cacheKey);
    return cached?.data ?? null;
  });
  const [loading, setLoading] = useState(!snapshot);

  const load = useCallback(
    async (forceRefresh = false) => {
      const cached = snapshotCache.get(cacheKey);
      const cacheIsFresh =
        cached && Date.now() - cached.timestamp < SNAPSHOT_TTL_MS;

      if (!forceRefresh && cacheIsFresh) {
        setSnapshot(cached.data);
        setLoading(false);
        return cached.data;
      }

      if (!forceRefresh && inflightSnapshotRequests.has(cacheKey)) {
        setLoading(true);
        const shared = await inflightSnapshotRequests.get(cacheKey);
        setSnapshot(shared);
        setLoading(false);
        return shared;
      }

      setLoading(true);

      const request = (async () => {
        const [liveRes, intelligenceRes] = await Promise.allSettled([
          fetchLatestPrice(symbol, { forceFresh: false }),
          fetchMarketIntelligence(symbol),
        ]);

        const nextSnapshot = {
          symbol: cacheKey,
          live: liveRes.status === "fulfilled" ? liveRes.value : cached?.data?.live ?? null,
          liveLoading: false,
          intelligence:
            intelligenceRes.status === "fulfilled"
              ? intelligenceRes.value
              : cached?.data?.intelligence ?? null,
          intelligenceLoading: false,
        };

        snapshotCache.set(cacheKey, {
          data: nextSnapshot,
          timestamp: Date.now(),
        });
        return nextSnapshot;
      })();

      inflightSnapshotRequests.set(cacheKey, request);

      try {
        const nextSnapshot = await request;
        setSnapshot(nextSnapshot);
        return nextSnapshot;
      } finally {
        inflightSnapshotRequests.delete(cacheKey);
        setLoading(false);
      }
    },
    [cacheKey, symbol]
  );

  useEffect(() => {
    void load();
  }, [load]);

  return {
    snapshot,
    loading,
    reload: load,
  };
}
