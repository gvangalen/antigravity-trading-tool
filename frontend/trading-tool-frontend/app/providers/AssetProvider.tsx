"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import { useAuth } from "@/components/auth/AuthProvider";
import { useWatchlist } from "@/hooks/useWatchlist";
import { API_BASE_URL } from "@/lib/config";
import { buildAuthHeaders } from "@/lib/api/auth";
import { readOnboardingAssetPreference } from "@/lib/onboardingAsset";

const preferredAssetCache = new Map<string, string | null>();
const preferredAssetPromise = new Map<string, Promise<string | null>>();
const DEFAULT_SELECTED_ASSET = "BTC";
const DEFAULT_AVAILABLE_ASSETS = ["BTC", "ETH", "SOL", "ADA", "DOT"];
const LEGACY_SELECTED_ASSET_KEY = "selectedAsset";

function selectedAssetStorageKey(userId: string | number | null | undefined) {
  const normalized = String(userId || "").trim();
  return normalized ? `selectedAsset:${normalized}` : LEGACY_SELECTED_ASSET_KEY;
}

function normalizeAssetSymbol(asset: string | null | undefined) {
  const normalized = String(asset || "").trim().toUpperCase();
  return /^[A-Z0-9._:-]{1,20}$/.test(normalized) ? normalized : "";
}

function buildAvailableAssets(symbols: Array<string | null | undefined>) {
  const normalized = symbols
    .map((symbol) => normalizeAssetSymbol(symbol))
    .filter(Boolean);

  return Array.from(new Set(normalized));
}

type AssetContextType = {
  selectedAsset: string;
  setSelectedAsset: (asset: string) => void;
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
  const [selectedAsset, setSelectedAssetState] = useState<string>(DEFAULT_SELECTED_ASSET);
  const [availableAssets, setAvailableAssets] = useState<string[]>(DEFAULT_AVAILABLE_ASSETS);
  const [preferencesHydrated, setPreferencesHydrated] = useState(false);
  const userStorageKey = selectedAssetStorageKey(user?.id);

  // Load from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem(userStorageKey);
    const normalized = normalizeAssetSymbol(saved);
    if (normalized) {
      setSelectedAssetState(normalized);
    }
  }, [userStorageKey]);

  useEffect(() => {
    if (isPublicAuthRoute || preferencesHydrated || !sessionChecked) return;

    if (!user?.id) {
      setPreferencesHydrated(true);
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
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
        const savedAsset = normalizeAssetSymbol(localStorage.getItem(userStorageKey));
        if (savedAsset) {
          setSelectedAssetState(savedAsset);
          setAvailableAssets((current) => (current.includes(savedAsset) ? current : [...current, savedAsset]));
          return;
        }

        const preferredAsset = await fetchPreferredAsset();
        if (!preferredAsset) return;
        if (cancelled) return;

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

    timer = setTimeout(() => {
      void hydrateSelectedAssetFromPreferences();
    }, 600);

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [preferencesHydrated, sessionChecked, user?.id, user?.ai_preferences, userStorageKey]);

  useEffect(() => {
    setPreferencesHydrated(false);
  }, [user?.id]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (user?.id) {
      localStorage.removeItem(LEGACY_SELECTED_ASSET_KEY);
      return;
    }
    const legacyAsset = normalizeAssetSymbol(localStorage.getItem(LEGACY_SELECTED_ASSET_KEY));
    if (legacyAsset) {
      setSelectedAssetState(legacyAsset);
    }
  }, [user?.id]);

  useEffect(() => {
    const watchlistSymbols = Array.isArray(watchlist)
      ? watchlist.map((item) => item?.symbol)
      : [];
    const nextAvailableAssets = buildAvailableAssets(
      watchlistSymbols.length
        ? [...watchlistSymbols, selectedAsset]
        : [selectedAsset, ...DEFAULT_AVAILABLE_ASSETS]
    );

    setAvailableAssets(nextAvailableAssets.length ? nextAvailableAssets : DEFAULT_AVAILABLE_ASSETS);
  }, [selectedAsset, watchlist]);

  const setSelectedAsset = (asset: string) => {
    const normalized = normalizeAssetSymbol(asset);
    if (!normalized) return;
    setSelectedAssetState(normalized);
    localStorage.setItem(userStorageKey, normalized);
  };

  const addAsset = (asset: string) => {
    const up = normalizeAssetSymbol(asset);
    if (!up) return;
    setAvailableAssets((current) => (current.includes(up) ? current : [...current, up]));
  };

  return (
    <AssetContext.Provider value={{ 
      selectedAsset, 
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
