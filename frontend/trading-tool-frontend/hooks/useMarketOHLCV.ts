import { useState, useEffect } from "react";
import { apiGet } from "@/lib/api/apiClient";

/**
 * 📈 Hook for fetching 7-day OHLCV data for the dashboard chart.
 */
export function useMarketOHLCV() {
  const [candles, setCandles] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadCandles() {
      setLoading(true);
      setError(null);
      try {
        const data = await apiGet<any[]>(`/api/market_data/7d`);
        
        // Transform naar Lightweight Charts formaat
        const formatted = Array.isArray(data) ? data.map(item => ({
          time: item.date, // Format: YYYY-MM-DD
          open: item.open,
          high: item.high,
          low: item.low,
          close: item.close,
          volume: item.volume
        })) : [];
        
        setCandles(formatted);
      } catch (err: any) {
        console.error("❌ useMarketOHLCV error:", err);
        setError(err.message || "Failed to load candle data");
      } finally {
        setLoading(false);
      }
    }

    loadCandles();
  }, []);

  return { candles, loading, error };
}
