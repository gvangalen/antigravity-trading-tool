"use client";

import React from "react";
import { useAsset } from "@/app/providers/AssetProvider";
import { Coins, ChevronDown } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useActiveSetup } from "@/app/providers/SetupProvider";
import useBotData from "@/hooks/useBotData";

export default function AssetSwitcher() {
  const { selectedAsset, setSelectedAsset, availableAssets } = useAsset();
  const { activeSetup, focusedBotId } = useActiveSetup();
  const { configs: botConfigs } = useBotData();
  const [isOpen, setIsOpen] = React.useState(false);

  const focusedBot = botConfigs.find(b => b.id === focusedBotId);
  const effectiveAsset = focusedBot?.symbol || activeSetup?.symbol || selectedAsset;
  const isOverride = !!(focusedBot || activeSetup);

  return (
    <div className="px-4 mb-4 relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`w-full flex items-center gap-3 px-5 py-4 border rounded-2xl transition-all hover:border-blue-500/50 group ${
          isOverride 
            ? "bg-amber-50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-900/50" 
            : "bg-slate-50 dark:bg-slate-900/50 border-slate-100 dark:border-slate-800"
        }`}
      >
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-white shadow-lg ${
          isOverride ? "bg-amber-500 shadow-amber-500/20" : "bg-blue-600 shadow-blue-600/20"
        }`}>
          <Coins size={16} />
        </div>
        <div className="flex flex-col items-start overflow-hidden text-left">
          <span className={`text-[9px] font-black uppercase tracking-[0.2em] leading-none mb-1 ${
            isOverride ? "text-amber-600 dark:text-amber-500" : "text-secondary"
          }`}>
            {isOverride ? "Bot Override" : "Active Asset"}
          </span>
          <span className="text-sm font-black text-slate-900 dark:text-white tracking-tight">{effectiveAsset}</span>
        </div>
        {!isOverride && (
          <ChevronDown 
            size={14} 
            className={`ml-auto text-secondary transition-transform duration-300 ${isOpen ? "rotate-180" : ""}`} 
          />
        )}
      </button>

      <AnimatePresence>
        {isOpen && (
          <>
            <div 
              className="fixed inset-0 z-40" 
              onClick={() => setIsOpen(false)} 
            />
            <motion.div
              initial={{ opacity: 0, y: -10, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -10, scale: 0.95 }}
              className="absolute left-4 right-4 top-full mt-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl z-50 overflow-hidden"
            >
              <div className="p-2 grid grid-cols-1 gap-1">
                {availableAssets.map((asset) => (
                  <button
                    key={asset}
                    onClick={() => {
                      setSelectedAsset(asset);
                      setIsOpen(false);
                    }}
                    className={`flex items-center justify-between px-4 py-3 rounded-xl transition-all ${
                      selectedAsset === asset 
                        ? "bg-blue-600 text-white" 
                        : "text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800"
                    }`}
                  >
                    <span className="text-xs font-black uppercase tracking-widest">{asset}</span>
                    {selectedAsset === asset && (
                       <div className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
                    )}
                  </button>
                ))}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
