"use client";

import {
  Bot as BotIcon,
  Pencil,
  Trash2,
  Play,
  Target,
  Activity,
  Layers,
  Settings2,
} from "lucide-react";

import { useActiveSetup } from "@/app/providers/SetupProvider";
import { useTranslation } from "@/app/providers/I18nProvider";

export default function BotCard({
  bot,
  isActive = false,
  onSelect,
  onEdit,
  onDelete,
  onRun,
  showActions = true,
}) {
  const { t } = useTranslation();
  const copy: Record<string, string> = t?.botPage?.botCard || {};
  const { focusedBotId, setFocusedBotId } = useActiveSetup();
  
  if (!bot) return null;

  const { id, name, is_active, strategy } = bot;
  const isFocused = focusedBotId === id;

  // 🔧 FIX: backend gebruikt strategy_type
  const getStrategyType = (s) =>
    (s?.strategy_type || s?.type || "manual").toUpperCase();

  return (
    <div
      data-bot-id={id}
      onClick={() => onSelect?.(id)}
      className={`
        card cursor-pointer group relative overflow-hidden
        ${
          isActive
            ? "ring-4 ring-blue-600/20 border-blue-600 shadow-xl shadow-blue-600/10"
            : "hover:border-blue-500/50"
        }
      `}
    >
      {/* Premium Gradient Background Effect on Hover */}
      <div className="absolute inset-0 bg-gradient-to-br from-blue-50/50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />

      <div className="relative p-6 space-y-6">
        {/* ================= HEADER ================= */}
        <div className="flex justify-between items-start">
          <div className="flex items-center gap-4">
            <div className={`
              w-12 h-12 rounded-2xl flex items-center justify-center transition-all
              ${isActive ? 'bg-blue-600 text-white shadow-lg' : 'bg-slate-100 text-slate-400 group-hover:bg-blue-50 group-hover:text-blue-600'}
            `}>
              <BotIcon size={24} />
            </div>

            <div className="space-y-1">
              <h3 className="text-lg font-black tracking-tight text-slate-900 dark:text-white leading-none">
                {name}
              </h3>

              <div className="flex items-center gap-2">
                <span className={`status ${is_active ? 'status-active' : 'status-neutral'} !py-1 !px-2 !text-[9px]`}>
                  {is_active ? (
                    <>
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                      {copy.active}
                    </>
                  ) : copy.inactive}
                </span>
                
                {strategy && (
                  <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
                    {strategy.symbol || copy.noSymbol}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* ACTION ICONS - Floating on right */}
          <div className="flex gap-1">
            <button
              className={`p-2 rounded-xl transition-all ${isFocused ? 'bg-blue-600 text-white shadow-md' : 'text-slate-300 hover:text-blue-600 hover:bg-blue-50'}`}
              onClick={(e) => {
                e.stopPropagation();
                setFocusedBotId(isFocused ? null : id);
              }}
              title={isFocused ? copy.unfocus : copy.focus}
            >
              <Target size={16} className={isFocused ? "animate-pulse" : ""} />
            </button>

            {showActions && (
              <>
                <button
                  className="p-2 rounded-xl text-slate-300 hover:text-slate-600 hover:bg-slate-100 transition-all"
                  onClick={(e) => {
                    e.stopPropagation();
                    onEdit?.(id);
                  }}
                  title={copy.edit}
                >
                  <Pencil size={16} />
                </button>

                <button
                  className="p-2 rounded-xl text-slate-300 hover:text-rose-600 hover:bg-rose-50 transition-all"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete?.(id);
                  }}
                  title={copy.delete}
                >
                  <Trash2 size={16} />
                </button>
              </>
            )}
          </div>
        </div>

        {/* ================= STRATEGY INFO ================= */}
        {strategy ? (
          <div className="trade-surface !p-4 group/strategy">
            <div className="flex items-center gap-2 mb-3">
              <Settings2 size={14} className="text-blue-600" />
              <span className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">{copy.strategyConfig}</span>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">{copy.name}</p>
                <p className="text-xs font-black text-slate-900 dark:text-slate-200 truncate">{strategy.name}</p>
              </div>
              <div className="space-y-1">
                <p className="text-[9px] font-bold text-slate-400 uppercase tracking-widest">{copy.type}</p>
                <p className="text-xs font-black text-blue-600">{getStrategyType(strategy)}</p>
              </div>
            </div>

            <div className="mt-3 pt-3 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-1">
                   <Activity size={10} className="text-slate-400" />
                   <span className="text-[10px] font-black text-slate-600 uppercase">{strategy.timeframe || "–"}</span>
                </div>
                <div className="flex items-center gap-1">
                   <Layers size={10} className="text-slate-400" />
                   <span className="text-[10px] font-black text-slate-600 uppercase">{copy.version}</span>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="p-4 rounded-2xl border-2 border-dashed border-slate-100 flex flex-col items-center justify-center text-center">
            <p className="text-xs font-bold text-slate-400">{copy.noStrategy}</p>
          </div>
        )}

        {/* ================= FOOTER / ACTION ================= */}
        <div className="flex items-center justify-between gap-4">
           {showActions && (
            <button
              className={`
                flex-1 flex items-center justify-center gap-2 py-3 rounded-xl 
                text-[11px] font-black uppercase tracking-widest transition-all
                active:scale-[0.98]
                ${strategy 
                  ? "bg-slate-900 hover:bg-black text-white shadow-lg hover:shadow-xl translate-y-[-2px] hover:translate-y-[-4px]" 
                  : "bg-slate-100 text-slate-300 cursor-not-allowed"}
              `}
              onClick={(e) => {
                e.stopPropagation();
                onRun?.(id);
              }}
              disabled={!strategy}
            >
              <Play size={14} fill="currentColor" />
              {copy.startExecution}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
