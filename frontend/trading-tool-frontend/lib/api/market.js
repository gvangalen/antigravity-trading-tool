"use client";

import { fetchWithRetry } from "@/lib/utils/fetchWithRetry";
import { fetchAuth } from "@/lib/api/auth";

//
// =======================================================
// 1) PUBLIC MARKET DATA (GEEN AUTH)
// =======================================================
//

export const fetchMarketData7d = (symbol = "BTC") => fetchWithRetry(`/api/market_data/7d?symbol=${symbol}`, "GET");
export const fetchLatestPrice = (symbol = "BTC") => fetchWithRetry(`/api/market_data/${symbol}/latest`, "GET");
export const fetchLatestBTC = () => fetchLatestPrice("BTC"); // Fallback

export const syncMarketData7d = (symbol = "BTC", overwrite = false) =>
  fetchAuth(`/api/market_data/7d/fill?symbol=${symbol}&overwrite=${overwrite}`, { method: "POST" });

export const fetchForwardReturnsWeek = (symbol = "BTC") =>
  fetchWithRetry(`/api/market_data/forward/week?symbol=${symbol}`, "GET");
export const fetchForwardReturnsMonth = (symbol = "BTC") =>
  fetchWithRetry(`/api/market_data/forward/maand?symbol=${symbol}`, "GET");
export const fetchForwardReturnsQuarter = (symbol = "BTC") =>
  fetchWithRetry(`/api/market_data/forward/kwartaal?symbol=${symbol}`, "GET");
export const fetchForwardReturnsYear = (symbol = "BTC") =>
  fetchWithRetry(`/api/market_data/forward/jaar?symbol=${symbol}`, "GET");

//
// =======================================================
// 2) USER MARKET DATA — zoals macro / technical
// =======================================================
//

export const fetchMarketDayData = (symbol = "BTC") =>
  fetchAuth(`/api/market_data/day?symbol=${symbol}`, { method: "GET" });

export const fetchUserMarketHistory = (symbol = "BTC") =>
  fetchAuth(`/api/market_data/indicators?symbol=${symbol}`, { method: "GET" });

//
// =======================================================
// 3) MARKET INDICATOR SYSTEM
// =======================================================
//

export const getMarketIndicatorNames = () =>
  fetchAuth(`/api/market/indicator_names`, { method: "GET" });

export const getScoreRulesForMarketIndicator = (name) =>
  fetchAuth(`/api/market/indicator_rules/${encodeURIComponent(name)}`, { method: "GET" });

export const getUserMarketIndicators = (symbol = "BTC") =>
  fetchAuth(`/api/market_data/indicators?symbol=${symbol}`, { method: "GET" });

export const marketIndicatorAdd = (indicatorName, symbol = "BTC") =>
  fetchAuth(`/api/market_data/indicator`, {
    method: "POST",
    body: JSON.stringify({ indicator: indicatorName, symbol }),
  });

// ✅ DELETE OP NAME (zoals macro) + URL encode
export const marketIndicatorDelete = (indicatorName, symbol = "BTC") => {
  if (!indicatorName) throw new Error("indicatorName is verplicht");

  const safe = encodeURIComponent(String(indicatorName).trim().toLowerCase());

  return fetchAuth(`/api/market_data/indicator/${safe}?symbol=${symbol}`, {
    method: "DELETE",
  });
};
// ✅ INITIALIZE ASSET (Triggers background warming)
export const initializeAsset = (symbol) =>
  fetchAuth(`/api/market/asset/initialize`, {
    method: "POST",
    body: JSON.stringify({ symbol }),
  });
