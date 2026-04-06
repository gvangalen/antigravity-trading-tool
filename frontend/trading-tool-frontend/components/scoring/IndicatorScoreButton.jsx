"use client";

import { Settings } from "lucide-react";
import { useModal } from "@/components/modal/ModalProvider";
import IndicatorScorePanel from "./IndicatorScorePanel";

export default function IndicatorScoreButton({ indicator, category }) {
  const { openModal } = useModal();

  const openEditor = () => {
    openModal({
      title: `Score instellingen — ${indicator}`,
      content: (
        <IndicatorScorePanel
          indicator={indicator}
          category={category}
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
      title="Score instellingen"
    >
      <Settings size={16} />
    </button>
  );
}
