"use client";

import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";
import { useAuth } from "@/components/auth/AuthProvider";
import { useWatchlist } from "@/hooks/useWatchlist";
import { API_BASE_URL } from "@/lib/config";
import { buildAuthHeaders } from "@/lib/api/auth";
import { normalizeScopedAssetSymbol, resolveScopedAssetStatus } from "@/lib/finnAssetIsolation";
import { readOnboardingAssetPreference } from "@/lib/onboardingAsset";

const preferredAssetCache = new Map<string, string | null>();
const preferredAssetPromise = new Map<string, Promise<string | null>>();
const DEFAULT_AVAILABLE_ASSETS = ["BTC", "ETH", "SOL", "ADA", "DOT"];
const LEGACY_SELECTED_ASSET_KEY = "selectedAsset";

function selectedAssetStorageKey(userId: string | number | null | undefined) {
  const normalized = String(userId || "").trim();
  return normalized ? `selectedAsset:${normalized}` : LEGACY_SELECTED_ASSET_KEY;
}

function buildAvailableAssets(symbols: Array<string | null | undefined>) {
  const normalized = symbols
    .map((symbol) => normalizeScopedAssetSymbol(symbol) || "")
    .filter(Boolean);

  return Array.from(new Set(normalized));
}

type AssetContextType = {
  selectedAsset: string | null;
  assetStatus: "loading" | "resolved" | "unconfigured";
  setSelectedAsset: (asset: string | null) => void;
  availableAssets: string[];
  addAsset: (asset: string) => void;
};

const AssetContext = createContext<AssetContextType | null>(null);

