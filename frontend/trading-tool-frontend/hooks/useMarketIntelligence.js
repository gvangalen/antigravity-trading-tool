"use client";

import { useEffect, useState } from "react";
import { fetchMarketIntelligence } from "@/lib/api/marketIntelligence";

export function useMarketIntelligence() {

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {

    try {

      const res = await fetchMarketIntelligence();
      setData(res);

    } catch (err) {

      console.error("Market intelligence error", err);

    } finally {

      setLoading(false);

    }

  };

  useEffect(() => {
    load();
  }, []);

  return { data, loading, reload: load };
}
