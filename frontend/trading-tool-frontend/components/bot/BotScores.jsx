"use client";

import CardWrapper from "@/components/ui/CardWrapper";
import CardLoader from "@/components/ui/CardLoader";
import { BarChart3 } from "lucide-react";
import { useTranslation } from "@/app/providers/I18nProvider";

export default function BotScores({
  scores = {},
  loading = false,
}) {
  const { t } = useTranslation();
  const copy = t?.botPage?.botScores || {};
  const hasScores =
    scores && Object.keys(scores).length > 0;

  return (
    <div className="bg-card border border-[var(--color-border)] rounded-[2rem] p-6 shadow-sm transition-colors duration-300">
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 rounded-lg bg-blue-50 text-[var(--primary)]">
          <BarChart3 size={18} />
        </div>
        <div>
          <div className="text-[10px] font-black text-muted uppercase tracking-widest">{copy.eyebrow}</div>
          <div className="text-sm font-bold text-foreground tracking-tight">{copy.title}</div>
        </div>
      </div>

      {loading && (
        <CardLoader text={copy.loading} />
      )}

      {!loading && !hasScores && (
        <div className="p-8 rounded-2xl bg-[var(--color-border-subtle)] border border-[var(--color-border)] border-dashed text-center">
          <p className="text-xs font-black text-muted uppercase tracking-widest">
            {copy.empty}
          </p>
        </div>
      )}

      {!loading && hasScores && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Object.entries(scores).map(([key, value]) => {
            const score = Number(value) || 0;

            let colorClass = "text-secondary";
            let bgClass = "bg-[var(--color-border-subtle)] border-[var(--color-border)]";
            
            if (score >= 70) {
              colorClass = "text-green-600 dark:text-green-400";
              bgClass = "bg-green-50/50 dark:bg-green-900/10 border-green-100/50 dark:border-green-900/20";
            } else if (score <= 35) {
              colorClass = "text-red-600 dark:text-red-400";
              bgClass = "bg-red-50/50 dark:bg-red-900/10 border-red-100/50 dark:border-red-900/20";
            }

            return (
              <div
                key={key}
                className={`
                  rounded-2xl
                  ${bgClass}
                  border
                  p-4 flex flex-col justify-between
                `}
              >
                <div className="text-[9px] font-black text-secondary uppercase tracking-tighter mb-1">
                  {copy.scoreSuffixTemplate.replace("{key}", key)}
                </div>

                <div className={`text-2xl font-black font-mono tracking-tighter ${colorClass}`}>
                  {score.toString().padStart(2, '0')}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
