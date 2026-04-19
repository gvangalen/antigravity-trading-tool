import { useState, useEffect } from "react";
import { apiGet } from "@/lib/api/apiClient";

/**
 * 🤖 Hook for fetching recent trades of a specific bot.
 */
export function useBotTrades(botId: number | null, limit: number = 50) {
  const [trades, setTrades] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!botId) {
      setTrades([]);
      return;
    }

    async function loadTrades() {
      setLoading(true);
      setError(null);
      try {
        // Gebruik de bestaande endpoint uit bot_api.py
        const data = await apiGet<any[]>(`/api/bot/trades?bot_id=${botId}&limit=${limit}`);
        setTrades(Array.isArray(data) ? data : []);
      } catch (err: any) {
        console.error("❌ useBotTrades error:", err);
        setError(err.message || "Failed to load bot trades");
      } finally {
        setLoading(false);
      }
    }

    loadTrades();
  }, [botId, limit]);

  return { trades, loading, error };
}
