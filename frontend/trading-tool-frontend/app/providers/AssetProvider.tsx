"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import { useAuth } from "@/components/auth/AuthProvider";
import { API_BASE_URL } from "@/lib/config";
import { buildAuthHeaders } from "@/lib/api/auth";
import { normalizeOnboardingAsset, readOnboardingAssetPreference } from "@/lib/onboardingAsset";

const preferredAssetCache = new Map<string, string | null>();
const preferredAssetPromise = new Map<string, Promise<string | null>>();

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
  const [selectedAsset, setSelectedAssetState] = useState<string>("BTC");
  const [availableAssets, setAvailableAssets] = useState<string[]>(["BTC", "ETH", "SOL", "ADA", "DOT"]);
  const [preferencesHydrated, setPreferencesHydrated] = useState(false);

  // Load from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem("selectedAsset");
    const normalized = normalizeOnboardingAsset(saved);
    if (normalized) {
      setSelectedAssetState(normalized);
    }
  }, []);

  useEffect(() => {
    const path = pathname || "/";
    const isPublicAuthRoute =
      path.startsWith("/login") ||
      path.startsWith("/register") ||
      path.startsWith("/forgot-password") ||
      path.startsWith("/reset-password");

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
        const preferredAsset = await fetchPreferredAsset();
        if (!preferredAsset) return;
        if (cancelled) return;

        setSelectedAssetState(preferredAsset);
        localStorage.setItem("selectedAsset", preferredAsset);
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
  }, [pathname, preferencesHydrated, sessionChecked, user?.id, user?.ai_preferences]);

  useEffect(() => {
    setPreferencesHydrated(false);
  }, [user?.id]);

  const setSelectedAsset = (asset: string) => {
    const normalized = normalizeOnboardingAsset(asset);
    if (!normalized) return;
    setSelectedAssetState(normalized);
    localStorage.setItem("selectedAsset", normalized);
  };

  const addAsset = (asset: string) => {
    const up = normalizeOnboardingAsset(asset);
    if (!up) return;
    if (!availableAssets.includes(up)) {
      setAvailableAssets([...availableAssets, up]);
    }
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
