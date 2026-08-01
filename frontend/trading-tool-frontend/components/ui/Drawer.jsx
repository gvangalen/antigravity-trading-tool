"use client";

import React, { useId } from "react";
import { X } from "lucide-react";
import OverlayShell from "@/components/ui/OverlayShell";

/**
 * Drawer component for professional "Pro" slide-overs.
 */
export default function Drawer({ 
  isOpen, 
  onClose, 
  title, 
  subtitle,
  children,
  width = "max-w-xl",
  description,
  closeOnBackdrop = true,
  closeOnEscape = true,
  isCloseBlocked = false,
}) {
  const titleId = useId();
  const descriptionId = useId();

  return (
    <OverlayShell
      isOpen={isOpen}
      onClose={onClose}
      variant="drawer"
      labelledBy={titleId}
      describedBy={description || subtitle ? descriptionId : undefined}
      closeOnBackdrop={closeOnBackdrop}
      closeOnEscape={closeOnEscape}
      isCloseBlocked={isCloseBlocked}
      rootClassName="z-[100]"
      backdropClassName="bg-slate-900/40 backdrop-blur-sm transition-opacity"
      positionClassName="pointer-events-none fixed inset-y-0 right-0 flex max-w-full pl-10"
      panelClassName={`pointer-events-auto w-screen ${width} animate-drawer-slide`}
    >
      <div className="flex h-full flex-col overflow-y-auto bg-card shadow-2xl">
        <div className="border-b border-slate-100 bg-[var(--color-border-subtle)] px-6 py-8">
          <div className="flex items-start justify-between gap-4">
            <div>
              {subtitle ? (
                <div
                  id={descriptionId}
                  className="mb-1 text-[10px] font-black uppercase tracking-[0.3em] text-[var(--primary)]"
                >
                  {subtitle}
                </div>
              ) : null}
              <h2 id={titleId} className="text-2xl font-black tracking-tight text-foreground">
                {title}
              </h2>
              {description ? (
                <p className="mt-2 max-w-2xl text-sm font-medium leading-relaxed text-slate-500">
                  {description}
                </p>
              ) : null}
            </div>
            <button
              type="button"
              aria-label="Sluiten"
              data-overlay-close="true"
              className="rounded-xl p-2 text-secondary transition-all hover:bg-white hover:text-slate-500 hover:shadow-sm"
              onClick={() => onClose?.("button")}
            >
              <X size={20} aria-hidden="true" />
            </button>
          </div>
        </div>
        <div className="relative flex-1 px-6 py-8">
          {children}
        </div>
      </div>
    </OverlayShell>
  );
}
