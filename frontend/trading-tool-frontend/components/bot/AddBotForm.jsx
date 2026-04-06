"use client";

import { useEffect, useMemo, useState } from "react";

const RISK_PROFILES = [
  {
    value: "conservative",
    label: "🛡️ Conservative",
    description: "Alleen trades bij hoge confidence, lage frequentie",
  },
  {
    value: "balanced",
    label: "⚖️ Balanced",
    description: "Standaard profiel met gebalanceerde trade-frequentie",
  },
  {
    value: "aggressive",
    label: "🚀 Aggressive",
    description: "Sneller trades, hogere exposure en risico",
  },
];

/**
 * AddBotForm — TradeLayer 2.5 (FINAL)
 */
export default function AddBotForm({
  initialData = null,
  strategies = [],
  onChange,
}) {

  const isEdit = Boolean(initialData?.id ?? initialData?.bot_id);

  const [form, setForm] = useState({
    id: undefined,
    bot_id: undefined,
    name: "",
    strategy_id: null,
    mode: "manual",
    risk_profile: "balanced",
  });

  /* =====================================================
     INIT / PREFILL
  ===================================================== */
  useEffect(() => {
    if (!initialData) return;

    setForm({
      id: initialData.id,
      bot_id: initialData.bot_id,
      name: initialData.name ?? "",
      strategy_id:
        typeof initialData.strategy_id === "number"
          ? initialData.strategy_id
          : initialData.strategy?.id ?? null,
      mode: initialData.mode ?? "manual",
      risk_profile: initialData.risk_profile ?? "balanced",
    });
  }, [initialData]);

  /* =====================================================
     LIVE SYNC NAAR PARENT
  ===================================================== */
  useEffect(() => {
    onChange?.(form);
  }, [form, onChange]);

  /* =====================================================
     DERIVED
  ===================================================== */
  const selectedStrategy = useMemo(() => {
    return (
      strategies.find((s) => s.id === form.strategy_id) ??
      initialData?.strategy ??
      null
    );
  }, [strategies, form.strategy_id, initialData]);

  const selectedRisk =
    RISK_PROFILES.find((r) => r.value === form.risk_profile) ??
    RISK_PROFILES[1];

  const getStrategyType = (s) =>
    (s?.strategy_type || s?.type || "manual").toUpperCase();

  /* =====================================================
     RENDER
  ===================================================== */
  return (
    <div className="space-y-8 p-1">
      {/* ================= BOT NAME ================= */}
      <div className="space-y-2">
        <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">
          Identifier Tag
        </label>
        <input
          className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-5 py-4 text-sm font-bold text-slate-800 focus:ring-2 focus:ring-[var(--primary)] focus:border-transparent transition-all outline-none placeholder:text-slate-300"
          placeholder="e.g. DCA BTC ALGO"
          value={form.name}
          onChange={(e) =>
            setForm((s) => ({ ...s, name: e.target.value }))
          }
        />
      </div>

      {/* ================= STRATEGY ================= */}
      <div className="space-y-2">
        <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">
          Execution Strategy
        </label>

        {isEdit ? (
          <div className="w-full bg-slate-100 border border-slate-200 rounded-2xl px-5 py-4 text-sm font-bold text-slate-500 cursor-not-allowed flex items-center justify-between">
            <span>
              {selectedStrategy
                ? `${selectedStrategy.name} · ${selectedStrategy.symbol}`
                : "—"}
            </span>
            <div className="text-[9px] bg-slate-200 px-2 py-0.5 rounded-md uppercase tracking-tighter">Locked</div>
          </div>
        ) : (
          <div className="relative">
            <select
              className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-5 py-4 text-sm font-bold text-slate-800 appearance-none focus:ring-2 focus:ring-[var(--primary)] outline-none cursor-pointer"
              value={form.strategy_id ?? ""}
              onChange={(e) =>
                setForm((s) => ({
                  ...s,
                  strategy_id: e.target.value
                    ? Number(e.target.value)
                    : null,
                }))
              }
            >
              <option value="">— Select Baseline Strategy —</option>
              {strategies.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.display_name || `${s.name} · ${s.symbol} · ${s.timeframe}`}
                </option>
              ))}
            </select>
            <div className="absolute right-5 top-1/2 -translate-y-1/2 pointer-events-none opacity-40">
               ▼
            </div>
          </div>
        )}
      </div>

      {/* ================= STRATEGY PREVIEW ================= */}
      {selectedStrategy && (
        <div className="rounded-2xl bg-blue-50/50 border border-blue-100 p-5 space-y-3">
          <div className="flex items-center justify-between">
             <div className="text-[9px] font-black text-blue-400 uppercase tracking-[0.2em]">Strategy Parameters</div>
             <div className="text-[9px] font-black text-blue-600 uppercase bg-blue-100 px-2 py-0.5 rounded-md">{getStrategyType(selectedStrategy)}</div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-[8px] font-bold text-blue-300 uppercase">Asset Node</div>
              <div className="text-sm font-black text-blue-800 font-mono tracking-tighter">{selectedStrategy.symbol}</div>
            </div>
            <div>
              <div className="text-[8px] font-bold text-blue-300 uppercase">Time Horizon</div>
              <div className="text-sm font-black text-blue-800 font-mono tracking-tighter">{selectedStrategy.timeframe}</div>
            </div>
          </div>

          {selectedStrategy.description && (
            <div className="text-xs text-blue-600/70 border-t border-blue-100 pt-3 italic">
              {selectedStrategy.description}
            </div>
          )}
        </div>
      )}

      {/* ================= MODE & RISK GRID ================= */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="space-y-2">
          <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">
            Operating Mode
          </label>
          <div className="relative">
            <select
              className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-5 py-4 text-sm font-bold text-slate-800 appearance-none focus:ring-2 focus:ring-[var(--primary)] outline-none"
              value={form.mode}
              onChange={(e) =>
                setForm((s) => ({ ...s, mode: e.target.value }))
              }
            >
              <option value="manual">Manual Approval</option>
              <option value="semi">Semi-Autonomous</option>
              <option value="auto">Full-Autonomous</option>
            </select>
            <div className="absolute right-5 top-1/2 -translate-y-1/2 pointer-events-none opacity-40">
               ▼
            </div>
          </div>
        </div>

        <div className="space-y-2">
          <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest pl-1">
            Safety Profile
          </label>
          <div className="relative">
            <select
              className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-5 py-4 text-sm font-bold text-slate-800 appearance-none focus:ring-2 focus:ring-[var(--primary)] outline-none"
              value={form.risk_profile}
              onChange={(e) =>
                setForm((s) => ({
                  ...s,
                  risk_profile: e.target.value,
                }))
              }
            >
              {RISK_PROFILES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
            <div className="absolute right-5 top-1/2 -translate-y-1/2 pointer-events-none opacity-40">
               ▼
            </div>
          </div>
        </div>
      </div>

      {/* PROFILE DESCRIPTION */}
      <div className="p-4 rounded-xl bg-slate-50 border border-dashed border-slate-200 flex items-center gap-3">
         <div className="w-10 h-10 rounded-full bg-white flex items-center justify-center text-lg shadow-sm">
            {selectedRisk.label.split(' ')[0]}
         </div>
         <div className="text-xs font-bold text-slate-500 italic">
            {selectedRisk.description}
         </div>
      </div>
    </div>
  );
}
