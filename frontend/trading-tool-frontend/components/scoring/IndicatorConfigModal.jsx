"use client";

import { useCallback, useMemo, useState } from "react";
import { X, SlidersHorizontal } from "lucide-react";

import IndicatorScorePanel from "@/components/scoring/IndicatorScorePanel";
import { useModal } from "@/components/modal/ModalProvider";
import { saveCustomRules, updateIndicatorSettings } from "@/lib/api/indicatorConfig";

function getCategoryLabel(category) {
  if (category === "technical") return "Technical";
  if (category === "macro") return "Macro";
  if (category === "market") return "Market";
  return "Indicator";
}

export default function IndicatorConfigModal({
  isOpen,
  category,
  indicator,
  assetSymbol,
  mode = "add",
  onClose,
  onSubmitAction,
  onCompleted,
}) {
  const { showSnackbar } = useModal();
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);

  const categoryLabel = useMemo(() => getCategoryLabel(category), [category]);
  const indicatorLabel = useMemo(() => String(indicator || "").toUpperCase(), [indicator]);
  const actionLabel = mode === "edit" ? "Opslaan" : `Toevoegen aan ${categoryLabel}`;

  const handleDraftChange = useCallback((nextDraft) => {
    setDraft(nextDraft);
  }, []);

  const handleConfirm = useCallback(async () => {
    if (!indicator || !category || !draft || saving) return;

    setSaving(true);

    try {
      if (draft.score_mode === "custom") {
        await saveCustomRules({
          category,
          indicator,
          rules: Array.isArray(draft.rules) ? draft.rules : [],
        });
      }

      await updateIndicatorSettings({
        category,
        indicator,
        score_mode: draft.score_mode || "standard",
        weight: typeof draft.weight === "number" ? draft.weight : 1,
      });

      await onSubmitAction?.({
        indicator,
        category,
        assetSymbol,
        draft,
      });

      showSnackbar(
        mode === "edit"
          ? `${indicatorLabel} opgeslagen voor ${assetSymbol} ${categoryLabel}.`
          : `${indicatorLabel} toegevoegd aan ${assetSymbol} ${categoryLabel}.`,
        "success"
      );

      onCompleted?.({
        indicator,
        category,
        assetSymbol,
        draft,
      });
      onClose?.();
    } catch (error) {
      console.error("Failed to confirm indicator config modal:", error);
      showSnackbar(`Actie voor ${indicatorLabel} is mislukt.`, "danger");
    } finally {
      setSaving(false);
    }
  }, [
    assetSymbol,
    category,
    categoryLabel,
    draft,
    indicator,
    indicatorLabel,
    mode,
    onClose,
    onCompleted,
    onSubmitAction,
    saving,
    showSnackbar,
  ]);

  if (!isOpen || !indicator || !category) return null;

  return (
    <div className="fixed inset-0 z-[220] overflow-y-auto bg-slate-950/55 px-4 py-6 backdrop-blur-sm sm:py-8">
      <div className="flex min-h-full items-start justify-center sm:items-center">
        <div className="relative flex max-h-[calc(100vh-3rem)] w-full max-w-6xl flex-col overflow-hidden rounded-[32px] border border-slate-200 bg-white shadow-[0_35px_120px_-35px_rgba(15,23,42,0.55)] sm:max-h-[calc(100vh-4rem)]">
        <button
          type="button"
          onClick={onClose}
          className="absolute right-5 top-5 z-10 rounded-2xl p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
        >
          <X size={20} />
        </button>

        <div className="border-b border-slate-100 px-8 py-7">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.28em] text-blue-600">
                Indicator Configuration
              </div>
              <h2 className="mt-2 text-3xl font-black tracking-tight text-slate-950">
                {indicatorLabel}
              </h2>
              <p className="mt-2 text-sm font-medium text-slate-500">
                Stel eerst de logica voor deze {categoryLabel.toLowerCase()}-indicator in en voeg hem daarna toe aan {assetSymbol}.
              </p>
            </div>

            <div className="inline-flex items-center gap-2 self-start rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.22em] text-blue-600">
              <SlidersHorizontal size={12} />
              {categoryLabel} Configuration
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-8 py-8">
          <IndicatorScorePanel
            indicator={indicator}
            category={category}
            deferred
            onDraftChange={handleDraftChange}
          />
        </div>

        <div className="flex items-center justify-end gap-4 border-t border-slate-100 px-8 py-6">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="rounded-2xl border border-slate-200 px-5 py-3 text-[11px] font-black uppercase tracking-[0.2em] text-slate-500 transition hover:border-slate-300 hover:text-slate-700 disabled:opacity-50"
          >
            Annuleren
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={saving || !draft}
            className="inline-flex min-w-[220px] items-center justify-center gap-2 rounded-2xl bg-blue-600 px-5 py-3 text-[11px] font-black uppercase tracking-[0.22em] text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? "Bezig..." : actionLabel}
          </button>
        </div>
      </div>
      </div>
    </div>
  );
}
