"use client";

import React, { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { useAsset } from "@/app/providers/AssetProvider";
import { Search, X, Command } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useWatchlist } from "@/hooks/useWatchlist";
import { useActiveSetup } from "@/app/providers/SetupProvider";
import { useTranslation } from "@/app/providers/I18nProvider";

const ASSETS = [
  { symbol: "BTC", name: "Bitcoin", icon: "₿" },
  { symbol: "ETH", name: "Ethereum", icon: "Ξ" },
  { symbol: "SOL", name: "Solana", icon: "S" },
  { symbol: "ADA", name: "Cardano", icon: "A" },
  { symbol: "DOT", name: "Polkadot", icon: "P" },
];

export default function AssetSearchBar() {
  const { locale } = useTranslation();
  const router = useRouter();
  const { selectedAsset, setSelectedAsset } = useAsset();
  const { setActiveSetup, setFocusedBotId } = useActiveSetup();
  const { isInWatchlist, add, remove } = useWatchlist();
  const [query, setQuery] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef(null);

  const filteredAssets = query.trim() === "" 
    ? [] 
    : ASSETS.filter(asset => 
        asset.symbol.toLowerCase().includes(query.toLowerCase()) || 
        asset.name.toLowerCase().includes(query.toLowerCase())
      );

  // Close on outside click
  useEffect(() => {
    function handleClickOutside(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSelect = (symbol) => {
    // Smooth transition: close first, then switch
    setIsOpen(false);
    setQuery("");
    
    // Clear setup/bot focus to allow global asset to take over
    setActiveSetup(null);
    setFocusedBotId(null);
    
    // Switch asset globally
    setSelectedAsset(symbol);
    
    // 🔥 TRIGGER INITIALIZATION: Warm up data in background
    import("@/lib/api/market").then(({ initializeAsset }) => {
      initializeAsset(symbol).catch(err => console.error("❌ Init error:", err));
    });
    
    // 🚀 THE 'BOEM' FIX: Update URL and navigate
    const targetUrl = `/dashboard?symbol=${symbol}`;
    router.push(targetUrl);
  };

  const toggleWatchlist = (e, symbol) => {
    e.stopPropagation(); // Voorkom dat handleSelect wordt aangeroepen
    if (isInWatchlist(symbol)) {
      remove(symbol);
    } else {
      add(symbol);
      // 🔥 TRIGGER INITIALIZATION: Warm up data when added to watchlist
      import("@/lib/api/market").then(({ initializeAsset }) => {
        initializeAsset(symbol).catch(err => console.error("❌ Init error:", err));
      });
    }
  };

  return (
    <div className="relative w-full max-w-md mx-4" ref={containerRef}>
      <div className="relative group">
        <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-slate-400 group-focus-within:text-blue-500 transition-colors">
          <Search size={16} strokeWidth={2.5} />
        </div>
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIsOpen(true);
          }}
          onFocus={() => setIsOpen(true)}
          placeholder={locale === "nl" ? "Zoek crypto of asset... (BTC, ETH, SOL)" : "Search crypto or asset... (BTC, ETH, SOL)"}
          className="w-full bg-slate-100/50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 rounded-2xl py-2.5 pl-11 pr-12 text-sm font-bold text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500/50 transition-all"
        />
        <div className="absolute inset-y-0 right-0 pr-4 flex items-center gap-2 pointer-events-none">
          <div className="hidden sm:flex items-center gap-1 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 px-1.5 py-0.5 rounded-md text-[10px] font-black text-slate-400 uppercase tracking-tighter">
            <Command size={10} />
            K
          </div>
          {query && (
            <button 
              onClick={() => setQuery("")}
              className="pointer-events-auto text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      <AnimatePresence>
        {isOpen && filteredAssets.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 10, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.98 }}
            className="absolute top-full left-0 right-0 mt-2 bg-white dark:bg-[#0f172a] border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl z-[100] overflow-hidden"
          >
            <div className="p-2">
              <div className="px-3 py-2 text-[10px] font-black text-slate-400 dark:text-slate-500 uppercase tracking-widest border-b border-slate-50 dark:border-slate-800/50 mb-1">
                {locale === "nl" ? "Crypto-assets" : "Crypto assets"}
              </div>
              {filteredAssets.map((asset) => (
                <button
                  key={asset.symbol}
                  onClick={() => handleSelect(asset.symbol)}
                  className={`w-full flex items-center justify-between px-3 py-3 rounded-xl transition-all group ${
                    selectedAsset === asset.symbol 
                      ? "bg-blue-500 text-white" 
                      : "hover:bg-slate-50 dark:hover:bg-slate-800/50 text-slate-700 dark:text-slate-300"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-sm font-black shadow-sm ${
                      selectedAsset === asset.symbol 
                        ? "bg-white/20 text-white" 
                        : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 group-hover:bg-blue-500/10 group-hover:text-blue-500"
                    }`}>
                      {asset.icon}
                    </div>
                    <div className="flex flex-col items-start">
                      <span className="text-xs font-black uppercase tracking-tight">{asset.symbol}</span>
                      <span className={`text-[10px] font-bold ${selectedAsset === asset.symbol ? "text-white/70" : "text-slate-400"}`}>
                        {asset.name}
                      </span>
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-2">
                    <div 
                      onClick={(e) => toggleWatchlist(e, asset.symbol)}
                      className={`p-1.5 rounded-lg transition-all ${
                        isInWatchlist(asset.symbol)
                          ? "text-amber-400 hover:bg-amber-400/10"
                          : "text-slate-300 dark:text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700"
                      }`}
                    >
                       <svg 
                        viewBox="0 0 24 24" 
                        fill={isInWatchlist(asset.symbol) ? "currentColor" : "none"} 
                        stroke="currentColor" 
                        strokeWidth="2.5" 
                        className="w-4 h-4"
                       >
                        <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
                       </svg>
                    </div>

                    {selectedAsset === asset.symbol && (
                      <div className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
                    )}
                  </div>
                </button>
              ))}
            </div>
          </motion.div>
        )}
        
        {isOpen && query.trim() !== "" && filteredAssets.length === 0 && (
           <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="absolute top-full left-0 right-0 mt-2 bg-white dark:bg-[#0f172a] border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl z-[100] p-8 text-center"
           >
              <div className="flex flex-col items-center gap-3">
                <div className="w-12 h-12 rounded-full bg-slate-50 dark:bg-slate-800/50 flex items-center justify-center text-slate-300">
                  <Search size={24} />
                </div>
                <div>
                  <div className="text-sm font-black text-slate-900 dark:text-white uppercase tracking-tight">
                    {locale === "nl" ? "Geen assets gevonden" : "No assets found"}
                  </div>
                  <div className="text-xs font-bold text-slate-400 mt-1">
                    {locale === "nl" ? "Probeer een ander symbool zoals BTC of ETH" : "Try another symbol such as BTC or ETH"}
                  </div>
                </div>
              </div>
           </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
