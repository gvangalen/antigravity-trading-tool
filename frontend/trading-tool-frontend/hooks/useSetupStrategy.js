"use client";

import { useEffect, useState, useCallback } from "react";
import { fetchStrategyBySetup } from "@/lib/api/strategy";

/**
 * 📈 useSetupStrategy — Haalt de gekoppelde strategie op voor een specifieke setup.
 * Bevat de execution parameters (entry, targets, sl, r/r).
 */
export function useSetupStrategy(setupId) {
  const [strategy, setStrategy] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!setupId) {
      setStrategy(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      const data = await fetchStrategyBySetup(setupId);
      setStrategy(data);
    } catch (err) {
      console.error(`❌ Error loading strategy for setup ${setupId}:`, err);
    } finally {
      setLoading(false);
    }
  }, [setupId]);

  useEffect(() => {
    load();
  }, [load]);

  return { strategy, loading, reload: load };
}
