'use client';

import { useEffect, useState } from 'react';
import { getDailyScores } from '@/lib/api/scores'; // 👈 jouw bestaande route

export function useDashboardData() {
  const [loading, setLoading] = useState(true);

  const [macroScore, setMacroScore] = useState(0);
  const [technicalScore, setTechnicalScore] = useState(0);
  const [marketScore, setMarketScore] = useState(0);
  const [setupScore, setSetupScore] = useState(0);

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

    async function load() {
      try {
        setLoading(true);

        // 🟦 CORRECTE BACKEND-CALL
        const res = await getDailyScores();
        if (!mounted || !res) return;

        // 🟩 EXACTE BACKEND-FIELDS (dit komt uit daily_scores)
        setMacroScore(res.macro_score ?? 0);
        setMacroExplanation(res.macro_interpretation ?? '–');
        setMacroTop(res.macro_top_contributors ?? []);

        setTechnicalScore(res.technical_score ?? 0);
        setTechnicalExplanation(res.technical_interpretation ?? '–');
        setTechnicalTop(res.technical_top_contributors ?? []);

        setMarketScore(res.market_score ?? 0);
        setMarketExplanation(res.market_interpretation ?? '–');
        setMarketTop(res.market_top_contributors ?? []);

        setSetupScore(res.setup_score ?? 0);
        setSetupExplanation(res.setup_interpretation ?? '–');
        setSetupTop(res.setup_top_contributors ?? []);

      } catch (err) {
        console.error('❌ Fout bij useDashboardData:', err);
      } finally {
        if (mounted) setLoading(false);
      }
    }

    load();
    const interval = setInterval(load, 60000);
    return () => {
      mounted = false;
      clearInterval(interval);
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
