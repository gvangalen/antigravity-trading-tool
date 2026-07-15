'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  fetchSetups,
  fetchTopSetups,
  updateSetup,
  deleteSetup,
} from '@/lib/api/setups';

export function useSetupData() {
  const [setups, setSetups] = useState([]);
  const [topSetups, setTopSetups] = useState([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  const [setupTypeFilter, setSetupTypeFilter] = useState(null);

  // ============================================================
  // 🔁 LOAD
  // ============================================================
  const loadSetups = useCallback(async () => {
    setLoading(true);
    setError('');

    try {
      const data = await fetchSetups({
        setup_type: setupTypeFilter,
      });

      setSetups(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('❌ loadSetups fout:', err);
      setError('Kan setups niet laden.');
      setSetups([]);
    } finally {
      setLoading(false);
    }
  }, [setupTypeFilter]);

  const loadTopSetups = useCallback(async () => {
    try {
      const data = await fetchTopSetups();
      setTopSetups(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('❌ loadTopSetups fout:', err);
      setTopSetups([]);
    }
  }, []);

  useEffect(() => {
    loadSetups();
    loadTopSetups();
  }, [loadSetups, loadTopSetups]);

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
      await loadSetups();
    } catch (err) {
      console.error('❌ saveSetup fout:', err);
      setError('Opslaan mislukt.');
    }
  }, [loadSetups]);

  // ============================================================
  // 🗑 4. Setup verwijderen
  // ============================================================
  const removeSetup = useCallback(async (id) => {
    try {
      await deleteSetup(id);
      await loadSetups();
    } catch (err) {
      console.error('❌ removeSetup fout:', err);
      setError('Verwijderen mislukt.');
    }
  }, [loadSetups]);

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
