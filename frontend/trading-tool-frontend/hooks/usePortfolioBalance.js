"use client";

import { useEffect, useState, useCallback } from "react";
import {
  fetchPortfolioBalanceHistory,
  fetchBotBalanceHistory,
} from "@/lib/api/botApi";

export default function usePortfolioBalance({
  bot_id = null,
  is_live = null,        // 🔥 NIEUW
  bucket = "1h",
  limit = 300,
  autoLoad = true,
} = {}) {

  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      let res;

      if (bot_id) {
        // 🔥 Per bot equity
        res = await fetchBotBalanceHistory({
          bot_id,
          bucket,
          limit,
        });
      } else {
        // 🌍 Global portfolio equity
        res = await fetchPortfolioBalanceHistory({
          bucket,
          limit,
          is_live,
        });
      }

      setData(Array.isArray(res) ? res : []);
    } catch (err) {
      console.error(err);
      setError(err.message || "Balance history laden mislukt");
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [bot_id, is_live, bucket, limit]);

  useEffect(() => {
    if (autoLoad) load();
  }, [load, autoLoad]);

  return {
    data,
    loading,
    error,
    reload: load,
  };
}
