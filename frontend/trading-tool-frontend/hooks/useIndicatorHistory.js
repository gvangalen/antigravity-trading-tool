"use client";

import { useEffect, useState } from "react";
import { fetchIndicatorHistory } from "@/lib/api/technical";

/**
 * 📈 useIndicatorHistory — Haalt echte historische data op voor sparklines.
 */
export function useIndicatorHistory(indicatorName, limit = 20) {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!indicatorName) return;

    async function load() {
      try {
        const data = await fetchIndicatorHistory(indicatorName, limit);
        setHistory(Array.isArray(data) ? data : []);
      } catch (err) {
        console.error(`❌ Error loading history for ${indicatorName}:`, err);
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [indicatorName, limit]);

  return { history, loading };
}
