'use client';

import { fetchAuth } from '@/lib/api/auth';  // ✅ JUISTE AUTH
import { API_BASE_URL } from '@/lib/config';

//
// =============================================================
// 📥 1. Alle technische data ophalen (user-specific)
// =============================================
export const technicalDataAll = async (symbol = "BTC") => {
  console.log(`📡 [technicalDataAll] GET /api/technical_data?symbol=${symbol}`);

  const data = await fetchAuth(`/api/technical_data?symbol=${symbol}`, {
    method: "GET",
  });

  return data || [];
};


//
// =============================================================
// ➕ 2. Technische indicator toevoegen (user-specific)
// =============================================================
export const technicalDataAdd = async (indicator, symbol = "BTC") => {
  console.log(`➕ [technicalDataAdd] Indicator toevoegen: ${indicator} voor ${symbol}`);

  const payload = {
    indicator,
    symbol,
    value: 0.0,   
    score: 0,
    advies: null,
    uitleg: null,
  };

  return await fetchAuth(`/api/technical_data`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
};


//
// =============================================================
// 🗑️ 3. Eén technische indicator verwijderen
// =============================================================
export const technicalDataDelete = async (indicator, symbol = "BTC") => {
  console.log(`🗑️ [technicalDataDelete] DELETE /api/technical_data/${indicator}?symbol=${symbol}`);

  return await fetchAuth(`/api/technical_data/${indicator}?symbol=${symbol}`, {
    method: "DELETE",
  });
};

// alias
export const deleteTechnicalIndicator = technicalDataDelete;


//
// =============================================================
// 📆 4. Periodieke data (day / week / month / quarter)
// =============================================================
export const technicalDataDay = async (symbol = "BTC") =>
  await fetchAuth(`/api/technical_data/day?symbol=${symbol}`, { method: "GET" });

export const technicalDataWeek = async (symbol = "BTC") =>
  await fetchAuth(`/api/technical_data/week?symbol=${symbol}`, { method: "GET" });

export const technicalDataMonth = async (symbol = "BTC") =>
  await fetchAuth(`/api/technical_data/month?symbol=${symbol}`, { method: "GET" });

export const technicalDataQuarter = async (symbol = "BTC") =>
  await fetchAuth(`/api/technical_data/quarter?symbol=${symbol}`, { method: "GET" });


//
// =============================================================
// 🧠 5. Scorelogica + configuratie (user-specific)
// =============================================================

// Beschikbare technische indicatornamen
export const getIndicatorNames = async () =>
  await fetchAuth(`/api/technical/indicators`, { method: "GET" });

// Scoreregels voor één indicator
export const getScoreRulesForIndicator = async (indicatorName) =>
  await fetchAuth(`/api/technical_indicator_rules/${indicatorName}`, {
    method: "GET",
  });

//
// =============================================================
// 📈 6. Historie ophalen (Sparklines)
// =============================================================
export const fetchIndicatorHistory = async (indicatorName, limit = 20) => {
  return await fetchAuth(`/api/technical/history/${indicatorName}?limit=${limit}`, {
    method: "GET",
  });
};
