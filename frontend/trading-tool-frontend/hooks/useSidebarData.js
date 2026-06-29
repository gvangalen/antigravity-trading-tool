'use client';

import { useEffect, useState } from 'react';
import { fetchDailyReportSummary } from '@/lib/api/sidebar'; // deze bestaat wél nog

export function useSidebarData(symbol = "BTC") {
  const [summary, setSummary] = useState("");
  const [trades, setTrades] = useState([]);
  const [aiStatus, setAiStatus] = useState({
    state: "",
    strategy: "",
    updated: ""
  });

  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    async function load() {
      setLoading(true);

      try {
        // 🟢 Enige echte API call - Nu met symbol!
        const summaryRes = await fetchDailyReportSummary(symbol);

        if (!mounted) return;

        setSummary(summaryRes.summary || "");

        // 🟡 ACTIEVE TRADES = dummy
        setTrades([]);

        // 🔵 AI BOT STATUS = dummy
        setAiStatus({
          state: "",
          strategy: "",
          updated: ""
        });

      } catch (e) {
        console.error("Sidebar load failed:", e);

        if (mounted) {
          setSummary("");
          setTrades([]);
          setAiStatus({
            state: "",
            strategy: "",
            updated: ""
          });
        }
      } finally {
        if (mounted) setLoading(false);
      }
    }

    load();
    return () => { mounted = false };
  }, [symbol]);

  return {
    summary,
    trades,
    aiStatus,
    loading,
  };
}
