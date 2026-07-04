"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import { API_BASE_URL } from "@/lib/config";
import { buildAuthHeaders } from "@/lib/api/auth";
import { normalizeOnboardingAsset, readOnboardingAssetPreference } from "@/lib/onboardingAsset";

type AssetContextType = {
  selectedAsset: string;
  setSelectedAsset: (asset: string) => void;
  availableAssets: string[];
  addAsset: (asset: string) => void;
};

const AssetContext = createContext<AssetContextType | null>(null);

export function AssetProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [selectedAsset, setSelectedAssetState] = useState<string>("BTC");
  const [availableAssets, setAvailableAssets] = useState<string[]>(["BTC", "ETH", "SOL", "ADA", "DOT"]);

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

    if (isPublicAuthRoute) return;

    let cancelled = false;

    async function hydrateSelectedAssetFromPreferences() {
      try {
        const response = await fetch(`${API_BASE_URL}/api/assistant/preferences`, {
          method: "GET",
          credentials: "include",
          headers: Object.fromEntries(buildAuthHeaders(undefined, "GET").entries()),
        });
        if (!response.ok || cancelled) return;

        const payload = await response.json().catch(() => null);
        if (cancelled || !payload) return;

        const preferredAsset = readOnboardingAssetPreference(payload.preferences || {});
        if (!preferredAsset) return;

        setSelectedAssetState(preferredAsset);
        localStorage.setItem("selectedAsset", preferredAsset);
        setAvailableAssets((current) =>
          current.includes(preferredAsset) ? current : [...current, preferredAsset]
        );
      } catch (error) {
        // Silent by design: public routes and expired sessions should not spam logs here.
      }
    }

    hydrateSelectedAssetFromPreferences();

    return () => {
      cancelled = true;
    };
  }, [pathname]);

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
