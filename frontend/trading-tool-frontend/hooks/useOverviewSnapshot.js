"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchLatestPrice } from "@/lib/api/market";
import { fetchMarketIntelligence } from "@/lib/api/marketIntelligence";
import { useTranslation } from "@/app/providers/I18nProvider";

const SNAPSHOT_TTL_MS = 60_000;
const snapshotCache = new Map();
const inflightSnapshotRequests = new Map();

function getCacheKey(symbol = "BTC", locale = "nl") {
  return `${String(symbol || "BTC").toUpperCase()}:${String(locale || "nl").toLowerCase()}`;
}

export function useOverviewSnapshot(symbol = "BTC") {
  const { locale } = useTranslation();
  const cacheKey = getCacheKey(symbol, locale);
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
          symbol: String(symbol || "BTC").toUpperCase(),
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
    [cacheKey, locale, symbol]
  );

  useEffect(() => {
    void load();
  }, [load, locale]);

  return {
    snapshot,
    loading,
    reload: load,
  };
}
