"use client";

import { useAsset } from "@/app/providers/AssetProvider";
import { useActiveSetup } from "@/app/providers/SetupProvider";
import useBotData from "@/hooks/useBotData";
import { useSearchParams } from "next/navigation";

/**
 * 🎯 Hook to resolve the active asset symbol with priority:
 * 1. Focused Bot
 * 2. Active Setup
 * 3. URL Query Param (?symbol=...)
 * 4. Global Asset Switcher
 */
export function useCurrentAsset() {
  const searchParams = useSearchParams();
  
  // Try searchParams first, then window.location as fallback
  let urlSymbol = searchParams?.get("symbol")?.toUpperCase();
  if (!urlSymbol && typeof window !== 'undefined') {
    const params = new URLSearchParams(window.location.search);
    urlSymbol = params.get("symbol")?.toUpperCase();
  }
  
  const { selectedAsset } = useAsset();
  const { activeSetup, focusedBotId } = useActiveSetup();
  const { configs: botConfigs } = useBotData();

  const focusedBot = botConfigs.find(b => b.id === focusedBotId);
  const activeSymbol = focusedBot?.symbol || activeSetup?.symbol || urlSymbol || selectedAsset;
  
  const isOverride = !!(focusedBot || activeSetup || urlSymbol);

  return {
    symbol: activeSymbol,
    isOverride,
    source: focusedBot ? "bot" : activeSetup ? "setup" : "global"
  };
}
