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


// =====================================================================
// 🧠 STRATEGY DATA HOOK (CLEAN V1)
// =====================================================================
export function useStrategyData() {
  const [strategies, setStrategies] = useState([]);
  const [setups, setSetups] = useState([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  // =========================================================
  // LOAD STRATEGIES
  // =========================================================
  const loadStrategies = useCallback(async () => {
    setLoading(true);
    setError('');

    try {
      const data = await fetchStrategies();
      const cleaned = Array.isArray(data) ? data.filter(Boolean) : [];
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
  const loadSetups = useCallback(async () => {
    setError('');
  
    try {
      const data = await fetchSetups();
  
      const cleaned = Array.isArray(data)
        ? data
            .filter(Boolean)
            .map((s) => ({
              ...s,
              setup_type: String(s.setup_type || '').toLowerCase(),
            }))
            .filter((s) => s.setup_type === 'dca' || s.setup_type === 'trade')
        : [];
  
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
    loadSetups();
    loadStrategies();
  }, [loadSetups, loadStrategies]);

  // =========================================================
  // CRUD
  // =========================================================
  async function addStrategy(strategyData) {
    try {
      const created = await createStrategy(strategyData);
      setSuccessMessage('Strategie toegevoegd.');
      await loadStrategies();
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
      await loadStrategies();
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
      await loadStrategies();
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
      await loadStrategies();
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
      await loadStrategies();
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
