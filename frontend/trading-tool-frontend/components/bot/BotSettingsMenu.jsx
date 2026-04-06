"use client";

import {
  Settings,
  Wallet,
  PauseCircle,
  PlayCircle,
  Trash2,
} from "lucide-react";

/**
 * BotSettingsMenu — TradeLayer 2.5 (FINAL)
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
    <div className="w-64 rounded-xl border bg-white shadow-md p-2 text-sm">
      {/* ================= HEADER ================= */}
      <div className="px-3 py-2 text-xs font-semibold text-[var(--text-muted)]">
        Bot instellingen
      </div>

      {/* ================= ALGEMEEN ================= */}
      <button
        type="button"
        onClick={() => onOpen("general")}
        className="settings-item"
      >
        <Settings size={16} />
        <span>Algemeen</span>
      </button>

      {/* ================= PORTFOLIO ================= */}
      <button
        type="button"
        onClick={() => onOpen("portfolio")}
        className="settings-item"
      >
        <Wallet size={16} />
        <span>Portfolio & budget</span>
      </button>

      {/* ================= DIVIDER ================= */}
      <div className="my-2 border-t" />

      {/* ================= PAUSE ================= */}
      <button
        type="button"
        onClick={() => onOpen("pause")}
        className="settings-item text-orange-600"
      >
        <PauseCircle size={16} />
        <span>Bot pauzeren</span>
      </button>

      {/* ================= RESUME ================= */}
      <button
        type="button"
        onClick={() => onOpen("resume")}
        className="settings-item text-green-600"
      >
        <PlayCircle size={16} />
        <span>Bot hervatten</span>
      </button>

      {/* ================= DELETE ================= */}
      <button
        type="button"
        onClick={() => onOpen("delete")}
        className="settings-item text-red-600"
      >
        <Trash2 size={16} />
        <span>Bot verwijderen</span>
      </button>
    </div>
  );
}
