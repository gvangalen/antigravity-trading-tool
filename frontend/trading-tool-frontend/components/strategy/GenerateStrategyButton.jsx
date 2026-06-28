"use client";

import { useState } from "react";
import { useModal } from "@/components/modal/ModalProvider";
import { useTranslation } from "@/app/providers/I18nProvider";

import {
  analyzeStrategy, // POST /api/strategies/analyze/{strategy_id}
} from "@/lib/api/strategy";

/* Icons */
import { Wand2, Loader2 } from "lucide-react";

export default function AnalyzeStrategyButton({ strategyId, onSuccess }) {
  const { showSnackbar } = useModal();
  const { t } = useTranslation();
  const copy = t?.strategies?.analyzeButton || {};

  const [loading, setLoading] = useState(false);

  // ======================================================
  // 🧠 START STRATEGY ANALYSE (V1 – zoals setup)
  // ======================================================
  const handleAnalyze = async () => {
    if (!strategyId) {
      showSnackbar(copy.noSelection, "warning");
      return;
    }

    setLoading(true);

    try {
      await analyzeStrategy(strategyId);

      showSnackbar(copy.success, "success");

      // Parent laten refreshen (strategies opnieuw laden)
      if (onSuccess) onSuccess();

    } catch (err) {
      console.error("❌ AI analyse fout:", err);
      showSnackbar(copy.error, "danger");
    } finally {
      setLoading(false);
    }
  };

  // ======================================================
  // 🔘 UI
  // ======================================================
  return (
    <button
      onClick={handleAnalyze}
      disabled={loading}
      className="
        flex items-center gap-2
        px-4 py-2 text-sm font-medium
        rounded-xl shadow-md
        text-white bg-[var(--primary)]
        hover:bg-blue-700
        transition
        disabled:opacity-50 disabled:cursor-not-allowed
      "
    >
      {loading ? (
        <>
          <Loader2 className="w-4 h-4 animate-spin" />
          {copy.loading}
        </>
      ) : (
        <>
          <Wand2 className="w-4 h-4" />
          {copy.label}
        </>
      )}
    </button>
  );
}
