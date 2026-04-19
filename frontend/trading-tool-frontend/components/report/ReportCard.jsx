"use client";

import React from "react";

/* ---------------------------------------------------------
   Mini utility fn
--------------------------------------------------------- */
function cn(...classes) {
  return classes.filter(Boolean).join(" ");
}

/* ---------------------------------------------------------
   Content formatter — ALLEEN voor data
--------------------------------------------------------- */
function formatContent(value) {
  if (value === null || value === undefined) return "–";

  if (typeof value === "string") return value;

  if (Array.isArray(value)) {
    return value
      .map((item) =>
        typeof item === "string" ? `- ${item}` : `- ${JSON.stringify(item, null, 2)}`
      )
      .join("\n");
  }

  if (typeof value === "object") {
    if (value.text) return value.text;
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }

  return String(value);
}

/* =====================================================
   REPORT CARD — GRID SAFE (breedte/flow gefixt)
===================================================== */

export default function ReportCard({
  title,
  icon = null,

  /** DATA-modus */
  content,
  pre = false,

  /** UI-modus */
  children,

  /** layout */
  full = false,

  /**
   * Standalone layout (bv. single card boven/onder report):
   * - constrain: max width + centreren
   * - default: grid bepaalt breedte (w-full)
   */
  constrain = false,

  /**
   * Optional: maak content scrollbaar als het te lang wordt
   * (handig bij 10+ indicators)
   */
  scroll = false,
  maxHeight = "320px",
}) {
  const isDataMode = content !== undefined;

  return (
    <section
      className={cn(
        "bg-slate-50/50 border border-slate-100 rounded-[1.25rem] p-6 transition-all duration-500",
        "w-full min-w-0 h-full",
        constrain && "max-w-[1100px] mx-auto",
        full && "md:col-span-2",
        scroll && "flex flex-col"
      )}
    >
      {/* Header */}
      {(title || icon) && (
        <header className="mb-5 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
             {icon && <div className="text-slate-400/80">{icon}</div>}
             {title && (
               <h2 className="text-[11px] font-bold text-muted tracking-tight">
                 {title}
               </h2>
             )}
          </div>
        </header>
      )}

      {/* Content */}
      <div
        className={cn(
          "text-[15px] leading-relaxed text-slate-700",
          scroll && "overflow-auto"
        )}
        style={scroll ? { maxHeight } : undefined}
      >
        {isDataMode ? (
          pre ? (
            <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-dim bg-[var(--color-border-subtle)] p-4 rounded-xl border border-slate-100">
              {formatContent(content)}
            </pre>
          ) : (
            <div className="font-medium">{formatContent(content)}</div>
          )
        ) : (
          children
        )}
      </div>
    </section>
  );
}
