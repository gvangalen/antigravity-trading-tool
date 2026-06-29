'use client';

import { useTranslation } from "@/app/providers/I18nProvider";
import { Star } from "lucide-react";
import CardWrapper from "@/components/ui/CardWrapper";

export default function SetupScoreCard() {
  const { t } = useTranslation();
  const copy = t?.legacyComponents?.setupScoreCard || {};

  return (
    <CardWrapper>
      <div
        className="
          p-5 rounded-xl
          bg-[var(--card-bg)]
          border border-[var(--card-border)]
          shadow-sm
          transition-all
          hover:shadow-md hover:-translate-y-[1px]
        "
      >
        {/* Header */}
        <div className="flex items-center gap-2 mb-2">
          <div className="p-2 rounded-lg bg-[var(--bg-soft)] shadow-sm">
            <Star className="w-4 h-4 text-yellow-500" />
          </div>

          <h2 className="text-sm font-semibold text-[var(--text-dark)]">
            {copy.title}
          </h2>
        </div>

        {/* Setup Info */}
        <p className="text-sm text-[var(--text-dark)] leading-relaxed">
          {copy.setupName}{" "}
          <span className="font-semibold text-green-600">
            {copy.scoreLabel}
          </span>
        </p>

      </div>
    </CardWrapper>
  );
}
