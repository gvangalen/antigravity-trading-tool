"use client";

import { Brain } from "lucide-react";
import { useScoresData } from "@/hooks/useScoresData";

import CardWrapper from "@/components/ui/CardWrapper";
import CardLoader from "@/components/ui/CardLoader";     // ✅ Nieuwe loader
import AIInsightBlock from "@/components/ui/AIInsightBlock";

export default function MasterScoreCard() {
  const { master, loading, error } = useScoresData();

  const getScoreColor = (score) => {
    if (score >= 70) return "text-green-600 dark:text-green-300";
    if (score <= 40) return "text-red-600 dark:text-red-300";
    return "text-yellow-500 dark:text-yellow-300";
  };

  const outlook = master?.outlook || "";

  return (
    <CardWrapper
      title="AI Master Score"
      icon={<Brain className="w-4 h-4 text-[var(--primary)]" />}
    >
      <div className="flex flex-col gap-4 min-h-[220px]">

        {/* 🔄 UNIFORME LOADER */}
        {loading && <CardLoader text="Master score laden…" />}

        {/* ❌ ERROR */}
        {!loading && (error || !master) && (
          <p className="text-red-500 text-center text-sm">
            ❌ Fout bij laden van Master Score
          </p>
        )}

        {/* ✅ CONTENT */}
        {!loading && master && (
          <>
            {/* SCORE NUMBER */}
            <p className={`text-4xl font-bold ${getScoreColor(master.score)}`}>
              {master.score.toFixed(1)}
            </p>

            {/* DETAILS */}
            <div className="space-y-[3px] text-sm text-[var(--text-dark)]">
              <p><strong>Trend:</strong> {master.trend}</p>
              <p><strong>Bias:</strong> {master.bias}</p>
              <p><strong>Risico:</strong> {master.risk}</p>
            </div>

            {/* AI INSIGHT BLOCK */}
            {outlook && (
              <AIInsightBlock text={outlook} variant="dashboard" />
            )}
          </>
        )}
      </div>
    </CardWrapper>
  );
}
