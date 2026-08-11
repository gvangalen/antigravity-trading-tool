'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  fetchCachedResource,
  getCachedResourceSnapshot,
  markCachedResourceStale,
  subscribeCachedResource,
} from '@/lib/clientDataCache';
import {
  fetchSetups,
  fetchTopSetups,
  updateSetup,
  deleteSetup,
} from '@/lib/api/setups';

const SETUPS_CACHE_TTL_MS = 60_000;
const setupsCacheKey = (setupTypeFilter) => `setups:list:${setupTypeFilter || 'all'}`;
const TOP_SETUPS_CACHE_KEY = 'setups:top';

export function useSetupData() {
  const initialSetups = getCachedResourceSnapshot(setupsCacheKey(null), []);
  const initialTopSetups = getCachedResourceSnapshot(TOP_SETUPS_CACHE_KEY, []);
  const [setups, setSetups] = useState([]);
  const [topSetups, setTopSetups] = useState(initialTopSetups.data || []);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  const [setupTypeFilter, setSetupTypeFilter] = useState(null);

  // ============================================================
  // 🔁 LOAD
  // ============================================================
  const loadSetups = useCallback(async () => {
    const cacheKey = setupsCacheKey(setupTypeFilter);
    if (!getCachedResourceSnapshot(cacheKey, []).hasData) {
      setLoading(true);
    }
    setError('');

    try {
      const data = await fetchCachedResource(cacheKey, {
        ttlMs: SETUPS_CACHE_TTL_MS,
        initialData: [],
        fetcher: async () => {
          const next = await fetchSetups({
            setup_type: setupTypeFilter,
          });
          return Array.isArray(next) ? next : [];
        },
      });
      setSetups(data || []);
    } catch (err) {
      console.error('❌ loadSetups fout:', err);
      setError('Kan setups niet laden.');
    } finally {
      setLoading(false);
    }
  }, [setupTypeFilter]);

  const loadTopSetups = useCallback(async () => {
    try {
      const data = await fetchCachedResource(TOP_SETUPS_CACHE_KEY, {
        ttlMs: SETUPS_CACHE_TTL_MS,
        initialData: [],
        fetcher: async () => {
          const next = await fetchTopSetups();
          return Array.isArray(next) ? next : [];
        },
      });
      setTopSetups(data || []);
    } catch (err) {
      console.error('❌ loadTopSetups fout:', err);
    }
  }, []);

  useEffect(() => {
    const cacheKey = setupsCacheKey(setupTypeFilter);
    const snapshot = getCachedResourceSnapshot(cacheKey, []);
    if (snapshot.hasData) {
      setSetups(snapshot.data || []);
    } else if (setupTypeFilter === null && initialSetups.hasData) {
      setSetups(initialSetups.data || []);
    }
    const unsubscribeSetups = subscribeCachedResource(cacheKey, () => {
      setSetups(getCachedResourceSnapshot(cacheKey, []).data || []);
    });
    const unsubscribeTopSetups = subscribeCachedResource(TOP_SETUPS_CACHE_KEY, () => {
      setTopSetups(getCachedResourceSnapshot(TOP_SETUPS_CACHE_KEY, []).data || []);
    });
    loadSetups();
    loadTopSetups();
    return () => {
      unsubscribeSetups();
      unsubscribeTopSetups();
    };
  }, [loadSetups, loadTopSetups, setupTypeFilter]);

  // ============================================================
  // 🔁 1. Setups ophalen
  // ============================================================
  // ============================================================
  // 💾 3. Setup bijwerken
  // ============================================================
  const saveSetup = useCallback(async (id, updatedData) => {
    try {
      await updateSetup(id, updatedData);
      setSuccessMessage('Setup succesvol opgeslagen.');
      markCachedResourceStale(setupsCacheKey(setupTypeFilter));
      markCachedResourceStale(TOP_SETUPS_CACHE_KEY);
      await loadSetups();
      await loadTopSetups();
    } catch (err) {
      console.error('❌ saveSetup fout:', err);
      setError('Opslaan mislukt.');
    }
  }, [loadSetups, loadTopSetups, setupTypeFilter]);

  // ============================================================
  // 🗑 4. Setup verwijderen
  // ============================================================
  const removeSetup = useCallback(async (id) => {
    try {
      await deleteSetup(id);
      markCachedResourceStale(setupsCacheKey(setupTypeFilter));
      markCachedResourceStale(TOP_SETUPS_CACHE_KEY);
      await loadSetups();
      await loadTopSetups();
    } catch (err) {
      console.error('❌ removeSetup fout:', err);
      setError('Verwijderen mislukt.');
    }
  }, [loadSetups, loadTopSetups, setupTypeFilter]);

  // ============================================================
  // 🔍 5. Naam-check
  // ============================================================
  function checkSetupNameExists(name) {
    return setups.some(
      (s) => s.name.toLowerCase() === name.toLowerCase()
    );
  }

  // ============================================================
  // 📤 PUBLIC API
  // ============================================================
  return {
    setups,
    topSetups,

    loading,
    error,
    successMessage,

    setupTypeFilter,
    setSetupTypeFilter,

    // actions
    loadSetups,
    reloadSetups: loadSetups, // ✅ FIX
    loadTopSetups,
    saveSetup,
    removeSetup,
    checkSetupNameExists,
  };
}