export function AssetProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, sessionChecked } = useAuth() as any;
  const path = pathname || "/";
  const isPublicAuthRoute =
    path.startsWith("/login") ||
    path.startsWith("/register") ||
    path.startsWith("/forgot-password") ||
    path.startsWith("/reset-password");
  const { watchlist } = useWatchlist({
    autoLoad: !isPublicAuthRoute && sessionChecked && Boolean(user?.id),
  });
  const [selectedAsset, setSelectedAssetState] = useState<string | null>(null);
  const [availableAssets, setAvailableAssets] = useState<string[]>(DEFAULT_AVAILABLE_ASSETS);
  const [preferencesHydrated, setPreferencesHydrated] = useState(false);
  const userStorageKey = selectedAssetStorageKey(user?.id);
  const isAuthenticated = Boolean(user?.id);
  const assetStatus = useMemo<AssetContextType["assetStatus"]>(() => {
    return resolveScopedAssetStatus({
      isPublicAuthRoute,
      sessionChecked,
      isAuthenticated,
      preferencesHydrated,
      selectedAsset,
    });
  }, [isAuthenticated, isPublicAuthRoute, preferencesHydrated, selectedAsset, sessionChecked]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!sessionChecked || isPublicAuthRoute) return;

    const saved = normalizeScopedAssetSymbol(localStorage.getItem(userStorageKey));
    if (saved) {
      setSelectedAssetState(saved);
      return;
    }

    if (!isAuthenticated) {
      const legacy = normalizeScopedAssetSymbol(localStorage.getItem(LEGACY_SELECTED_ASSET_KEY));
      setSelectedAssetState(legacy || null);
    }
  }, [isAuthenticated, isPublicAuthRoute, sessionChecked, userStorageKey]);

  useEffect(() => {
    if (isPublicAuthRoute || preferencesHydrated || !sessionChecked) return;

    if (!user?.id) {
      setPreferencesHydrated(true);
      return;
    }

    let cancelled = false;
    const userKey = String(user.id);

    async function fetchPreferredAsset() {
      const assetFromUser = readOnboardingAssetPreference(user?.ai_preferences || {});
      if (assetFromUser) {
        preferredAssetCache.set(userKey, assetFromUser);
        return assetFromUser;
      }

      if (preferredAssetCache.has(userKey)) {
        return preferredAssetCache.get(userKey) || null;
      }

      if (!preferredAssetPromise.has(userKey)) {
        preferredAssetPromise.set(
          userKey,
          fetch(`${API_BASE_URL}/api/assistant/preferences`, {
            method: "GET",
            credentials: "include",
            headers: Object.fromEntries(buildAuthHeaders(undefined, "GET").entries()),
          })
            .then(async (response) => {
              if (!response.ok) return null;
              const payload = await response.json().catch(() => null);
              const asset = readOnboardingAssetPreference(payload?.preferences || {});
              preferredAssetCache.set(userKey, asset || null);
              return asset || null;
            })
            .catch(() => null)
            .finally(() => {
              preferredAssetPromise.delete(userKey);
            })
        );
      }

      return preferredAssetPromise.get(userKey) || null;
    }

    async function hydrateSelectedAssetFromPreferences() {
      try {
        const savedAsset = normalizeScopedAssetSymbol(localStorage.getItem(userStorageKey));
        if (savedAsset) {
          setSelectedAssetState(savedAsset);
          setAvailableAssets((current) => (current.includes(savedAsset) ? current : [...current, savedAsset]));
          return;
        }

        const preferredAsset = await fetchPreferredAsset();
        if (cancelled) return;
        if (!preferredAsset) {
          setSelectedAssetState(null);
          return;
        }

        setSelectedAssetState(preferredAsset);
        localStorage.setItem(userStorageKey, preferredAsset);
        setAvailableAssets((current) =>
          current.includes(preferredAsset) ? current : [...current, preferredAsset]
        );
      } catch (error) {
        // Silent by design: public routes and expired sessions should not spam logs here.
      } finally {
        if (!cancelled) {
          setPreferencesHydrated(true);
        }
      }
    }

    void hydrateSelectedAssetFromPreferences();

    return () => {
      cancelled = true;
    };
  }, [preferencesHydrated, sessionChecked, user?.id, user?.ai_preferences, userStorageKey]);

  useEffect(() => {
    setSelectedAssetState(null);
    setPreferencesHydrated(false);
  }, [user?.id]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (user?.id) {
      localStorage.removeItem(LEGACY_SELECTED_ASSET_KEY);
      return;
    }
      const legacyAsset = normalizeScopedAssetSymbol(localStorage.getItem(LEGACY_SELECTED_ASSET_KEY));
    setSelectedAssetState(legacyAsset || null);
  }, [user?.id]);

  useEffect(() => {
    const watchlistSymbols = Array.isArray(watchlist)
      ? watchlist.map((item) => item?.symbol)
      : [];
    const nextAvailableAssets = buildAvailableAssets(
      watchlistSymbols.length
        ? [...watchlistSymbols, selectedAsset]
        : [selectedAsset, ...(isAuthenticated ? [] : DEFAULT_AVAILABLE_ASSETS)]
    );

    setAvailableAssets(nextAvailableAssets.length ? nextAvailableAssets : DEFAULT_AVAILABLE_ASSETS);
  }, [isAuthenticated, selectedAsset, watchlist]);

  const setSelectedAsset = (asset: string | null) => {
    if (asset == null) {
      setSelectedAssetState(null);
      localStorage.removeItem(userStorageKey);
      return;
    }
    const normalized = normalizeScopedAssetSymbol(asset);
    if (!normalized) return;
    setSelectedAssetState(normalized);
    localStorage.setItem(userStorageKey, normalized);
  };

  const addAsset = (asset: string) => {
    const up = normalizeScopedAssetSymbol(asset);
    if (!up) return;
    setAvailableAssets((current) => (current.includes(up) ? current : [...current, up]));
  };

  return (
    <AssetContext.Provider value={{ 
      selectedAsset, 
      assetStatus,
      setSelectedAsset, 
      availableAssets,
      addAsset
    }}>
      {children}
    </AssetContext.Provider>
  );
}

export function useAsset() {
  const context = useContext(AssetContext);
  if (!context) {
    throw new Error("useAsset must be used within an AssetProvider");
  }
  return context;
}
