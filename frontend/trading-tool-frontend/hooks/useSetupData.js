'use client';

import { useEffect, useState } from 'react';
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
  useEffect(() => {
    loadSetups();
    loadTopSetups();
  }, [setupTypeFilter]);

  // ============================================================
  // 🔁 1. Setups ophalen
  // ============================================================
  async function loadSetups() {
    console.log('🔍 loadSetups gestart');
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
  }

  // ============================================================
  // ⭐ 2. Top setups
  // ============================================================
  async function loadTopSetups() {
    try {
      const data = await fetchTopSetups();
      setTopSetups(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('❌ loadTopSetups fout:', err);
      setTopSetups([]);
    }
  }

  // ============================================================
  // 💾 3. Setup bijwerken
  // ============================================================
  async function saveSetup(id, updatedData) {
    try {
      await updateSetup(id, updatedData);
      setSuccessMessage('Setup succesvol opgeslagen.');
      await loadSetups();
    } catch (err) {
      console.error('❌ saveSetup fout:', err);
      setError('Opslaan mislukt.');
    }
  }

  // ============================================================
  // 🗑 4. Setup verwijderen
  // ============================================================
  async function removeSetup(id) {
    try {
      await deleteSetup(id);
      await loadSetups();
    } catch (err) {
      console.error('❌ removeSetup fout:', err);
      setError('Verwijderen mislukt.');
    }
  }

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
