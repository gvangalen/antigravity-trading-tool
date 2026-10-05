'use client';

import { fetchAuth } from '@/lib/api/auth';
import { toast } from 'react-hot-toast';
import { normalizeSetupSaveResponse } from '@/lib/setup/activeSetup';

const normalizePublicSetup = (setup) => normalizeSetupSaveResponse(setup) || setup;

//
// =========================================================
// 1. ALLE SETUPS OPHALEN (met setup_type filter)
// =========================================================
export const fetchSetups = async ({ setup_type = '' } = {}) => {
  try {
    const query = new URLSearchParams();

    if (setup_type) query.append('setup_type', setup_type);

    const url = `/api/setups${query.toString() ? `?${query.toString()}` : ''}`;

    const result = await fetchAuth(url, { method: 'GET' });
    return Array.isArray(result) ? result.map(normalizePublicSetup) : [];
  } catch (err) {
    console.error('❌ [fetchSetups] Fout:', err);
    toast.error('Setups laden mislukt.');
    throw err;
  }
};

//
// =========================================================
// SETUP UPDATEN
// =========================================================
export const updateSetup = async (id, updatedData) => {
  try {
    const res = await fetchAuth(`/api/setups/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(updatedData),
    });

    toast.success('Setup bijgewerkt!');
    return res;
  } catch (err) {
    console.error('❌ [updateSetup] Fout:', err);
    toast.error('Bijwerken mislukt.');
    throw err;
  }
};

//
// =========================================================
// 4. SETUP VERWIJDEREN
// =========================================================
export const deleteSetup = async (id) => {
  try {
    await fetchAuth(`/api/setups/${id}`, {
      method: 'DELETE',
    });

    toast.success('Setup verwijderd!');
  } catch (err) {
    console.error('❌ [deleteSetup] Fout:', err);
    toast.error('Verwijderen mislukt.');
    throw err;
  }
};

//
// =========================================================
// 5. NIEUWE SETUP OPSLAAN
// =========================================================
export const saveNewSetup = async (newData) => {
  try {
    return await fetchAuth('/api/setups', {
      method: 'POST',
      body: JSON.stringify(newData),
    });
  } catch (err) {
    console.error('❌ [saveNewSetup] Fout:', err);
    throw err;
  }
};

//
// =========================================================
// CHECK OF NAAM BESTAAT
// =========================================================
export const checkSetupNameExists = async (name) => {
  try {
    const res = await fetchAuth(
      `/api/setups/check_name/${encodeURIComponent(name)}`,
      { method: 'GET' }
    );
    return res?.exists === true;
  } catch {
    return false;
  }
};

//
// =========================================================
// 8. LAATSTE SETUP
// =========================================================
export const fetchLastSetup = async () => {
  try {
    const res = await fetchAuth('/api/setups/last', { method: 'GET' });
    return normalizePublicSetup(res?.setup ?? null);
  } catch {
    return null;
  }
};

//
// =========================================================
// 9. ACTIEVE SETUP
// =========================================================
export const fetchActiveSetup = async (symbol = "BTC") => {
  try {
    const query = new URLSearchParams();
    if (symbol) query.set("symbol", String(symbol).toUpperCase());
    const res = await fetchAuth(`/api/setups/active${query.toString() ? `?${query.toString()}` : ""}`, { method: 'GET' });
    return normalizePublicSetup(res?.active ?? null);
  } catch (err) {
    console.error('❌ [fetchActiveSetup] Fout:', err);
    toast.error('Actieve setup laden mislukt.');
    return null;
  }
};

//
// =========================================================
// 10. DAGELIJKSE SETUP SCORES
// =========================================================
export const fetchSetupMarketMatches = async () => {
  try {
    const res = await fetchAuth('/api/setups/market-matches', {
      method: 'GET',
    });

    return Array.isArray(res) ? res : [];
  } catch (err) {
    console.error('❌ [fetchSetupMarketMatches] Fout:', err);
    toast.error('Setupmatches laden mislukt.');
    return [];
  }
};
