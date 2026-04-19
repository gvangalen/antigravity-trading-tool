"use client";

import {
  Settings,
  Wallet,
  PauseCircle,
  PlayCircle,
  Trash2,
} from "lucide-react";

/**
 * BotSettingsMenu — Tradamind 2.5 (FINAL)
 * --------------------------------------------------
 * ❌ kent GEEN bot
 * ❌ GEEN state
 * ❌ GEEN business logic
 *
 * ✅ dom menu
 * ✅ roept alleen onOpen(type)
 *
 * Types:
 * - "general"
 * - "portfolio"
 * - "pause"
 * - "resume"
 * - "delete"
 */
export default function BotSettingsMenu({ onOpen }) {
  return (
    <div className="w-64 rounded-xl border border-slate-200 bg-white dark:bg-slate-900 shadow-xl p-2 text-sm flex flex-col gap-1">
      {/* ================= HEADER ================= */}
      <div className="px-3 py-2 text-[10px] font-black text-slate-400 uppercase tracking-widest border-b border-slate-50 dark:border-slate-800 mb-1">
        Bot instellingen
      </div>

      {/* ================= ALGEMEEN ================= */}
      <button
        type="button"
        onClick={() => onOpen("general")}
        className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors group text-left"
      >
        <div className="p-1.5 bg-slate-100 dark:bg-slate-800 rounded-md group-hover:bg-blue-50 dark:group-hover:bg-blue-900/40 group-hover:text-blue-600 transition-colors">
          <Settings size={14} />
        </div>
        <span className="font-bold text-foreground dark:text-slate-200">Algemeen</span>
      </button>

      {/* ================= PORTFOLIO ================= */}
      <button
        type="button"
        onClick={() => onOpen("portfolio")}
        className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors group text-left"
      >
        <div className="p-1.5 bg-slate-100 dark:bg-slate-800 rounded-md group-hover:bg-indigo-50 dark:group-hover:bg-indigo-900/40 group-hover:text-indigo-600 transition-colors">
          <Wallet size={14} />
        </div>
        <span className="font-bold text-foreground dark:text-slate-200">Portfolio & budget</span>
      </button>

      {/* ================= DIVIDER ================= */}
      <div className="my-1 border-t border-slate-50 dark:border-slate-800" />

      {/* ================= PAUSE ================= */}
      <button
        type="button"
        onClick={() => onOpen("pause")}
        className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-orange-50 dark:hover:bg-orange-950/20 transition-colors group text-left"
      >
        <div className="p-1.5 bg-orange-50 dark:bg-orange-950/20 rounded-md text-orange-600 group-hover:bg-orange-100 transition-colors">
          <PauseCircle size={14} />
        </div>
        <span className="font-bold text-orange-600">Bot pauzeren</span>
      </button>

      {/* ================= RESUME ================= */}
      <button
        type="button"
        onClick={() => onOpen("resume")}
        className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-green-50 dark:hover:bg-green-950/20 transition-colors group text-left"
      >
        <div className="p-1.5 bg-green-50 dark:bg-green-950/20 rounded-md text-green-600 group-hover:bg-green-100 transition-colors">
          <PlayCircle size={14} />
        </div>
        <span className="font-bold text-green-600">Bot hervatten</span>
      </button>

      {/* ================= DELETE ================= */}
      <button
        type="button"
        onClick={() => onOpen("delete")}
        className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-950/20 transition-colors group text-left"
      >
        <div className="p-1.5 bg-red-50 dark:bg-red-950/20 rounded-md text-red-600 group-hover:bg-red-100 transition-colors">
          <Trash2 size={14} />
        </div>
        <span className="font-bold text-red-600">Bot verwijderen</span>
      </button>
    </div>
  );
}
