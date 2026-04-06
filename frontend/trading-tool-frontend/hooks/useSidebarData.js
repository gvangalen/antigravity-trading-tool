'use client';

import { useEffect, useState } from 'react';
import { fetchDailyReportSummary } from '@/lib/api/sidebar'; // deze bestaat wél nog

export function useSidebarData() {
  const [summary, setSummary] = useState('Geen samenvatting beschikbaar');
  const [trades, setTrades] = useState([]);
  const [aiStatus, setAiStatus] = useState({
    state: 'onbekend',
    strategy: 'n.v.t.',
    updated: 'onbekend'
  });

  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    async function load() {
      setLoading(true);

      try {
        // 🟢 Enige echte API call
        const summaryRes = await fetchDailyReportSummary();

        if (!mounted) return;

        setSummary(summaryRes.summary || 'Geen samenvatting beschikbaar');

        // 🟡 ACTIEVE TRADES = dummy
        setTrades([]);

        // 🔵 AI BOT STATUS = dummy
        setAiStatus({
          state: 'onbekend',
          strategy: 'n.v.t.',
          updated: 'onbekend'
        });

      } catch (e) {
        console.error("Sidebar load failed:", e);

        if (mounted) {
          setSummary('Geen samenvatting beschikbaar');
          setTrades([]);
          setAiStatus({
            state: 'onbekend',
            strategy: 'n.v.t.',
            updated: 'onbekend'
          });
        }
      } finally {
        if (mounted) setLoading(false);
      }
    }

    load();
    return () => { mounted = false };
  }, []);

  return {
    summary,
    trades,
    aiStatus,
    loading,
  };
}
