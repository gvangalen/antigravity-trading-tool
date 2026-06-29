"use client";

import React from "react";
import { Brain } from "lucide-react";
import { useTranslation } from "@/app/providers/I18nProvider";

export default function AIFloatingButton({ isOpen, onClick }) {
  const { t } = useTranslation();
  const assistantBuild = "mc-shell-v2";
  return (
    <button
      onClick={onClick}
      data-assistant-build={assistantBuild}
      aria-label={t?.ui?.aiFloatingButton?.open}
      className={`fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-2xl border transition-all duration-300 group ${
        isOpen 
          ? "bg-slate-900 border-slate-700 opacity-95 ring-2 ring-blue-500/15" 
          : "bg-slate-900 border-slate-700 shadow-lg shadow-slate-900/20 hover:border-blue-500/40 hover:shadow-blue-900/20 hover:-translate-y-0.5"
      }`}
    >
      <div className="relative">
        <Brain 
          size={24} 
          className={`transition-colors duration-300 ${
            isOpen ? "text-blue-400" : "text-slate-50"
          }`} 
        />

        {!isOpen && (
          <span className="absolute -top-3.5 -right-3.5 flex h-2.5 w-2.5">
            <span className="animate-pulse absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-green-400"></span>
          </span>
        )}
      </div>
    </button>
  );
}
