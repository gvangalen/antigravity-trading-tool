"use client";

import React, { createContext, useContext, useState, useEffect } from "react";

type AssetContextType = {
  selectedAsset: string;
  setSelectedAsset: (asset: string) => void;
  availableAssets: string[];
  addAsset: (asset: string) => void;
};

const AssetContext = createContext<AssetContextType | null>(null);

export function AssetProvider({ children }: { children: React.ReactNode }) {
  const [selectedAsset, setSelectedAssetState] = useState<string>("BTC");
  const [availableAssets, setAvailableAssets] = useState<string[]>(["BTC", "ETH", "SOL", "ADA", "DOT"]);

  // Load from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem("selectedAsset");
    if (saved) {
      setSelectedAssetState(saved);
    }
  }, []);

  const setSelectedAsset = (asset: string) => {
    setSelectedAssetState(asset);
    localStorage.setItem("selectedAsset", asset);
  };

  const addAsset = (asset: string) => {
    const up = asset.toUpperCase();
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
