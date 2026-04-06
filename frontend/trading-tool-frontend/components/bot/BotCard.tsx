"use client";

import {
  Bot as BotIcon,
  Pencil,
  Trash2,
  Play,
} from "lucide-react";

export default function BotCard({
  bot,
  isActive = false,
  onSelect,
  onEdit,
  onDelete,
  onRun,
}) {
  if (!bot) return null;

  const { id, name, is_active, strategy } = bot;

  // 🔧 FIX: backend gebruikt strategy_type
  const getStrategyType = (s) =>
    (s?.strategy_type || s?.type || "manual").toUpperCase();

  return (
    <div
      data-bot-id={id}
      onClick={() => onSelect?.(id)}
      className={`
        card-surface cursor-pointer p-4 space-y-4
        transition
        ${
          isActive
            ? "ring-2 ring-[var(--primary)]"
            : "hover:shadow-md"
        }
      `}
    >
      {/* ================= HEADER ================= */}
      <div className="flex justify-between items-start">
        <div className="flex items-center gap-2">
          <BotIcon className="icon icon-primary" />

          <div>
            <h3 className="font-semibold leading-tight text-[var(--text-dark)]">
              {name}
            </h3>

            {strategy ? (
              <p className="text-xs text-[var(--text-muted)]">
                {getStrategyType(strategy)} •{" "}
                {strategy.symbol} • {strategy.timeframe}
              </p>
            ) : (
              <p className="text-xs icon-danger">
                ⚠️ Geen strategie gekoppeld
              </p>
            )}
          </div>
        </div>

        {/* ACTION ICONS */}
        <div className="flex gap-2">
          <button
            className="btn-ghost"
            onClick={(e) => {
              e.stopPropagation();
              onEdit?.(id);
            }}
            title="Bewerken"
          >
            <Pencil size={16} />
          </button>

          <button
            className="btn-ghost icon-danger"
            onClick={(e) => {
              e.stopPropagation();
              onDelete?.(id);
            }}
            title="Verwijderen"
          >
            <Trash2 size={16} />
          </button>
        </div>
      </div>

      {/* ================= STRATEGY INFO ================= */}
      {strategy && (
        <div className="rounded-md bg-[var(--surface-2)] p-3 text-sm space-y-1">
          <div>
            <b>Strategie:</b> {strategy.name}
          </div>
          <div className="text-[var(--text-muted)]">
            Type: {getStrategyType(strategy)}
          </div>
        </div>
      )}

      {/* ================= STATUS + ACTION ================= */}
      <div className="flex justify-between items-center pt-2">
        <span
          className={`text-xs font-medium ${
            is_active ? "icon-success" : "text-[var(--text-muted)]"
          }`}
        >
          {is_active ? "Actief" : "Inactief"}
        </span>

        <button
          className="btn-primary flex items-center gap-1"
          onClick={(e) => {
            e.stopPropagation();
            onRun?.(id);
          }}
          disabled={!strategy}
          title={
            strategy
              ? "Bot uitvoeren"
              : "Koppel eerst een strategie"
          }
        >
          <Play size={14} />
          Run
        </button>
      </div>
    </div>
  );
}
