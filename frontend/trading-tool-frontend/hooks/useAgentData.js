"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/components/auth/AuthProvider";

import {
  fetchMacroInsight,
  fetchMarketInsight,
  fetchTechnicalInsight,
  fetchSetupInsight,
  fetchStrategyInsight,
  fetchMacroReflections,
  fetchMarketReflections,
  fetchTechnicalReflections,
  fetchSetupReflections,
  fetchStrategyReflections,
} from "@/lib/api/agents";

import { fetchActiveStrategyToday } from "@/lib/api/strategy";

/* ======================================================
   🧠 INSIGHTS + REFLECTIES (BESTAAND)
   → Wordt gebruikt door AgentInsightPanel
====================================================== */

const insightMap = {
  macro: fetchMacroInsight,
  market: fetchMarketInsight,
  technical: fetchTechnicalInsight,
  setup: fetchSetupInsight,
  strategy: fetchStrategyInsight,
};

const reflectionMap = {
  macro: fetchMacroReflections,
  market: fetchMarketReflections,
  technical: fetchTechnicalReflections,
  setup: fetchSetupReflections,
  strategy: fetchStrategyReflections,
};
export function useAgentData(category) {
  const [insight, setInsight] = useState(null);
  const [reflections, setReflections] = useState([]);
  const [loading, setLoading] = useState(true);

  const { isAuthenticated } = useAuth();

  const load = async () => {
    if (!category || !isAuthenticated) return;

    console.log(`🧠 [useAgentData] load voor categorie: ${category}`);

    const fetchInsightFn = insightMap[category];
    const fetchReflectionsFn = reflectionMap[category];

    if (!fetchInsightFn || !fetchReflectionsFn) {
      console.error(`❌ Geen fetch functie gevonden voor category=${category}`);
      setInsight(null);
      setReflections([]);
      setLoading(false);
      return;
    }

    try {
      const [insightData, reflectionsData] = await Promise.all([
        fetchInsightFn(),
        fetchReflectionsFn(),
      ]);

      setInsight(insightData || null);
      setReflections(Array.isArray(reflectionsData) ? reflectionsData : []);
    } catch (e) {
      console.error("❌ [useAgentData] Fout:", e);
      setInsight(null);
      setReflections([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setLoading(true);
    load();

    // 🔥 FIX: auto refresh elke 10 sec (alleen indien ingelogd)
    const interval = setInterval(() => {
      if (isAuthenticated) {
        load();
      } else {
        clearInterval(interval);
      }
    }, 10000);

    return () => clearInterval(interval);
  }, [category, isAuthenticated]);

  return {
    insight,
    reflections,
    loading,
    refetch: load, // 🔥 manual trigger mogelijk
  };
}

/* ======================================================
   🎯 ACTIEVE STRATEGIE VANDAAG (NIEUW)
   → Voor de nieuwe Strategy Today Card
====================================================== */

export function useActiveStrategyToday() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      setLoading(true);

      try {
        // ==================================================
        // 1️⃣ Probeer normale actieve strategie (snapshot)
        // ==================================================
        const active = await fetchActiveStrategyToday();

        if (active) {
          setData(active);
          return;
        }

        // ==================================================
        // 2️⃣ Fallback → DCA strategy via AI insight
        // ==================================================
        const strategyInsight = await fetchStrategyInsight();

        if (!strategyInsight) {
          setData(null);
          return;
        }

        /**
         * We bouwen hier bewust een "strategy today" object
         * zonder entry → UI herkent dit als DCA
         */
        const dcaStrategyToday = {
          setup_name: strategyInsight.setup_name || "DCA",
          symbol: strategyInsight.symbol || "BTC",
          timeframe: strategyInsight.timeframe || "1D",

          entry: null,          // 🔑 DCA → referentieprijs in UI
          targets: null,
          stop_loss: null,

          adjustment_reason:
            strategyInsight.summary ||
            "DCA-strategie actief. Vandaag afgestemd op marktcondities.",

          confidence_score: strategyInsight.avg_score ?? null,
        };

        setData(dcaStrategyToday);

      } catch (e) {
        console.error("❌ [useActiveStrategyToday] Fout:", e);
        setData(null);
      } finally {
        setLoading(false);
      }
    };

    load();
  }, []);

  return {
    strategy: data,
    loading,
  };
}
