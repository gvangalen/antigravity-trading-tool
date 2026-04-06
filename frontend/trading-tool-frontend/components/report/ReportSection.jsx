"use client";

import React from "react";

/* ---------------------------------------------------------
   Mini utility fn
--------------------------------------------------------- */
function cn(...classes) {
  return classes.filter(Boolean).join(" ");
}

/* =====================================================
   REPORT SECTION
   - document / verhaal
   - GEEN card
   - GEEN border
===================================================== */

export default function ReportSection({
  title,
  children,
  className,
}) {
  if (!children) return null;

  return (
    <section className={cn("w-full py-6", className)}>
      {title && (
        <h3 className="mb-4 text-xs font-bold text-slate-400/80 tracking-tight">
          {title}
        </h3>
      )}

      <div className={cn(
        "text-[16px] leading-[1.7] text-slate-700",
        "animate-in fade-in duration-700"
      )}>
        {children}
      </div>
    </section>
  );
}
