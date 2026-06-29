"use client";

import { useEffect, useState } from "react";
import { fetchMarketIntelligence } from "@/lib/api/marketIntelligence";
import { useTranslation } from "@/app/providers/I18nProvider";

const INTELLIGENCE_CACHE_TTL_MS = 60_000;
const intelligenceCache = new Map();
const inflightIntelligenceRequests = new Map();

export function useMarketIntelligence(symbol = "BTC") {
  const { locale } = useTranslation();

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const cacheKey = `${String(symbol || "BTC").toUpperCase()}:${String(locale || "nl").toLowerCase()}`;

  const load = async (forceRefresh = false) => {
    const cached = intelligenceCache.get(cacheKey);
    const cacheIsFresh =
      cached && Date.now() - cached.timestamp < INTELLIGENCE_CACHE_TTL_MS;

    if (!forceRefresh && cacheIsFresh) {
      setData(cached.data);
      setLoading(false);
      return cached.data;
    }

    if (!forceRefresh && inflightIntelligenceRequests.has(cacheKey)) {
      setLoading(true);
      const shared = await inflightIntelligenceRequests.get(cacheKey);
      setData(shared);
      setLoading(false);
      return shared;
    }

    setLoading(true);

    const request = (async () => {
      try {
        const res = await fetchMarketIntelligence(symbol);
        intelligenceCache.set(cacheKey, { data: res, timestamp: Date.now() });
        return res;
      } catch (err) {
        console.error("Market intelligence error", err);
        return cached?.data ?? null;
      }
    })();

    inflightIntelligenceRequests.set(cacheKey, request);

    try {
      const res = await request;
      setData(res);
      return res;
    } finally {
      inflightIntelligenceRequests.delete(cacheKey);
      setLoading(false);
    }

  };

  useEffect(() => {
    load();
  }, [locale, symbol]);

  return { data, loading, reload: load };
}
