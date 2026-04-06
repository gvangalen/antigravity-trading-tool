"use client";

import { fetchAuth } from '@/lib/api/auth';  // ✅ JUISTE AUTH
import { API_BASE_URL } from "@/lib/config";

//
// =======================================================
// 📊 1. Basis macrodata (USER-SPECIFIC → AUTH)
// =======================================================
//

// 📌 Alle macrodata (laatste snapshot per indicator)
export const fetchMacroData = async () => {
  return await fetchAuth(`/api/macro_data`, { method: "GET" });
};

// 📌 Per periode
export const fetchMacroDataByDay = () =>
  fetchAuth(`/api/macro_data/day`, { method: "GET" });

export const fetchMacroDataByWeek = () =>
  fetchAuth(`/api/macro_data/week`, { method: "GET" });

export const fetchMacroDataByMonth = () =>
  fetchAuth(`/api/macro_data/month`, { method: "GET" });

export const fetchMacroDataByQuarter = () =>
  fetchAuth(`/api/macro_data/quarter`, { method: "GET" });


//
// =======================================================
// ➕ 2. Indicatorbeheer (user-specific → AUTH!)
// =======================================================
//

// ➕ Indicator toevoegen
export const addMacroIndicator = async (name) => {
  return await fetchAuth(`/api/macro_data`, {
    method: "POST",
    body: JSON.stringify({ name }),
  });
};

// 🗑 Indicator verwijderen
export const deleteMacroIndicator = async (name) => {
  return await fetchAuth(`/api/macro_data/${name}`, {
    method: "DELETE",
  });
};


//
// =======================================================
// 🧠 3. Scorelogica & configuratie (user-specific)
// =======================================================
//

// 📋 Namen van beschikbare macro-indicatoren
export const getMacroIndicatorNames = async () => {
  return await fetchAuth(`/api/macro/indicators`, { method: "GET" });
};

// 📊 Scoreregels voor een indicator
export const getScoreRulesForMacroIndicator = async (indicatorName) => {
  if (!indicatorName) return [];
  return await fetchAuth(`/api/macro_indicator_rules/${indicatorName}`, {
    method: "GET",
  });
};

// Alias voor consistentie
export const macroDataAdd = async (indicator) => {
  return await fetchAuth(`/api/macro_data`, {
    method: "POST",
    body: JSON.stringify({ name: indicator }),
  });
};
