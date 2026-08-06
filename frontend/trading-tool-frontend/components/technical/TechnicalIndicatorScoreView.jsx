"use client";

import { useState, useEffect } from "react";
import {
  getIndicatorNames as getTechnicalIndicatorNames,
} from "@/lib/api/technical";

import UniversalSearchDropdown from "@/components/ui/UniversalSearchDropdown";
import IndicatorScorePanel from "@/components/scoring/IndicatorScorePanel";

import { BarChart2, Plus, Terminal } from "lucide-react";
import { useModal } from "@/components/modal/ModalProvider";
import { useTranslation } from "@/app/providers/I18nProvider";

/**
 * 🛠️ TechnicalIndicatorScoreView — V2 PRO
 * Redesigned as a technical configuration terminal.
 */
export default function TechnicalIndicatorScoreView({
  addTechnicalIndicator,
  activeTechnicalIndicatorNames = [],
  preferences = null,
  preferencesLoading = false,
  syncing = false,
  assetClass = null,
  assetSymbol = "BTC",
  applyRecommendedPreset = null,
}) {
  const { t } = useTranslation();
  const copy = t?.pages?.technical?.indicatorPanel || {};
  const [allIndicators, setAllIndicators] = useState([]);
  const [selected, setSelected] = useState(null);

  const { showSnackbar } = useModal();

  useEffect(() => {
    async function load() {
      try {
        const list = await getTechnicalIndicatorNames();
        setAllIndicators(Array.isArray(list) ? list : []);
      } catch (err) {
        console.error("❌ technical indicators ophalen", err);
        showSnackbar(copy.loadError, "danger");
      }
    }
    load();
  }, []);

  const handleSelect = (indicator) => {
    setSelected(indicator);
  };

  const isAlreadyAdded =
    selected &&
    activeTechnicalIndicatorNames.includes(selected.name);

  const handleAdd = async () => {
    if (!selected?.name || isAlreadyAdded) return;

    try {
      await addTechnicalIndicator(selected.name);
      showSnackbar(
        copy.addSuccess.replace("{name}", selected.display_name || selected.name),
        "success"
      );
    } catch (err) {
      // ✅ Correcte status veld voor onze custom fetchAuth
      const status = err.status || err.response?.status;
      
      if (status === 409) {
        showSnackbar(
          copy.alreadyAddedSuccess.replace("{name}", selected.display_name || selected.name),
          "success"
        );
      } else {
        console.error("❌ Toevoegen mislukt", err);
        showSnackbar(copy.addError, "danger");
      }
    }
  };

  const displayName =
    selected?.display_name ||
    selected?.label ||
    selected?.name;

  const effectiveScope = preferences?.scope || "default";
  const configuredIndicators = Array.isArray(preferences?.indicators) ? preferences.indicators : [];
  const scopeLabel =
    effectiveScope === "symbol_override"
      ? `Asset override · ${assetSymbol}`
      : effectiveScope === "asset_class_override"
      ? `Asset class default · ${assetClass || "unknown"}`
      : "Global default";

  return (
    <div className="bg-card border border-slate-200 rounded-[2.5rem] p-8 shadow-sm">
      {/* 🕋 MODULE HEADER */}
      <div className="flex items-center justify-between mb-8 pb-6 border-b border-slate-100">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[var(--color-border-subtle)] border border-slate-100 flex items-center justify-center text-slate-400">
            <Terminal size={20} />
          </div>
          <div>
            <div className="text-[10px] font-black text-secondary uppercase tracking-widest">{copy.eyebrow}</div>
            <h2 className="text-xl font-black text-foreground tracking-tight uppercase">{copy.title}</h2>
          </div>
        </div>
        <div className="text-[9px] font-black text-blue-500 bg-blue-50 px-3 py-1 rounded-lg uppercase tracking-widest border border-blue-100">
           {copy.logicVersion}
        </div>
      </div>

      <div className="space-y-8">
        <div className="rounded-[2rem] border border-slate-200 bg-slate-50/80 p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-500">
                Active preference scope
              </div>
              <div className="mt-2 text-sm font-black uppercase tracking-[0.12em] text-slate-900">
                {preferencesLoading ? "Loading..." : scopeLabel}
              </div>
              <div className="mt-2 text-sm text-slate-500">
                {configuredIndicators.length > 0
                  ? `${configuredIndicators.length} indicator${configuredIndicators.length === 1 ? "" : "s"} configured for this context.`
                  : "No configured indicators yet for this context."}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {applyRecommendedPreset ? (
                <>
                  <button
                    type="button"
                    onClick={() => applyRecommendedPreset("asset_class")}
                    disabled={preferencesLoading || syncing}
                    className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-[10px] font-black uppercase tracking-[0.18em] text-slate-700 transition hover:border-blue-300 hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {syncing ? "Syncing..." : `Use ${assetClass || "asset"} defaults`}
                  </button>
                  <button
                    type="button"
                    onClick={() => applyRecommendedPreset("symbol")}
                    disabled={preferencesLoading || syncing}
                    className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-[10px] font-black uppercase tracking-[0.18em] text-slate-700 transition hover:border-blue-300 hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {syncing ? "Syncing..." : `Make ${assetSymbol} specific`}
                  </button>
                </>
              ) : null}
            </div>
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            {configuredIndicators.map((item) => (
              <span
                key={`${item.indicator}-${item.priority ?? 100}`}
                className="rounded-full border border-slate-200 bg-white px-3 py-1 text-[10px] font-black uppercase tracking-[0.16em] text-slate-600"
              >
                {item.indicator}
              </span>
            ))}
          </div>
        </div>

        {/* 🔍 SEARCH NODES */}
        <div className="space-y-2">
          <label className="text-[10px] font-black text-secondary uppercase tracking-[0.2em] pl-1">
             {copy.searchLabel}
          </label>
          <UniversalSearchDropdown
            items={allIndicators}
            selected={selected}
            onSelect={handleSelect}
            placeholder={copy.searchPlaceholder}
          />
        </div>

        {/* EMPTY_CONTEXT */}
        {!selected && (
          <div className="py-12 border-2 border-dashed border-slate-100 rounded-[2rem] flex flex-col items-center justify-center text-center">
             <BarChart2 className="w-10 h-10 text-slate-100 mb-3" />
             <p className="text-[10px] font-black text-slate-300 uppercase tracking-widest">
                {copy.emptyHint}
             </p>
          </div>
        )}

        {/* ACTIVE_NODE_DISPLAY */}
        {selected && (
          <div className="animate-in fade-in slide-in-from-bottom-2 duration-500">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                 <div className="w-2 h-2 rounded-full bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.5)]" />
                 <span className="text-sm font-black text-foreground uppercase tracking-tight">{copy.editingNode}: {displayName}</span>
              </div>
              
              <button
                onClick={handleAdd}
                disabled={isAlreadyAdded}
                className="flex items-center gap-2 px-6 py-2 rounded-xl bg-[var(--primary)] text-white text-[10px] font-black uppercase tracking-widest hover:scale-105 active:scale-95 disabled:opacity-30 disabled:hover:scale-100 transition-all shadow-lg shadow-blue-500/20"
              >
                <Plus size={14} strokeWidth={3} />
                {isAlreadyAdded ? copy.alreadySynced : copy.syncToTerminal}
              </button>
            </div>

            <div className="min-h-[300px]">
              <IndicatorScorePanel
                category="technical"
                indicator={selected.name}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
