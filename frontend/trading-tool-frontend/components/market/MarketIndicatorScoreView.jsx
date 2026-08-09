"use client";

import { useState, useEffect } from "react";
import UniversalSearchDropdown from "@/components/ui/UniversalSearchDropdown";
import IndicatorScorePanel from "@/components/scoring/IndicatorScorePanel";
import { Coins, Plus } from "lucide-react";
import { useModal } from "@/components/modal/ModalProvider";
import { useTranslation } from "@/app/providers/I18nProvider";

const INDICATOR_LABEL_KEYS = {
  price: "price",
  volume: "volumeRelative",
  market_volume: "volumeRelative",
  volume_change: "volumeChange",
  volume_change_24h: "volumeChange",
  change_24h: "change24h",
  change_7d: "change7d",
};

export default function MarketIndicatorScoreView({
  availableIndicators = [],
  selectedIndicator,
  selectIndicator,
  addMarketIndicator,
  activeIndicators = [],
  preferences = null,
  preferencesLoading = false,
  syncing = false,
  assetClass = null,
  assetSymbol = "BTC",
  applyRecommendedPreset = null,
}) {
  const { showSnackbar } = useModal();
  const { t } = useTranslation();
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
      showSnackbar(panelCopy.addSuccess, "success");
    } catch {
      showSnackbar(panelCopy.addError, "danger");
    }
  };

  /* --------------------------------------------------
     Display name helper
  -------------------------------------------------- */
  const panelCopy = t?.pages?.market?.indicatorPanel || {};
  const indicatorLabels = t?.legacyComponents?.indicatorScore?.indicatorLabels || {};
  const copy = {
    eyebrow: panelCopy.eyebrow,
    title: panelCopy.title,
    configBadge: panelCopy.configBadge || panelCopy.configId,
    activeScopeLabel: panelCopy.activeScopeLabel,
    selectLabel: panelCopy.selectLabel,
    searchPlaceholder: panelCopy.searchPlaceholder,
    emptyHint: panelCopy.emptyHint,
    tuningLabel: panelCopy.tuningLabel,
    active: t?.ui?.terminalGrid?.active,
    attach: panelCopy.attach,
  };

  const getLocalizedIndicatorLabel = (item) => {
    const labelKey = INDICATOR_LABEL_KEYS[item?.name];
    return (labelKey && indicatorLabels?.[labelKey]) || item?.display_name || item?.label || item?.name;
  };

  const displayName = indicator ? getLocalizedIndicatorLabel(indicator) : null;
  const effectiveScope = preferences?.scope || "default";
  const configuredIndicators = Array.isArray(preferences?.indicators) ? preferences.indicators : [];
  const scopeLabel =
    effectiveScope === "symbol_override"
      ? `Asset override · ${assetSymbol}`
      : effectiveScope === "asset_class_override"
      ? `Asset class default · ${assetClass || "unknown"}`
      : "Global default";

  return (
    <div className="bg-card border border-slate-200 rounded-[2.5rem] shadow-sm overflow-hidden">
      {/* TERMINAL HEADER */}
      <div className="px-8 py-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-card border border-slate-200 flex items-center justify-center text-[var(--primary)] shadow-sm">
             <Coins size={20} className="w-5 h-5" />
          </div>
          <div>
            <div className="text-[10px] font-black text-secondary uppercase tracking-widest leading-none">
              {copy.eyebrow}
            </div>
            <h2 className="text-xl font-black text-foreground tracking-tight uppercase leading-none mt-1">
              {copy.title}
            </h2>
          </div>
        </div>
        <div className="text-[10px] font-black text-secondary uppercase tracking-[0.2em] bg-card px-4 py-2 rounded-xl border border-slate-200 shadow-sm">
          {copy.configBadge}
        </div>
      </div>

      <div className="p-8 space-y-8">
        <div className="rounded-[2rem] border border-slate-200 bg-slate-50/80 p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-500">
                {copy.activeScopeLabel || "Active preference scope"}
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

        {/* SEARCH BLOCK */}
        <div className="max-w-xl">
          <UniversalSearchDropdown
            label={copy.selectLabel}
            placeholder={copy.searchPlaceholder}
            items={availableIndicators}
            selected={indicator}
            onSelect={handleSelect}
            getItemLabel={getLocalizedIndicatorLabel}
            hideSecondaryLabel
          />
          
          {!indicator && (
            <div className="mt-4 flex items-center gap-2 text-[10px] font-bold text-secondary uppercase tracking-widest italic opacity-60">
               <div className="w-1 h-1 rounded-full bg-slate-400 animate-pulse" />
               {copy.emptyHint}
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
                  {copy.tuningLabel}
                </span>
              </div>

              <button
                onClick={handleAdd}
                disabled={isAdded}
                className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-[var(--primary)] text-white text-[10px] font-black uppercase tracking-[0.2em] hover:brightness-110 disabled:opacity-30 disabled:cursor-not-allowed transition-all shadow-lg active:scale-95"
              >
                <Plus size={14} />
                {isAdded ? copy.active : copy.attach}
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
