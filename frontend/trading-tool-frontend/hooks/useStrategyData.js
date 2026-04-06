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
      setStrategies(Array.isArray(data) ? data.filter(Boolean) : []);
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
  
    } catch (err) {
      console.error('❌ loadSetups fout:', err);
      setError('Fout bij laden setups.');
      setSetups([]);
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
      await createStrategy(strategyData);
      setSuccessMessage('Strategie toegevoegd.');
      await loadStrategies();
    } catch (err) {
      console.error('❌ addStrategy fout:', err);
      setError('Toevoegen mislukt.');
    }
  }

  async function saveStrategy(id, updatedData) {
    try {
      await updateStrategy(id, updatedData);
      setSuccessMessage('Strategie opgeslagen.');
      await loadStrategies();
    } catch (err) {
      console.error('❌ saveStrategy fout:', err);
      setError('Opslaan mislukt.');
    }
  }

  async function removeStrategy(id) {
    try {
      await deleteStrategy(id);
      setSuccessMessage('Strategie verwijderd.');
      await loadStrategies();
    } catch (err) {
      console.error('❌ removeStrategy fout:', err);
      setError('Verwijderen mislukt.');
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
