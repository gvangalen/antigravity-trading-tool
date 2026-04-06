"use client";

import { fetchWithRetry } from "@/lib/utils/fetchWithRetry";
import { fetchAuth } from "@/lib/api/auth";

//
// =======================================================
// 1) PUBLIC MARKET DATA (GEEN AUTH)
// =======================================================
//

export const fetchMarketData7d = () => fetchWithRetry(`/api/market_data/7d`, "GET");
export const fetchLatestBTC = () => fetchWithRetry(`/api/market_data/btc/latest`, "GET");

export const fetchForwardReturnsWeek = () =>
  fetchWithRetry(`/api/market_data/forward/week`, "GET");
export const fetchForwardReturnsMonth = () =>
  fetchWithRetry(`/api/market_data/forward/maand`, "GET");
export const fetchForwardReturnsQuarter = () =>
  fetchWithRetry(`/api/market_data/forward/kwartaal`, "GET");
export const fetchForwardReturnsYear = () =>
  fetchWithRetry(`/api/market_data/forward/jaar`, "GET");

//
// =======================================================
// 2) USER MARKET DATA — zoals macro / technical
// =======================================================
//

export const fetchMarketDayData = () =>
  fetchAuth(`/api/market_data/day`, { method: "GET" });

export const fetchUserMarketHistory = () =>
  fetchAuth(`/api/market_data/indicators`, { method: "GET" });

//
// =======================================================
// 3) MARKET INDICATOR SYSTEM
// =======================================================
//

export const getMarketIndicatorNames = () =>
  fetchAuth(`/api/market/indicator_names`, { method: "GET" });

export const getScoreRulesForMarketIndicator = (name) =>
  fetchAuth(`/api/market/indicator_rules/${encodeURIComponent(name)}`, { method: "GET" });

export const getUserMarketIndicators = () =>
  fetchAuth(`/api/market_data/indicators`, { method: "GET" });

export const marketIndicatorAdd = (indicatorName) =>
  fetchAuth(`/api/market_data/indicator`, {
    method: "POST",
    body: JSON.stringify({ indicator: indicatorName }),
  });

// ✅ DELETE OP NAME (zoals macro) + URL encode
export const marketIndicatorDelete = (indicatorName) => {
  if (!indicatorName) throw new Error("indicatorName is verplicht");

  const safe = encodeURIComponent(String(indicatorName).trim().toLowerCase());

  return fetchAuth(`/api/market_data/indicator/${safe}`, {
    method: "DELETE",
  });
};
