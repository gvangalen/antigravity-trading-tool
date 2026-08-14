"use client";

import { fetchAuth } from '@/lib/api/auth';  // ✅ JUISTE AUTH
import { API_BASE_URL } from "@/lib/config";

//
// =======================================================
// 📊 1. Basis macrodata (USER-SPECIFIC → AUTH)
// =======================================================
//

function buildSymbolQuery(symbol = null) {
  return symbol ? `?symbol=${encodeURIComponent(String(symbol).toUpperCase())}` : "";
}

// 📌 Alle macrodata (laatste snapshot per indicator)
export const fetchMacroData = async (symbol = null) => {
  return await fetchAuth(`/api/macro_data${buildSymbolQuery(symbol)}`, { method: "GET" });
};

// 📌 Per periode
export const fetchMacroDataByDay = (symbol = null) =>
  fetchAuth(`/api/macro_data/day${buildSymbolQuery(symbol)}`, { method: "GET" });

export const fetchMacroDataByWeek = (symbol = null) =>
  fetchAuth(`/api/macro_data/week${buildSymbolQuery(symbol)}`, { method: "GET" });

export const fetchMacroDataByMonth = (symbol = null) =>
  fetchAuth(`/api/macro_data/month${buildSymbolQuery(symbol)}`, { method: "GET" });

export const fetchMacroDataByQuarter = (symbol = null) =>
  fetchAuth(`/api/macro_data/quarter${buildSymbolQuery(symbol)}`, { method: "GET" });


//
// =======================================================
// ➕ 2. Indicatorbeheer (user-specific → AUTH!)
// =======================================================
//

// ➕ Indicator toevoegen
export const addMacroIndicator = async (name, symbol = null) => {
  return await fetchAuth(`/api/macro_data`, {
    method: "POST",
    body: JSON.stringify({ name, symbol }),
  });
};

// 🗑 Indicator verwijderen
export const deleteMacroIndicator = async (name, symbol = null) => {
  return await fetchAuth(`/api/macro_data/${name}${buildSymbolQuery(symbol)}`, {
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
export const macroDataAdd = async (indicator, symbol = null) => {
  return await fetchAuth(`/api/macro_data`, {
    method: "POST",
    body: JSON.stringify({ name: indicator, symbol }),
  });
};

function buildPreferenceQuery(params = {}) {
  const query = new URLSearchParams();
  if (params.symbol) query.set("symbol", String(params.symbol).toUpperCase());
  if (params.assetClass) query.set("asset_class", String(params.assetClass).toLowerCase());
  if (params.scope) query.set("scope", String(params.scope));
  if (params.preset) query.set("preset", String(params.preset));
  const suffix = query.toString();
  return suffix ? `?${suffix}` : "";
}

export const getMacroPreferences = async ({ symbol, assetClass } = {}) =>
  await fetchAuth(`/api/macro/preferences${buildPreferenceQuery({ symbol, assetClass })}`, {
    method: "GET",
    forceFresh: true,
  });

export const updateMacroPreferences = async ({
  symbol = null,
  assetClass = null,
  indicators = [],
} = {}) =>
  await fetchAuth(`/api/macro/preferences`, {
    method: "PUT",
    body: JSON.stringify({
      symbol,
      asset_class: assetClass,
      indicators,
    }),
  });

export const bootstrapMacroPreferences = async ({
  symbol = null,
  assetClass = null,
  scope = "asset_class",
  preset = "recommended",
} = {}) =>
  await fetchAuth(
    `/api/macro/preferences/bootstrap${buildPreferenceQuery({ symbol, assetClass, scope, preset })}`,
    { method: "POST" }
  );

export const syncMacroPreferences = async (symbol, { resetExisting = false } = {}) =>
  await fetchAuth(`/api/macro/preferences/sync?symbol=${encodeURIComponent(String(symbol || "BTC").toUpperCase())}&reset_existing=${resetExisting ? "true" : "false"}`, {
    method: "POST",
  });
