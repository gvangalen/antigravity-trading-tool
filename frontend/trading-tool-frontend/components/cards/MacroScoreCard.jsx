'use client';

import CardWrapper from "@/components/ui/CardWrapper";
import { Gauge } from "lucide-react";

export default function TechnicalScoreCard({ score = 14.3 }) {
  // Score kleur
  const color =
    score >= 70
      ? "text-green-600"
      : score >= 40
      ? "text-yellow-500"
      : "text-red-500";

  const bgColor =
    score >= 70
      ? "bg-green-50 dark:bg-green-900 border-green-300 dark:border-green-700"
      : score >= 40
      ? "bg-yellow-50 dark:bg-yellow-900 border-yellow-300 dark:border-yellow-700"
      : "bg-red-50 dark:bg-red-900 border-red-300 dark:border-red-700";

  return (
    <CardWrapper>
      <div className={`rounded-xl p-4 border ${bgColor}`}>
        {/* Header */}
        <div className="flex items-center gap-2 mb-2 text-[var(--text-dark)]">
          <Gauge className="w-4 h-4" />
          <span className="text-sm font-semibold">Technische Score</span>
        </div>

        {/* Score */}
        <p className={`text-3xl font-bold ${color}`}>
          {score}
        </p>

        <p className="text-xs mt-1 text-[var(--text-light)]">Gecombineerde technische analyse score</p>
      </div>
    </CardWrapper>
  );
}
