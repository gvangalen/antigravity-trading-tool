"use client";

import { useTranslation } from "@/app/providers/I18nProvider";
import { Settings } from "lucide-react";
import { useModal } from "@/components/modal/ModalProvider";
import IndicatorScorePanel from "./IndicatorScorePanel";

export default function IndicatorScoreButton({ indicator, category, assetSymbol }) {
  const { openModal } = useModal();
  const { t } = useTranslation();
  const copy = t?.legacyComponents?.indicatorScore || {};

  const openEditor = () => {
    openModal({
      title: `${copy.buttonTitle} — ${indicator}`,
      content: (
        <IndicatorScorePanel
          indicator={indicator}
          category={category}
          assetSymbol={assetSymbol}
        />
      ),
    });
  };

  return (
    <button
      onClick={openEditor}
      className="
        inline-flex items-center justify-center
        p-1.5
        rounded-[var(--radius-sm)]
        text-[var(--icon-muted)]
        hover:text-[var(--icon-primary)]
        hover:bg-[var(--surface-2)]
        transition
      "
      title={copy.buttonTitle}
    >
      <Settings size={16} />
    </button>
  );
}
