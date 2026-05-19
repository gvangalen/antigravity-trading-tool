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
 * AddBotForm — Tradamind 2.5 (FINAL)
 */
export default function AddBotForm({
  initialData = null,
  initialValues = null,
  strategies = [],
  onChange,
}) {

  const sourceData = initialData ?? initialValues;
  const isEdit = Boolean(sourceData?.id ?? sourceData?.bot_id);

  const [form, setForm] = useState({
    id: undefined,
    bot_id: undefined,
    name: "",
    strategy_id: null,
    mode: "manual",
    is_live: false,
    risk_profile: "balanced",
    base_currency: "EUR",
    budget_total_eur: 0,
    budget_daily_limit_eur: 0,
    budget_min_order_eur: 0,
    budget_max_order_eur: 0,
    max_asset_exposure_pct: 100,
  });

  /* =====================================================
     INIT / PREFILL
  ===================================================== */
  useEffect(() => {
    if (!sourceData) return;

    setForm({
      id: sourceData.id,
      bot_id: sourceData.bot_id,
      name: sourceData.name ?? "",
      strategy_id:
        typeof sourceData.strategy_id === "number"
          ? sourceData.strategy_id
          : sourceData.strategy?.id ?? null,
      mode: sourceData.mode ?? "manual",
      is_live: sourceData.is_live ?? false,
      risk_profile: sourceData.risk_profile ?? "balanced",
      base_currency: sourceData.base_currency ?? "EUR",
      budget_total_eur: sourceData.budget_total_eur ?? sourceData.budget?.total_eur ?? 0,
      budget_daily_limit_eur: sourceData.budget_daily_limit_eur ?? sourceData.budget?.daily_limit_eur ?? 0,
      budget_min_order_eur: sourceData.budget_min_order_eur ?? sourceData.budget?.min_order_eur ?? 0,
      budget_max_order_eur: sourceData.budget_max_order_eur ?? sourceData.budget?.max_order_eur ?? 0,
      max_asset_exposure_pct: sourceData.max_asset_exposure_pct ?? sourceData.budget?.max_asset_exposure_pct ?? 100,
    });
  }, [sourceData]);

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
      sourceData?.strategy ??
      null
    );
  }, [strategies, form.strategy_id, sourceData]);

  const selectedRisk =
    RISK_PROFILES.find((r) => r.value === form.risk_profile) ??
    RISK_PROFILES[1];

  const getStrategyType = (s) =>
    (s?.strategy_type || s?.type || "manual").toUpperCase();

  return (
    <div className="space-y-6">
      {/* ================= BOT NAME ================= */}
      <div className="space-y-1.5">
        <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
          Identifier Tag
        </label>
        <input
          className="w-full bg-card border-2 border-slate-100 dark:border-slate-800 rounded-2xl px-5 py-4 text-sm font-bold text-foreground focus:border-blue-600 transition-all outline-none placeholder:text-slate-300"
          placeholder="e.g. DCA BTC ALGO"
          value={form.name}
          onChange={(e) =>
            setForm((s) => ({ ...s, name: e.target.value }))
          }
        />
      </div>

      {/* ================= STRATEGY ================= */}
      <div className="space-y-1.5">
        <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
          Execution Strategy
        </label>

        {isEdit ? (
          <div className="w-full bg-slate-50 dark:bg-slate-900 border-2 border-slate-100 dark:border-slate-800 rounded-2xl px-5 py-4 text-sm font-bold text-muted cursor-not-allowed flex items-center justify-between">
            <span>
              {selectedStrategy
                ? `${selectedStrategy.name} · ${selectedStrategy.symbol}`
                : "—"}
            </span>
            <div className="text-[9px] bg-slate-200 dark:bg-slate-700 px-2 py-0.5 rounded-md uppercase tracking-tighter">Locked</div>
          </div>
        ) : (
          <div className="relative">
            <select
              className="w-full bg-card border-2 border-slate-100 dark:border-slate-800 rounded-2xl px-5 py-4 text-sm font-bold text-foreground appearance-none focus:border-blue-600 outline-none cursor-pointer"
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
        <div className="rounded-2xl bg-blue-50/30 dark:bg-blue-900/10 border-2 border-blue-600/10 p-5 space-y-3">
          <div className="flex items-center justify-between">
             <div className="text-[9px] font-black text-blue-600 dark:text-blue-400 uppercase tracking-[0.2em]">Strategy Parameters</div>
             <div className="text-[9px] font-black text-white uppercase bg-blue-600 px-2 py-0.5 rounded-md shadow-sm shadow-blue-600/20">{getStrategyType(selectedStrategy)}</div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-[8px] font-black text-blue-400 uppercase">Asset Node</div>
              <div className="text-sm font-black text-foreground dark:text-slate-100 font-mono tracking-tighter">{selectedStrategy.symbol}</div>
            </div>
            <div>
              <div className="text-[8px] font-black text-blue-400 uppercase">Time Horizon</div>
              <div className="text-sm font-black text-foreground dark:text-slate-100 font-mono tracking-tighter">{selectedStrategy.timeframe}</div>
            </div>
          </div>

          {selectedStrategy.description && (
            <div className="text-[11px] font-medium text-slate-500 italic border-t border-blue-100/50 pt-3 leading-relaxed">
              "{selectedStrategy.description}"
            </div>
          )}
        </div>
      )}

      {/* ================= EXECUTION TYPE & RISK ================= */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
            Execution Environment
          </label>
          <div className="flex bg-slate-100 dark:bg-slate-900 p-1 rounded-2xl border-2 border-slate-100 dark:border-slate-800">
             <button 
                type="button"
                onClick={() => setForm(s => ({ ...s, is_live: false }))}
                className={`flex-1 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${!form.is_live ? 'bg-white dark:bg-slate-800 text-blue-600 shadow-sm' : 'text-slate-400 hover:text-slate-600'}`}
             >
                📝 Paper Trading
             </button>
             <button 
                type="button"
                onClick={() => setForm(s => ({ ...s, is_live: true }))}
                className={`flex-1 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${form.is_live ? 'bg-white dark:bg-slate-800 text-emerald-600 shadow-sm' : 'text-slate-400 hover:text-emerald-600'}`}
             >
                ⚡ Live Exchange
             </button>
          </div>
        </div>

        <div className="space-y-1.5">
          <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
            Operating Mode
          </label>
          <div className="relative">
            <select
              className="w-full bg-card border-2 border-slate-100 dark:border-slate-800 rounded-2xl px-5 py-4 text-sm font-bold text-foreground appearance-none focus:border-blue-600 outline-none"
              value={form.mode}
              onChange={(e) =>
                setForm((s) => ({ ...s, mode: e.target.value }))
              }
            >
              <option value="manual">Manual Approval</option>
              <option value="semi-auto">Semi-Autonomous</option>
              <option value="auto">Full-Autonomous</option>
            </select>
            <div className="absolute right-5 top-1/2 -translate-y-1/2 pointer-events-none opacity-40">
               ▼
            </div>
          </div>
        </div>
      </div>
 
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
            Safety Profile
          </label>
          <div className="relative">
            <select
              className="w-full bg-card border-2 border-slate-100 dark:border-slate-800 rounded-2xl px-5 py-4 text-sm font-bold text-foreground appearance-none focus:border-blue-600 outline-none"
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

        <div className="space-y-1.5">
          <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
            Base Currency
          </label>
          <div className="relative">
            <select
              className="w-full bg-card border-2 border-slate-100 dark:border-slate-800 rounded-2xl px-5 py-4 text-sm font-bold text-foreground appearance-none focus:border-blue-600 outline-none"
              value={form.base_currency}
              onChange={(e) =>
                setForm((s) => ({
                  ...s,
                  base_currency: e.target.value,
                }))
              }
            >
              <option value="EUR">🇪🇺 EUR (Euro)</option>
              <option value="USD">🇺🇸 USD (US Dollar)</option>
            </select>
            <div className="absolute right-5 top-1/2 -translate-y-1/2 pointer-events-none opacity-40">
               ▼
            </div>
          </div>
        </div>
      </div>

      {(form.is_live || form.mode !== "manual") && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            ["budget_total_eur", "Total Budget"],
            ["budget_daily_limit_eur", "Daily Limit"],
            ["budget_min_order_eur", "Min Order"],
            ["budget_max_order_eur", "Max Order"],
          ].map(([key, label]) => (
            <div key={key} className="space-y-1.5">
              <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1">
                {label}
              </label>
              <input
                type="number"
                min="0"
                step="0.01"
                className="w-full bg-card border-2 border-slate-100 dark:border-slate-800 rounded-2xl px-4 py-3 text-sm font-bold text-foreground focus:border-blue-600 transition-all outline-none"
                value={form[key]}
                onChange={(e) => setForm((s) => ({ ...s, [key]: Number(e.target.value) }))}
              />
            </div>
          ))}
        </div>
      )}

      {/* PROFILE DESCRIPTION */}
      <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-900/50 border-2 border-slate-100 dark:border-slate-800 flex items-center gap-4 transition-all hover:bg-slate-100">
         <div className="w-10 h-10 rounded-xl bg-card border border-slate-100 shadow-sm flex items-center justify-center text-lg">
            {selectedRisk.label.split(' ')[0]}
         </div>
         <div className="text-[11px] font-bold text-slate-500 leading-relaxed italic">
            {selectedRisk.description}
         </div>
      </div>
    </div>
  );
}
