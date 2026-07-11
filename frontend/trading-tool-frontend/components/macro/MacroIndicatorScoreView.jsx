"use client";

import { useState, useEffect } from "react";
import {
  getMacroIndicatorNames,
} from "@/lib/api/macro";

import CardWrapper from "@/components/ui/CardWrapper";
import UniversalSearchDropdown from "@/components/ui/UniversalSearchDropdown";
import IndicatorScorePanel from "@/components/scoring/IndicatorScorePanel";

import { BarChart2, Plus } from "lucide-react";
import { useModal } from "@/components/modal/ModalProvider";
import { useTranslation } from "@/app/providers/I18nProvider";

/* =========================================================
   Macro Indicator Score View — Uses IndicatorScorePanel
========================================================= */
export default function MacroIndicatorScoreView({
  addMacroIndicator,
  activeMacroIndicatorNames = [],
  initialSelectedName = null,
}) {
  const { t } = useTranslation();
  const [allIndicators, setAllIndicators] = useState([]);
  const [selected, setSelected] = useState(null);

  const { showSnackbar } = useModal();
  const copy = t?.pages?.macro?.indicatorPanel || {};

  /* -------------------------------------------------------
     📡 Indicatorlijst ophalen
  ------------------------------------------------------- */
  useEffect(() => {
    async function load() {
      try {
        const list = await getMacroIndicatorNames();
        setAllIndicators(Array.isArray(list) ? list : []);
      } catch (err) {
        console.error("❌ macro indicators ophalen:", err);
        showSnackbar(copy.loadError, "danger");
      }
    }
    load();
  }, []);

  useEffect(() => {
    if (!initialSelectedName) return;
    if (!allIndicators.length) return;
    const matchingIndicator = allIndicators.find((item) => item?.name === initialSelectedName);
    if (matchingIndicator) {
      setSelected(matchingIndicator);
    }
  }, [allIndicators, initialSelectedName]);

  /* -------------------------------------------------------
     Select indicator
  ------------------------------------------------------- */
  const handleSelect = (indicator) => {
    setSelected(indicator);
  };

  /* -------------------------------------------------------
     Already added?
  ------------------------------------------------------- */
  const isAlreadyAdded =
    selected && activeMacroIndicatorNames.includes(selected.name);

  /* -------------------------------------------------------
     Add indicator
  ------------------------------------------------------- */
  const handleAdd = async () => {
    if (!selected?.name || isAlreadyAdded) return;

    const result = await addMacroIndicator(selected.name);

    if (result?.duplicate) {
      showSnackbar(
        copy.alreadyAdded.replace("{name}", selected.display_name || selected.name),
        "info"
      );
      return;
    }

    if (result?.ok) {
      showSnackbar(
        (result?.refreshed ? copy.addSuccess : copy.addSuccessPendingRefresh).replace(
          "{name}",
          selected.display_name || selected.name
        ),
        "success"
      );
      return;
    }

    if (result?.reason !== "missing_name") {
      showSnackbar(copy.addError, "danger");
    }
  };

  const displayName =
    selected?.display_name ||
    selected?.label ||
    selected?.name;

  return (
    <div className="bg-card border border-slate-200 rounded-[2.5rem] shadow-sm overflow-hidden">
      {/* TERMINAL HEADER */}
      <div className="px-8 py-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-card border border-slate-200 flex items-center justify-center text-[var(--primary)] shadow-sm">
             <BarChart2 className="w-5 h-5" />
          </div>
          <div>
            <div className="text-[10px] font-black text-secondary uppercase tracking-widest">{copy.eyebrow}</div>
            <h2 className="text-xl font-black text-foreground tracking-tight uppercase">{copy.title}</h2>
          </div>
        </div>
        <div className="text-[10px] font-black text-secondary uppercase tracking-[0.2em] bg-card px-4 py-2 rounded-xl border border-slate-200 shadow-sm">
           {copy.configBadge}
        </div>
      </div>

      <div className="p-8 space-y-8">
        {/* SEARCH BLOCK */}
        <div className="max-w-xl">
          <UniversalSearchDropdown
            label={copy.selectLabel}
            placeholder={copy.searchPlaceholder}
            items={allIndicators}
            selected={selected}
            onSelect={handleSelect}
          />
          
          {!selected && (
            <div className="mt-4 flex items-center gap-2 text-[10px] font-bold text-secondary uppercase tracking-widest italic opacity-60">
               <div className="w-1 h-1 rounded-full bg-slate-400 animate-pulse" />
               {copy.emptyHint}
            </div>
          )}
        </div>

        {/* CONFIGURATION PANEL */}
        {selected && (
          <div className="space-y-6 animate-in fade-in slide-in-from-top-2 duration-500">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="bg-[var(--primary)] text-white text-[10px] font-black px-4 py-1.5 rounded-lg uppercase tracking-widest shadow-sm">
                  {displayName}
                </span>
                <span className="text-[10px] font-black text-secondary uppercase tracking-widest">
                  {copy.tuningLabel}
                </span>
              </div>

              <button
                onClick={handleAdd}
                disabled={isAlreadyAdded}
                className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-[var(--primary)] text-white text-[10px] font-black uppercase tracking-[0.2em] hover:brightness-110 disabled:opacity-30 disabled:cursor-not-allowed transition-all shadow-lg active:scale-95"
              >
                <Plus size={14} />
                {isAlreadyAdded ? copy.active : copy.sync}
              </button>
            </div>

            <div className="border-t border-slate-100 pt-8 mt-10">
              <IndicatorScorePanel
                category="macro"
                indicator={selected.name}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
