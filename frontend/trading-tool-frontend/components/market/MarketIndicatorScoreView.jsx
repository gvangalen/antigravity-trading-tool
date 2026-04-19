"use client";

import { useState, useEffect } from "react";
import CardWrapper from "@/components/ui/CardWrapper";
import UniversalSearchDropdown from "@/components/ui/UniversalSearchDropdown";
import IndicatorScorePanel from "@/components/scoring/IndicatorScorePanel";
import { Coins, Plus } from "lucide-react";
import { useModal } from "@/components/modal/ModalProvider";

export default function MarketIndicatorScoreView({
  availableIndicators = [],
  selectedIndicator,
  selectIndicator,
  addMarketIndicator,
  activeIndicators = [],
}) {
  const { showSnackbar } = useModal();
  const [indicator, setIndicator] = useState(selectedIndicator || null);

  /* --------------------------------------------------
     Sync met parent state
  -------------------------------------------------- */
  useEffect(() => {
    if (selectedIndicator) {
      setIndicator(selectedIndicator);
    }
  }, [selectedIndicator]);

  /* --------------------------------------------------
     Select indicator
  -------------------------------------------------- */
  const handleSelect = (item) => {
    setIndicator(item);
    selectIndicator?.(item);
  };

  /* --------------------------------------------------
     Already added?
  -------------------------------------------------- */
  const isAdded =
    indicator && activeIndicators.includes(indicator.name);

  /* --------------------------------------------------
     Add indicator
  -------------------------------------------------- */
  const handleAdd = async () => {
    if (!indicator || isAdded) return;

    try {
      await addMarketIndicator(indicator.name);
      showSnackbar("Indicator toegevoegd", "success");
    } catch {
      showSnackbar("Toevoegen mislukt", "danger");
    }
  };

  /* --------------------------------------------------
     Display name helper
  -------------------------------------------------- */
  const displayName =
    indicator?.display_name ||
    indicator?.label ||
    indicator?.name;

  return (
    <div className="bg-card border border-slate-200 rounded-[2.5rem] shadow-sm overflow-hidden">
      {/* TERMINAL HEADER */}
      <div className="px-8 py-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-card border border-slate-200 flex items-center justify-center text-[var(--primary)] shadow-sm">
             <Coins size={20} className="w-5 h-5" />
          </div>
          <div>
            <div className="text-[10px] font-black text-secondary uppercase tracking-widest leading-none">Logic Manifest</div>
            <h2 className="text-xl font-black text-foreground tracking-tight uppercase leading-none mt-1">Market Indicator Configuration</h2>
          </div>
        </div>
        <div className="text-[10px] font-black text-secondary uppercase tracking-[0.2em] bg-card px-4 py-2 rounded-xl border border-slate-200 shadow-sm">
           SYSTEM_ID: MARKET_CFG_V2.0
        </div>
      </div>

      <div className="p-8 space-y-8">
        {/* SEARCH BLOCK */}
        <div className="max-w-xl">
          <UniversalSearchDropdown
            label="SELECT_MARKET_NODE"
            placeholder="Search indicators (Price, Volume, Change 24h)..."
            items={availableIndicators}
            selected={indicator}
            onSelect={handleSelect}
          />
          
          {!indicator && (
            <div className="mt-4 flex items-center gap-2 text-[10px] font-bold text-secondary uppercase tracking-widest italic opacity-60">
               <div className="w-1 h-1 rounded-full bg-slate-400 animate-pulse" />
               Awaiting node selection for signal configuration...
            </div>
          )}
        </div>

        {/* CONFIGURATION PANEL */}
        {indicator && (
          <div className="space-y-6 animate-in fade-in slide-in-from-top-2 duration-500">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="bg-[var(--primary)] text-white text-[10px] font-black px-4 py-1.5 rounded-lg uppercase tracking-widest shadow-sm">
                  {displayName}
                </span>
                <span className="text-[10px] font-black text-secondary uppercase tracking-widest leading-none">
                  Live_Parameter_Tuning
                </span>
              </div>

              <button
                onClick={handleAdd}
                disabled={isAdded}
                className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-[var(--primary)] text-white text-[10px] font-black uppercase tracking-[0.2em] hover:brightness-110 disabled:opacity-30 disabled:cursor-not-allowed transition-all shadow-lg active:scale-95"
              >
                <Plus size={14} />
                {isAdded ? "NODE_ACTIVE" : "SYNC_TO_MARKET_TERMINAL"}
              </button>
            </div>

            <div className="border-t border-slate-100 pt-8 mt-10">
              <IndicatorScorePanel
                category="market"
                indicator={indicator.name}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
