'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  fetchCachedResource,
  getCachedResourceSnapshot,
  markCachedResourceStale,
  subscribeCachedResource,
} from '@/lib/clientDataCache';

import {
  fetchStrategies,
  createStrategy,
  updateStrategy,
  deleteStrategy,
  analyzeStrategy,
  generateAllStrategies,
} from '@/lib/api/strategy';

import { fetchSetups } from '@/lib/api/setups';

const STRATEGIES_CACHE_TTL_MS = 60_000;
const SETUPS_CACHE_TTL_MS = 60_000;
const STRATEGIES_CACHE_KEY = 'strategies:list';
const SETUPS_CACHE_KEY = 'setups:list:strategy-data';

export function invalidateStrategyDataCaches() {
  markCachedResourceStale(STRATEGIES_CACHE_KEY);
  markCachedResourceStale(SETUPS_CACHE_KEY);
}

async function loadStrategiesShared(forceFresh = false) {
  return fetchCachedResource(STRATEGIES_CACHE_KEY, {
    ttlMs: STRATEGIES_CACHE_TTL_MS,
    forceFresh,
    initialData: [],
    fetcher: async () => {
      const data = await fetchStrategies();
      return Array.isArray(data) ? data.filter(Boolean) : [];
    },
  });
}

async function loadSetupsShared(forceFresh = false) {
  return fetchCachedResource(SETUPS_CACHE_KEY, {
    ttlMs: SETUPS_CACHE_TTL_MS,
    forceFresh,
    initialData: [],
    fetcher: async () => {
      const data = await fetchSetups();
      return Array.isArray(data)
        ? data
            .filter(Boolean)
            .map((s) => ({
              ...s,
              setup_type: String(s.setup_type || '').toLowerCase(),
            }))
            .filter((s) => s.setup_type === 'dca' || s.setup_type === 'trade')
        : [];
    },
  });
}

// =====================================================================
// 🧠 STRATEGY DATA HOOK (CLEAN V1)
// =====================================================================
export function useStrategyData(options = {}) {
  const { autoLoad = true, includeSetups = true } = options;
  const initialStrategies = getCachedResourceSnapshot(STRATEGIES_CACHE_KEY, []);
  const initialSetups = getCachedResourceSnapshot(SETUPS_CACHE_KEY, []);
  const [strategies, setStrategies] = useState(() => initialStrategies.data || []);
  const [setups, setSetups] = useState(() => (includeSetups ? initialSetups.data || [] : []));

  const [loading, setLoading] = useState(
    () => autoLoad && (!initialStrategies.hasData || (includeSetups && !initialSetups.hasData))
  );
  const [error, setError] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  // =========================================================
  // LOAD STRATEGIES
  // =========================================================
  const loadStrategies = useCallback(async (forceFresh = false) => {
    setLoading(true);
    setError('');

    try {
      const cleaned = await loadStrategiesShared(forceFresh);
      setStrategies(cleaned);
      return cleaned;
    } catch (err) {
      console.error('❌ loadStrategies fout:', err);
      setError('Fout bij laden strategieën.');
      setStrategies([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // =========================================================
  // LOAD SETUPS
  // =========================================================
  const loadSetups = useCallback(async (forceFresh = false) => {
    setError('');
  
    try {
      const cleaned = await loadSetupsShared(forceFresh);
      setSetups(cleaned);
      return cleaned;
    } catch (err) {
      console.error('❌ loadSetups fout:', err);
      setError('Fout bij laden setups.');
      setSetups([]);
      return [];
    }
  }, []);

  // =========================================================
  // INIT LOAD
  // =========================================================
  useEffect(() => {
    const unsubStrategies = subscribeCachedResource(STRATEGIES_CACHE_KEY, () => {
      const snapshot = getCachedResourceSnapshot(STRATEGIES_CACHE_KEY, []);
      setStrategies(snapshot.data || []);
    });
    const unsubSetups = subscribeCachedResource(SETUPS_CACHE_KEY, () => {
      if (!includeSetups) return;
      const snapshot = getCachedResourceSnapshot(SETUPS_CACHE_KEY, []);
      setSetups(snapshot.data || []);
    });

    if (!autoLoad) {
      setLoading(false);
      return () => {
        unsubStrategies();
        unsubSetups();
      };
    }

    let cancelled = false;

    async function bootstrap() {
      setLoading(true);
      const tasks = [loadStrategies()];
      if (includeSetups) {
        tasks.push(loadSetups());
      }
      await Promise.all(tasks);
      if (!cancelled) {
        setLoading(false);
      }
    }

    void bootstrap();

    return () => {
      cancelled = true;
      unsubStrategies();
      unsubSetups();
    };
  }, [autoLoad, includeSetups, loadSetups, loadStrategies]);

  // =========================================================
  // CRUD
  // =========================================================
  async function addStrategy(strategyData) {
    try {
      const created = await createStrategy(strategyData);
      invalidateStrategyDataCaches();
      setSuccessMessage('Strategie toegevoegd.');
      await loadStrategies(true);
      return created;
    } catch (err) {
      console.error('❌ addStrategy fout:', err);
      setError('Toevoegen mislukt.');
      throw err;
    }
  }

  async function saveStrategy(id, updatedData) {
    try {
      const saved = await updateStrategy(id, updatedData);
      invalidateStrategyDataCaches();
      setSuccessMessage('Strategie opgeslagen.');
      await loadStrategies(true);
      return saved;
    } catch (err) {
      console.error('❌ saveStrategy fout:', err);
      setError('Opslaan mislukt.');
      throw err;
    }
  }

  async function removeStrategy(id) {
    try {
      await deleteStrategy(id);
      invalidateStrategyDataCaches();
      setSuccessMessage('Strategie verwijderd.');
      await loadStrategies(true);
      return true;
    } catch (err) {
      console.error('❌ removeStrategy fout:', err);
      setError('Verwijderen mislukt.');
      throw err;
    }
  }

  // =========================================================
  // AI ANALYSE
  // =========================================================
  async function analyzeSingleStrategy(strategyId) {
    setSuccessMessage('');
    setError('');

    if (!strategyId) {
      setError('Geen strategie geselecteerd.');
      return;
    }

    try {
      await analyzeStrategy(strategyId);
      invalidateStrategyDataCaches();
      await loadStrategies(true);
      setSuccessMessage('🧠 AI-uitleg bijgewerkt');
    } catch (err) {
      console.error('❌ AI analyse fout:', err);
      setError('AI analyse mislukt.');
    }
  }

  // =========================================================
  // BULK
  // =========================================================
  async function generateAll() {
    try {
      await generateAllStrategies();
      invalidateStrategyDataCaches();
      await loadStrategies(true);
      setSuccessMessage('Alle strategieën gegenereerd.');
    } catch (err) {
      console.error('❌ generateAll fout:', err);
      setError('Bulkgeneratie mislukt.');
    }
  }

  // =========================================================
  // RETURN
  // =========================================================
  return {
    strategies,
    setups,
    loading,
    error,
    successMessage,

    loadStrategies,
    loadSetups,

    addStrategy,
    saveStrategy,
    removeStrategy,

    analyzeSingleStrategy,
    generateAll,
  };
}
