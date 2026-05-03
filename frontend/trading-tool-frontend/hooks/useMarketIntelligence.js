"use client";

import { useEffect, useState } from "react";
import { fetchMarketIntelligence } from "@/lib/api/marketIntelligence";

export function useMarketIntelligence(symbol = "BTC") {

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {

      const res = await fetchMarketIntelligence(symbol);
      setData(res);

    } catch (err) {

      console.error("Market intelligence error", err);

    } finally {

      setLoading(false);

    }

  };

  useEffect(() => {
    load();
  }, [symbol]);

  return { data, loading, reload: load };
}
