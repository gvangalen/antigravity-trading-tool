"use client";

import { fetchAuth } from '@/lib/api/auth';  // ✅ JUISTE AUTH
import { API_BASE_URL } from "@/lib/config";

//
// =========================
// 🧠 INSIGHTS PER CATEGORIE
// =========================
//

// Iedere endpoint geeft terug: { insight: "..." }
export const fetchMacroInsight = async () => {
  const res = await fetchAuth(`/api/agents/insights/macro`, { method: "GET" });
  return res?.insight ?? null;
};

export const fetchMarketInsight = async () => {
  const res = await fetchAuth(`/api/agents/insights/market`, { method: "GET" });
  return res?.insight ?? null;
};

export const fetchTechnicalInsight = async () => {
  const res = await fetchAuth(`/api/agents/insights/technical`, { method: "GET" });
  return res?.insight ?? null;
};

export const fetchSetupInsight = async () => {
  const res = await fetchAuth(`/api/agents/insights/setup`, { method: "GET" });
  return res?.insight ?? null;
};

export const fetchStrategyInsight = async () => {
  const res = await fetchAuth(`/api/agents/insights/strategy`, { method: "GET" });
  console.log("STRATEGY INSIGHT RAW:", res);

  return res?.insight ?? null;  // 🔥 FIX
};

//
// ============================
// 🪞 REFLECTIES PER CATEGORIE
// ============================
//

// Iedere endpoint geeft terug: { reflections: [] }
export const fetchMacroReflections = async () => {
  const res = await fetchAuth(`/api/agents/reflections/macro`, { method: "GET" });
  return res?.reflections ?? [];
};

export const fetchMarketReflections = async () => {
  const res = await fetchAuth(`/api/agents/reflections/market`, { method: "GET" });
  return res?.reflections ?? [];
};

export const fetchTechnicalReflections = async () => {
  const res = await fetchAuth(`/api/agents/reflections/technical`, { method: "GET" });
  return res?.reflections ?? [];
};

export const fetchSetupReflections = async () => {
  const res = await fetchAuth(`/api/agents/reflections/setup`, { method: "GET" });
  return res?.reflections ?? [];
};

export const fetchStrategyReflections = async () => {
  const res = await fetchAuth(`/api/agents/reflections/strategy`, { method: "GET" });
  return res?.reflections ?? [];
};

//
// ============================
// 🎯 ACTIEVE STRATEGIE (VANDAAG)
// ============================
//

// Geeft terug:
// {
//   active: true/false,
//   entry,
//   targets,
//   stop_loss,
//   confidence_score,
//   adjustment_reason,
//   changes,
//   market_context,
//   setup_name,
//   symbol,
//   timeframe
// }

export const fetchActiveStrategyToday = async () => {
  const res = await fetchAuth(`/api/strategy/active/today`, {
    method: "GET",
  });

  // Geen actieve strategie = card kan "geen signaal vandaag" tonen
  if (!res || res.active === false) {
    return null;
  }

  return res;
};
