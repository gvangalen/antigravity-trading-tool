"use client";

import { fetchWithRetry } from "@/lib/utils/fetchWithRetry";
import { fetchAuth } from "@/lib/api/auth";

const inflightLatestPriceRequests = new Map();
const latestPriceCache = new Map();
const LATEST_PRICE_TTL_MS = 30_000;

//
// =======================================================
// 1) PUBLIC MARKET DATA (GEEN AUTH)
// =======================================================
//

export const fetchMarketData7d = (symbol = "BTC") =>
  fetchWithRetry(`/api/market_data/7d?symbol=${symbol}`, "GET", null, 1, 250, { silent: true });
export const fetchLatestPrice = (symbol = "BTC", options = {}) => {
  const normalizedSymbol = String(symbol || "BTC").toUpperCase();
  const allowCache = options.forceFresh === false;
  const requestKey = `${normalizedSymbol}:${allowCache ? "cached" : "fresh"}`;

  if (allowCache) {
    const cached = latestPriceCache.get(normalizedSymbol);
    if (cached && Date.now() - cached.timestamp < LATEST_PRICE_TTL_MS) {
      return Promise.resolve(cached.data);
    }
  }

  const existing = inflightLatestPriceRequests.get(requestKey);
  if (existing) return existing;

  const request = fetchWithRetry(
    `/api/market_data/${normalizedSymbol}/latest`,
    "GET",
    null,
    1,
    allowCache ? 150 : 300,
    {
      ...(allowCache ? {} : { cache: "no-store" }),
      silent: true,
    }
  ).then((data) => {
    if (allowCache) {
      latestPriceCache.set(normalizedSymbol, {
        data,
        timestamp: Date.now(),
      });
    }
    return data;
  }).finally(() => {
    inflightLatestPriceRequests.delete(requestKey);
  });

  inflightLatestPriceRequests.set(requestKey, request);
  return request;
};
export const fetchLatestBTC = () => fetchLatestPrice("BTC"); // Fallback

export const syncMarketData7d = (symbol = "BTC", overwrite = false) =>
  fetchAuth(`/api/market_data/7d/fill?symbol=${symbol}&overwrite=${overwrite}`, { method: "POST" });

export const fetchForwardReturnsWeek = (symbol = "BTC") =>
  fetchWithRetry(`/api/market_data/forward/week?symbol=${symbol}`, "GET", null, 1, 250, { silent: true });
export const fetchForwardReturnsMonth = (symbol = "BTC") =>
  fetchWithRetry(`/api/market_data/forward/maand?symbol=${symbol}`, "GET", null, 1, 250, { silent: true });
export const fetchForwardReturnsQuarter = (symbol = "BTC") =>
  fetchWithRetry(`/api/market_data/forward/kwartaal?symbol=${symbol}`, "GET", null, 1, 250, { silent: true });
export const fetchForwardReturnsYear = (symbol = "BTC") =>
  fetchWithRetry(`/api/market_data/forward/jaar?symbol=${symbol}`, "GET", null, 1, 250, { silent: true });

//
// =======================================================
// 2) USER MARKET DATA — zoals macro / technical
// =======================================================
//

export const fetchMarketDayData = (symbol = "BTC") =>
  fetchAuth(`/api/market_data/day?symbol=${symbol}`, { method: "GET" });

export const fetchMarketWeekData = (symbol = "BTC") =>
  fetchAuth(`/api/market_data/week?symbol=${symbol}`, { method: "GET" });

export const fetchMarketMonthData = (symbol = "BTC") =>
  fetchAuth(`/api/market_data/month?symbol=${symbol}`, { method: "GET" });

export const fetchMarketQuarterData = (symbol = "BTC") =>
  fetchAuth(`/api/market_data/quarter?symbol=${symbol}`, { method: "GET" });

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

function buildPreferenceQuery(params = {}) {
  const query = new URLSearchParams();
  if (params.symbol) query.set("symbol", String(params.symbol).toUpperCase());
  if (params.assetClass) query.set("asset_class", String(params.assetClass).toLowerCase());
  if (params.scope) query.set("scope", String(params.scope));
  if (params.preset) query.set("preset", String(params.preset));
  const suffix = query.toString();
  return suffix ? `?${suffix}` : "";
}

export const getMarketPreferences = async ({ symbol, assetClass } = {}) =>
  await fetchAuth(`/api/market/preferences${buildPreferenceQuery({ symbol, assetClass })}`, {
    method: "GET",
    forceFresh: true,
  });

export const bootstrapMarketPreferences = async ({
  symbol = null,
  assetClass = null,
  scope = "asset_class",
  preset = "recommended",
} = {}) =>
  await fetchAuth(
    `/api/market/preferences/bootstrap${buildPreferenceQuery({ symbol, assetClass, scope, preset })}`,
    { method: "POST" }
  );

export const syncMarketPreferences = async (symbol) =>
  await fetchAuth(`/api/market/preferences/sync?symbol=${encodeURIComponent(String(symbol || "BTC").toUpperCase())}`, {
    method: "POST",
  });
