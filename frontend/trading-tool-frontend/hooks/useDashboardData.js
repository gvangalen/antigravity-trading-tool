'use client';

import { useEffect, useRef, useState } from 'react';
import { getDailyScores } from '@/lib/api/scores'; // 👈 jouw bestaande route

const FOREGROUND_POLL_INTERVAL_MS = 120000;
const BACKGROUND_POLL_INTERVAL_MS = 300000;

export function useDashboardData() {
  const [loading, setLoading] = useState(true);
  const loadingRef = useRef(false);

  const [macroScore, setMacroScore] = useState(null);
  const [technicalScore, setTechnicalScore] = useState(null);
  const [marketScore, setMarketScore] = useState(null);
  const [setupScore, setSetupScore] = useState(null);

  const [macroExplanation, setMacroExplanation] = useState('–');
  const [technicalExplanation, setTechnicalExplanation] = useState('–');
  const [marketExplanation, setMarketExplanation] = useState('–');
  const [setupExplanation, setSetupExplanation] = useState('–');

  const [macroTop, setMacroTop] = useState([]);
  const [technicalTop, setTechnicalTop] = useState([]);
  const [marketTop, setMarketTop] = useState([]);
  const [setupTop, setSetupTop] = useState([]);

  useEffect(() => {
    let mounted = true;
    let interval = null;

    async function load() {
      if (loadingRef.current) return;
      loadingRef.current = true;

      try {
        setLoading(true);

        // 🟦 CORRECTE BACKEND-CALL
        const res = await getDailyScores();
        if (!mounted || !res) return;

        // 🟩 EXACTE BACKEND-FIELDS (dit komt uit daily_scores)
        setMacroScore(Number.isFinite(Number(res.macro_score)) ? Number(res.macro_score) : null);
        setMacroExplanation(res.macro_interpretation ?? '–');
        setMacroTop(res.macro_top_contributors ?? []);

        setTechnicalScore(Number.isFinite(Number(res.technical_score)) ? Number(res.technical_score) : null);
        setTechnicalExplanation(res.technical_interpretation ?? '–');
        setTechnicalTop(res.technical_top_contributors ?? []);

        setMarketScore(Number.isFinite(Number(res.market_score)) ? Number(res.market_score) : null);
        setMarketExplanation(res.market_interpretation ?? '–');
        setMarketTop(res.market_top_contributors ?? []);

        setSetupScore(Number.isFinite(Number(res.setup_score)) ? Number(res.setup_score) : null);
        setSetupExplanation(res.setup_interpretation ?? '–');
        setSetupTop(res.setup_top_contributors ?? []);

      } catch (err) {
        console.error('❌ Fout bij useDashboardData:', err);
      } finally {
        loadingRef.current = false;
        if (mounted) setLoading(false);
      }
    }

    function scheduleNextPoll() {
      if (interval) clearInterval(interval);
      const isHidden = typeof document !== 'undefined' && document.visibilityState === 'hidden';
      const intervalMs = isHidden ? BACKGROUND_POLL_INTERVAL_MS : FOREGROUND_POLL_INTERVAL_MS;
      interval = setInterval(load, intervalMs);
    }

    function handleVisibilityChange() {
      scheduleNextPoll();
      if (document.visibilityState === 'visible') {
        load();
      }
    }

    load();
    scheduleNextPoll();

    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', handleVisibilityChange);
    }

    return () => {
      mounted = false;
      if (interval) clearInterval(interval);
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', handleVisibilityChange);
      }
    };
  }, []);

  return {
    loading,

    macroScore,
    technicalScore,
    marketScore,
    setupScore,

    macroExplanation,
    technicalExplanation,
    marketExplanation,
    setupExplanation,

    macroTop,
    technicalTop,
    marketTop,
    setupTop,
  };
}
