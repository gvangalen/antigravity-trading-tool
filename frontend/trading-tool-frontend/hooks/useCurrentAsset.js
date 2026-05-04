"use client";

import { useAsset } from "@/app/providers/AssetProvider";
import { useActiveSetup } from "@/app/providers/SetupProvider";
import useBotData from "@/hooks/useBotData";

/**
 * 🎯 Hook to resolve the active asset symbol with priority:
 * 1. Focused Bot
 * 2. Active Setup
 * 3. Global Asset Switcher
 */
export function useCurrentAsset() {
  const { selectedAsset } = useAsset();
  const { activeSetup, focusedBotId } = useActiveSetup();
  const { configs: botConfigs } = useBotData();

  const focusedBot = botConfigs.find(b => b.id === focusedBotId);
  const activeSymbol = focusedBot?.symbol || activeSetup?.symbol || selectedAsset;
  
  const isOverride = !!(focusedBot || activeSetup);

  return {
    symbol: activeSymbol,
    isOverride,
    source: focusedBot ? "bot" : activeSetup ? "setup" : "global"
  };
}
