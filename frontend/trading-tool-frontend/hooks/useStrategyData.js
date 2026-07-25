'use client';

import { useState, useEffect, useCallback } from 'react';

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

let strategiesCache = [];
let strategiesCacheUpdatedAt = 0;
let strategiesInFlightPromise = null;

let setupsCache = [];
let setupsCacheUpdatedAt = 0;
let setupsInFlightPromise = null;

function hasFreshStrategiesCache() {
  return Date.now() - strategiesCacheUpdatedAt < STRATEGIES_CACHE_TTL_MS;
}

function hasFreshSetupsCache() {
  return Date.now() - setupsCacheUpdatedAt < SETUPS_CACHE_TTL_MS;
}

async function loadStrategiesShared(forceFresh = false) {
  if (!forceFresh && hasFreshStrategiesCache()) {
    return strategiesCache;
  }

  if (!strategiesInFlightPromise) {
    strategiesInFlightPromise = fetchStrategies()
      .then((data) => {
        strategiesCache = Array.isArray(data) ? data.filter(Boolean) : [];
        strategiesCacheUpdatedAt = Date.now();
        return strategiesCache;
      })
      .finally(() => {
        strategiesInFlightPromise = null;
      });
  }

  return strategiesInFlightPromise;
}

async function loadSetupsShared(forceFresh = false) {
  if (!forceFresh && hasFreshSetupsCache()) {
    return setupsCache;
  }

  if (!setupsInFlightPromise) {
    setupsInFlightPromise = fetchSetups()
      .then((data) => {
        setupsCache = Array.isArray(data)
          ? data
              .filter(Boolean)
              .map((s) => ({
                ...s,
                setup_type: String(s.setup_type || '').toLowerCase(),
              }))
              .filter((s) => s.setup_type === 'dca' || s.setup_type === 'trade')
          : [];
        setupsCacheUpdatedAt = Date.now();
        return setupsCache;
      })
      .finally(() => {
        setupsInFlightPromise = null;
      });
  }

  return setupsInFlightPromise;
}

// =====================================================================
// 🧠 STRATEGY DATA HOOK (CLEAN V1)
// =====================================================================
export function useStrategyData(options = {}) {
  const { autoLoad = true, includeSetups = true } = options;
  const [strategies, setStrategies] = useState(() => (hasFreshStrategiesCache() ? strategiesCache : []));
  const [setups, setSetups] = useState(() => (includeSetups && hasFreshSetupsCache() ? setupsCache : []));

  const [loading, setLoading] = useState(() => autoLoad && (!hasFreshStrategiesCache() || (includeSetups && !hasFreshSetupsCache())));
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
    if (!autoLoad) {
      setLoading(false);
      return;
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
    };
  }, [autoLoad, includeSetups, loadSetups, loadStrategies]);

  // =========================================================
  // CRUD
  // =========================================================
  async function addStrategy(strategyData) {
    try {
      const created = await createStrategy(strategyData);
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
